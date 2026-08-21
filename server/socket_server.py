"""
AgentSocket - Server Gateway Strip
FastAPI WebSocket and HTTP Hub connecting AI Agent frameworks with the Chrome Extension.
"""

import asyncio
import json
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from server.models import (
    ActionType,
    WSMessageType,
    ControlMode,
    ResponseStatus,
    ErrorCode,
    AgentActionPayload,
    ReleasePayload,
    BorrowSubskillPayload,
    RegisterSubskillPayload,
    StandardResponse,
    ServerStatusResponse,
    SessionStatus,
    SessionEventType,
)
from server.session_manager import session_manager

# Configurable idle timeout (default: 20 minutes = 1200 seconds)
IDLE_TIMEOUT_SECONDS = float(os.environ.get("SOCKET_IDLE_TIMEOUT", "1200"))
PID_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".socket_server.pid")


class SystemState:
    def __init__(self):
        self.extension_ws: Optional[WebSocket] = None
        self.human_in_control: bool = False
        self.last_intervention_notes: Optional[str] = None
        self.takeover_start_time: Optional[float] = None
        self.pending_responses: dict[str, asyncio.Future] = {}
        self.last_activity_time: float = time.time()
        self.watchdog_task: Optional[asyncio.Task] = None

    def record_activity(self):
        self.last_activity_time = time.time()


state = SystemState()


def write_pid_file():
    try:
        with open(PID_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        print(f"[Watchdog] Warning: Unable to write PID file: {e}")


def remove_pid_file():
    try:
        if os.path.exists(PID_FILE_PATH):
            os.remove(PID_FILE_PATH)
    except Exception as e:
        print(f"[Watchdog] Warning: Unable to remove PID file: {e}")


async def idle_watchdog_loop():
    print(f"[Watchdog] Auto-idle watchdog started (timeout: {IDLE_TIMEOUT_SECONDS}s / {IDLE_TIMEOUT_SECONDS/60:.1f}m).")
    try:
        while True:
            await asyncio.sleep(10)
            # Check for inactive tab group sessions (>5 minutes)
            session_manager.check_inactivity(inactivity_threshold_seconds=300.0)

            idle_duration = time.time() - state.last_activity_time
            if idle_duration >= IDLE_TIMEOUT_SECONDS:
                print(f"\n[WATCHDOG] Idle duration {idle_duration:.1f}s exceeded limit of {IDLE_TIMEOUT_SECONDS}s.")
                print("[WATCHDOG] Cleanly shutting down background gateway process...\n")
                remove_pid_file()
                os._exit(0)
    except asyncio.CancelledError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    write_pid_file()
    state.record_activity()
    state.watchdog_task = asyncio.create_task(idle_watchdog_loop())
    
    yield
    
    # Shutdown
    if state.watchdog_task and not state.watchdog_task.done():
        state.watchdog_task.cancel()
    
    # Abort pending responses
    for cmd_id, future in list(state.pending_responses.items()):
        if not future.done():
            future.set_result({"status": "aborted", "message": "Server shutting down."})
    state.pending_responses.clear()
    
    # Close any active sessions
    session_manager.handle_disconnect()
    
    remove_pid_file()


app = FastAPI(title="AgentSocket Server Gateway", lifespan=lifespan)

# Enable global cross-origin rules
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    state.record_activity()
    return {
        "status": "AgentSocket Server is Live", 
        "extension_connected": state.extension_ws is not None,
        "human_in_control": state.human_in_control,
        "idle_seconds_remaining": max(0.0, IDLE_TIMEOUT_SECONDS - (time.time() - state.last_activity_time))
    }


@app.get("/status")
def get_status():
    state.record_activity()
    return {
        "status": "AgentSocket Server is Live",
        "extension_connected": state.extension_ws is not None,
        "human_in_control": state.human_in_control,
        "last_intervention_notes": state.last_intervention_notes,
        "idle_seconds_remaining": max(0.0, IDLE_TIMEOUT_SECONDS - (time.time() - state.last_activity_time))
    }


@app.get("/history")
def get_history(query: str = "", month: Optional[str] = None, limit: int = 10):
    state.record_activity()
    return session_manager.query_history(query_hint=query, month=month, limit=limit)


@app.get("/session/details")
def get_session_details(path: str):
    state.record_activity()
    return session_manager.get_session_details(session_path=path)


@app.get("/session/artifact")
def get_session_artifact(path: str, name: str):
    state.record_activity()
    return session_manager.get_session_artifact(session_path=path, artifact_name=name)


@app.get("/session/document")
def get_session_document(path: str):
    state.record_activity()
    doc = session_manager.generate_session_document(session_dir_or_path=path)
    return {"status": "success", "session_path": path, "document_markdown": doc}


@app.get("/subskills")
def list_subskills(query: str = "", tags: Optional[str] = None):
    state.record_activity()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return session_manager.list_subskills(query=query, tags=tag_list)


@app.get("/subskills/{name}")
def get_subskill(name: str):
    state.record_activity()
    res = session_manager.get_subskill(name=name)
    if not res:
        return {"status": "error", "message": f"Subskill '{name}' not found."}
    return {"status": "success", "data": res}


@app.post("/subskills/borrow")
def borrow_subskill(payload: BorrowSubskillPayload):
    state.record_activity()
    return session_manager.borrow_subskill(
        name=payload.name,
        target_session_id_or_title_or_path=payload.session_title,
        tab_group_id=payload.tab_group_id,
        input_file_path=payload.input_file_path,
    )


@app.post("/subskills/register")
def register_subskill(payload: RegisterSubskillPayload):
    state.record_activity()
    return session_manager.register_subskill(
        session_path=payload.session_path,
        name=payload.name,
        display_title=payload.display_title,
        description=payload.description,
        tags=payload.tags,
        adhoc_tools=payload.adhoc_tools,
        subskill_markdown=payload.subskill_markdown,
    )



@app.websocket("/ws/extension")
async def extension_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.extension_ws = websocket
    state.record_activity()
    print("\n[SUCCESS] ==========================================")
    print("[AgentSocket] Chrome Extension plugged in cleanly via WebSocket.")
    print("====================================================\n")
    try:
        while True:
            raw_message = await websocket.receive_text()
            state.record_activity()
            message = json.loads(raw_message)
            msg_type = message.get("type")
            
            if msg_type == WSMessageType.PING.value or msg_type == "ping":
                continue
            
            if msg_type == WSMessageType.STATE_CHANGE.value or msg_type == "state_change":
                new_state = message.get("human_in_control", False)
                if not new_state and state.human_in_control:
                    print("[AgentSocket] Info: Extension sent release state. Release must go through the /human_release endpoint.")
                else:
                    state.human_in_control = new_state
                    if state.human_in_control:
                        state.takeover_start_time = time.time()
                        if message.get("notes"):
                            state.last_intervention_notes = message.get("notes")
                    print(f"[AgentSocket] State Sync -> Human In Control: {state.human_in_control}")
            
            elif msg_type == WSMessageType.COMMAND_RESPONSE.value or msg_type == "command_response":
                cmd_id = message.get("command_id")
                if cmd_id in state.pending_responses:
                    state.pending_responses[cmd_id].set_result(message.get("payload"))
                    
    except WebSocketDisconnect:
        print("\n[DISCONNECT] Chrome Extension unplugged from AgentSocket bridge.\n")
        # Abort any active sessions due to abrupt disconnect
        session_manager.handle_disconnect()
    finally:
        state.extension_ws = None
        state.record_activity()


@app.post("/execute")
async def execute_to_extension(command: AgentActionPayload):
    state.record_activity()
    t_start = time.time()
    session_title = command.session_title or "AgentSocket Task"
    group_color = command.group_color or "purple"
    
    # Non-blocking check: immediately report lock if human is currently in control
    if state.human_in_control:
        return {
            "status": ResponseStatus.HUMAN_LOCKED.value,
            "message": "Human operator is currently in control of the browser session.",
            "last_intervention_notes": state.last_intervention_notes,
            "instructions": "Wait for human operator to click 'Release Control' or check GET /status."
        }

    # Check if we should inject human notes context from a recent release
    if state.last_intervention_notes:
        injected_context = f"[HUMAN INTERVENTION OVERRIDE LOG]: {state.last_intervention_notes}"
        state.last_intervention_notes = None  
        return {
            "status": ResponseStatus.RESUMED_CONTEXT.value,
            "message": injected_context,
            "instructions": "Human operator handoff caught. Adapt steps using log data."
        }

    # PRIVACY TRIGGER CHECK
    sensitive_keywords = [
        "credential", "password", "payment", "checkout", "bank", "dashboard", 
        "scrape", "scraping", "login", "signin", "signup", "creditcard", "cvv", 
        "card_number", "personal", "account", "stripe", "paypal"
    ]
    
    trigger_fired = False
    reason = ""
    
    if command.requires_privacy_check:
        trigger_fired = True
        reason = "requires_privacy_check flag set to True"
    else:
        target_lower = command.target_data.lower()
        matched_kws = [kw for kw in sensitive_keywords if kw in target_lower]
        if matched_kws:
            trigger_fired = True
            reason = f"sensitive keywords detected: {', '.join(matched_kws)}"

    if trigger_fired:
        state.human_in_control = True
        state.takeover_start_time = time.time()
        if state.extension_ws:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.STATE_SYNC.value,
                "human_in_control": True,
                "notes": f"Security Abort: {reason}"
            }))
        print(f"[SECURITY ABORT] Outbound requests locked. {reason}")

        # Log security abort event to active session if one exists
        active_sess = session_manager.get_active_session_by_title(session_title)
        if active_sess:
            session_manager.log_event(
                tab_group_id=active_sess.tab_group_id,
                event_type=SessionEventType.SECURITY_ABORT,
                title="Security Abort Triggered",
                start_time=t_start,
                end_time=time.time(),
                payload={"reason": reason, "target_data": "[REDACTED SENSITIVE DATA]"}
            )

        return {
            "status": ResponseStatus.SECURITY_ABORT.value,
            "message": f"Sensitive scope detected. Outbound requests locked. Human intervention required. Reason: {reason}"
        }

    if not state.extension_ws:
        return {
            "status": ResponseStatus.ERROR.value, 
            "message": "Extension is offline.",
            "error": {"code": ErrorCode.EXTENSION_OFFLINE.value, "message": "Chrome extension is not plugged into WebSocket gateway."}
        }

    cmd_id = command.id
    loop = asyncio.get_running_loop()
    state.pending_responses[cmd_id] = loop.create_future()

    # Enforce schema inside WS frame
    await state.extension_ws.send_text(json.dumps({
        "type": WSMessageType.EXECUTE_ACTION.value,
        "id": command.id,
        "action_type": command.action_type.value if hasattr(command.action_type, "value") else str(command.action_type),
        "target_data": command.target_data,
        "requires_privacy_check": command.requires_privacy_check,
        "session_title": command.session_title,
        "group_color": command.group_color
    }))

    try:
        result = await asyncio.wait_for(state.pending_responses[cmd_id], timeout=30.0)
        t_end = time.time()

        # Correlate / create session based on returned tab group ID or title
        tab_group_id = None
        tab_id = None
        if isinstance(result, dict):
            tab_group_id = result.get("groupId")
            tab_id = result.get("tabId")

        # Fallback to active session by title if groupId was not in result (e.g. execute_js)
        if tab_group_id is None:
            existing = session_manager.get_active_session_by_title(session_title)
            if existing:
                tab_group_id = existing.tab_group_id
            else:
                tab_group_id = 1  # Default tab group 1 if standalone

        session = session_manager.get_or_create_session(
            tab_group_id=tab_group_id,
            tab_group_name=session_title,
            group_color=group_color
        )

        # Log event based on ActionType
        act_val = command.action_type.value if hasattr(command.action_type, "value") else str(command.action_type)
        if act_val == ActionType.NAVIGATE.value:
            session_manager.log_event(
                tab_group_id=tab_group_id,
                event_type=SessionEventType.NAVIGATE,
                title=f"Navigate to {command.target_data}",
                start_time=t_start,
                end_time=t_end,
                tab_id=tab_id,
                tab_group_id_val=tab_group_id,
                url=command.target_data,
                payload={"target_url": command.target_data, "result": result}
            )
        elif act_val == ActionType.EXECUTE_JS.value:
            session_manager.log_event(
                tab_group_id=tab_group_id,
                event_type=SessionEventType.EXECUTE_JS,
                title=f"Execute JavaScript ({command.target_data[:40]}...)",
                start_time=t_start,
                end_time=t_end,
                tab_id=tab_id,
                tab_group_id_val=tab_group_id,
                payload={"script": command.target_data, "output": result.get("output") if isinstance(result, dict) else result, "result": result}
            )
        elif act_val == ActionType.TASK_COMPLETE.value:
            session_manager.log_event(
                tab_group_id=tab_group_id,
                event_type=SessionEventType.TASK_COMPLETE,
                title=f"Task Completed: {session_title}",
                start_time=t_start,
                end_time=t_end,
                tab_id=tab_id,
                tab_group_id_val=tab_group_id,
                payload={"result": result}
            )
            # Finalize session as completed
            session_manager.finalize_session(tab_group_id=tab_group_id, status=SessionStatus.COMPLETED, end_reason="task_complete")

        return {"status": ResponseStatus.SUCCESS.value, "result": result}
    except asyncio.TimeoutError:
        t_end = time.time()
        active_sess = session_manager.get_active_session_by_title(session_title)
        if active_sess:
            session_manager.log_event(
                tab_group_id=active_sess.tab_group_id,
                event_type=SessionEventType.ERROR,
                title="Command Execution Timeout",
                start_time=t_start,
                end_time=t_end,
                payload={"error": ErrorCode.EXECUTION_TIMEOUT.value, "message": "Command execution exceeded 30.0s limit."}
            )
        return {
            "status": ResponseStatus.ERROR.value, 
            "message": "Execution engine frame timed out.",
            "error": {"code": ErrorCode.EXECUTION_TIMEOUT.value, "message": "Command execution exceeded 30.0s limit."}
        }
    finally:
        state.pending_responses.pop(cmd_id, None)


@app.post("/human_release")
async def human_release(payload: ReleasePayload):
    state.record_activity()
    state.human_in_control = False
    state.last_intervention_notes = payload.notes if payload.notes else "Released by human operator."
    
    t_now = time.time()
    takeover_dur_ms = 0.0
    if state.takeover_start_time:
        takeover_dur_ms = max(0.0, round((t_now - state.takeover_start_time) * 1000.0, 2))
        state.takeover_start_time = None

    print(f"[AgentSocket] Human Release Endpoint -> Human In Control: {state.human_in_control}, Notes: {state.last_intervention_notes}, Duration: {takeover_dur_ms}ms")
    
    # Log human release event to all active sessions
    for gid in list(session_manager.active_sessions.keys()):
        session_manager.log_event(
            tab_group_id=gid,
            event_type=SessionEventType.HUMAN_RELEASE,
            title="Human Operator Release Handoff",
            start_time=t_now - (takeover_dur_ms / 1000.0),
            end_time=t_now,
            payload={
                "notes": state.last_intervention_notes,
                "takeover_duration_ms": takeover_dur_ms,
            }
        )

    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.STATE_SYNC.value,
                "human_in_control": False,
                "notes": state.last_intervention_notes
            }))
        except Exception as e:
            print(f"[AgentSocket] Error sending state_sync on release: {e}")
            
    return {"status": ResponseStatus.SUCCESS.value, "human_in_control": False}


@app.post("/stop")
async def stop_active_task():
    state.record_activity()
    state.human_in_control = False
    state.last_intervention_notes = None
    state.takeover_start_time = None
    
    # Finalize all active sessions in session_manager as stopped
    for gid in list(session_manager.active_sessions.keys()):
        session_manager.finalize_session(
            tab_group_id=gid,
            status=SessionStatus.STOPPED,
            end_reason="user_stopped"
        )

    # Cancel all pending future responses
    for cmd_id, future in list(state.pending_responses.items()):
        if not future.done():
            future.set_result({"status": "aborted", "message": "Task terminated by human operator."})
    state.pending_responses.clear()
    
    print("[AgentSocket] Task aborted by user takeover stop command.")
    
    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.STATE_SYNC.value,
                "human_in_control": False,
                "notes": "Task terminated."
            }))
        except Exception as e:
            print(f"[AgentSocket] Error sending state_sync on stop: {e}")

    return {"status": ResponseStatus.SUCCESS.value}

