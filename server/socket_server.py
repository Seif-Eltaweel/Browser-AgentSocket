"""
AgentSocket - Server Gateway Strip
FastAPI WebSocket and HTTP Hub connecting AI Agent frameworks with the Chrome Extension.
"""

from __future__ import annotations
import asyncio
import json
import os
import platform
import signal
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from server.logger import logger
from server.models import (
    ActionType,
    AgentActionPayload,
    BorrowSubskillPayload,
    ControlMode,
    ErrorCode,
    ProgressPayload,
    PromoteAdhocPayload,
    RegisterSubskillPayload,
    ReleasePayload,
    ResponseStatus,
    RunAdhocPayload,
    ServerStatusResponse,
    SessionEventType,
    SessionStatus,
    StandardResponse,
    WSMessageType,
)
from server.session import session_manager

# Configurable idle timeout (default: 20 minutes = 1200 seconds)
IDLE_TIMEOUT_SECONDS = float(os.environ.get("SOCKET_IDLE_TIMEOUT", "1200"))
PID_FILE_PATH = os.path.join(REPO_ROOT, ".socket_server.pid")
PORT_FILE_PATH = os.path.join(REPO_ROOT, ".socket_server.port")


class SystemState:
    def __init__(self) -> None:
        self.extension_ws: WebSocket | None = None
        self.human_in_control: bool = False
        self.last_intervention_notes: str | None = None
        self.takeover_start_time: float | None = None
        self.pending_responses: dict[str, asyncio.Future] = {}
        self.last_activity_time: float = time.time()
        self.watchdog_task: asyncio.Task | None = None
        self.agent_name: str | None = None
        self.group_color: str | None = None

    def record_activity(self) -> None:
        self.last_activity_time = time.time()


state = SystemState()


def write_pid_file() -> None:
    try:
        with open(PID_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning(f"Unable to write PID file: {e}")


def remove_pid_file() -> None:
    try:
        if os.path.exists(PID_FILE_PATH):
            os.remove(PID_FILE_PATH)
    except Exception as e:
        logger.warning(f"Unable to remove PID file: {e}")


def get_bound_port() -> int:
    env_port = os.environ.get("AGENTSOCKET_PORT") or os.environ.get("PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
    if "--port" in sys.argv:
        try:
            idx = sys.argv.index("--port")
            if idx + 1 < len(sys.argv):
                return int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            pass
    return 8000


def write_port_file(port: int | None = None) -> None:
    try:
        if port is None:
            port = get_bound_port()
        with open(PORT_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(str(port))
    except Exception as e:
        logger.warning(f"Unable to write port file: {e}")


def remove_port_file() -> None:
    try:
        if os.path.exists(PORT_FILE_PATH):
            os.remove(PORT_FILE_PATH)
    except Exception as e:
        logger.warning(f"Unable to remove port file: {e}")


async def idle_watchdog_loop() -> None:
    logger.info(f"Auto-idle watchdog started (timeout: {IDLE_TIMEOUT_SECONDS}s / {IDLE_TIMEOUT_SECONDS/60:.1f}m).")
    try:
        while True:
            await asyncio.sleep(10)
            # Check for inactive tab group sessions (>10 minutes)
            session_manager.check_inactivity(inactivity_threshold_seconds=600.0)

            idle_duration = time.time() - state.last_activity_time
            if idle_duration >= IDLE_TIMEOUT_SECONDS:
                logger.info(f"Idle duration {idle_duration:.1f}s exceeded limit of {IDLE_TIMEOUT_SECONDS}s.")
                logger.info("Initiating graceful shutdown of gateway server...")
                remove_pid_file()
                remove_port_file()
                try:
                    signal.raise_signal(signal.SIGINT)
                except Exception:
                    loop = asyncio.get_running_loop()
                    loop.stop()
                break
    except asyncio.CancelledError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    write_pid_file()
    write_port_file()
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
    remove_port_file()
    logger.info("Server gateway shutdown completed cleanly.")


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
def read_root() -> dict[str, Any]:
    state.record_activity()
    return {
        "status": "AgentSocket Server is Live",
        "extension_connected": state.extension_ws is not None,
        "human_in_control": state.human_in_control,
        "idle_seconds_remaining": max(0.0, IDLE_TIMEOUT_SECONDS - (time.time() - state.last_activity_time)),
    }


@app.get("/status")
def get_status() -> dict[str, Any]:
    state.record_activity()
    return {
        "status": "AgentSocket Server is Live",
        "extension_connected": state.extension_ws is not None,
        "human_in_control": state.human_in_control,
        "last_intervention_notes": state.last_intervention_notes,
        "idle_seconds_remaining": max(0.0, IDLE_TIMEOUT_SECONDS - (time.time() - state.last_activity_time)),
    }


@app.post("/progress")
async def update_progress(payload: ProgressPayload) -> dict[str, Any]:
    if payload.step_total == 0:
        progress_percent = 100
        total = 0
        current = payload.step_current
    else:
        total = payload.step_total
        current = max(0, min(payload.step_current, total))
        progress_percent = int((current / total) * 100)

    logger.debug(
        f"Progress Update: '{payload.session_title}' [{current}/{total}] ({progress_percent}%) - {payload.step_title or ''}"
    )

    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.UPDATE_PROGRESS.value,
                "session_title": payload.session_title,
                "step_current": payload.step_current,
                "step_total": payload.step_total,
                "progress_percent": progress_percent,
                "step_title": payload.step_title,
            }))
            return {
                "status": "success",
                "progress_percent": progress_percent,
                "step_current": payload.step_current,
                "step_total": payload.step_total,
                "step_title": payload.step_title,
                "session_title": payload.session_title,
            }
        except Exception as e:
            logger.warning(f"Error forwarding progress to extension: {e}")
            return {
                "status": "success",
                "progress_percent": progress_percent,
                "step_current": payload.step_current,
                "step_total": payload.step_total,
                "step_title": payload.step_title,
                "warning": f"Failed to forward progress frame: {e}",
            }
    else:
        logger.debug("Extension is not connected. Progress recorded locally.")
        return {
            "status": "success",
            "progress_percent": progress_percent,
            "step_current": payload.step_current,
            "step_total": payload.step_total,
            "step_title": payload.step_title,
            "warning": "Extension WebSocket offline - progress logged locally",
        }



@app.get("/history")
def get_history(query: str = "", month: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    state.record_activity()
    return session_manager.query_history(query_hint=query, month=month, limit=limit)


@app.get("/session/details")
def get_session_details(path: str) -> dict[str, Any]:
    state.record_activity()
    return session_manager.get_session_details(session_path=path)


@app.get("/session/artifact")
def get_session_artifact(path: str, name: str) -> dict[str, Any] | str:
    state.record_activity()
    return session_manager.get_session_artifact(session_path=path, artifact_name=name)


@app.get("/session/document")
def get_session_document(path: str) -> dict[str, Any]:
    state.record_activity()
    doc = session_manager.generate_session_document(session_dir_or_path=path)
    return {"status": "success", "session_path": path, "document_markdown": doc}


@app.get("/session/thread")
def get_session_thread(path: str) -> dict[str, Any]:
    state.record_activity()
    thread_md = session_manager.generate_thread_document(session_dir_or_path=path)
    return {"status": "success", "session_path": path, "thread_markdown": thread_md}


@app.get("/subskills")
def list_subskills(query: str = "", tags: str | None = None) -> list[dict[str, Any]]:
    state.record_activity()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return session_manager.list_subskills(query=query, tags=tag_list)


@app.get("/subskills/{name}")
def get_subskill(name: str) -> dict[str, Any]:
    state.record_activity()
    res = session_manager.get_subskill(name=name)
    if not res:
        return {"status": "error", "message": f"Subskill '{name}' not found."}
    return {"status": "success", "data": res}


@app.post("/subskills/borrow")
def borrow_subskill(payload: BorrowSubskillPayload) -> dict[str, Any]:
    state.record_activity()
    return session_manager.borrow_subskill(
        name=payload.name,
        target_session_id_or_title_or_path=payload.session_title,
        tab_group_id=payload.tab_group_id,
        input_file_path=payload.input_file_path,
    )


@app.post("/subskills/register")
def register_subskill(payload: RegisterSubskillPayload) -> dict[str, Any]:
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


# ============================================================================
# Central Adhocs Vault & Execution Endpoints (Spec 18)
# ============================================================================
@app.get("/adhocs")
def list_adhocs() -> list[dict[str, Any]]:
    state.record_activity()
    return session_manager.list_adhocs()


@app.post("/adhocs/promote")
def promote_adhoc(payload: PromoteAdhocPayload) -> dict[str, Any]:
    state.record_activity()
    return session_manager.promote_adhoc(
        session_path=payload.session_path,
        tool_name=payload.tool_name,
        target=payload.target,
        subskill_name=payload.subskill_name,
    )


@app.get("/adhocs/resolve")
def resolve_adhoc(tool_name: str, session_path: str | None = None) -> dict[str, Any]:
    state.record_activity()
    return session_manager.resolve_adhoc(tool_name=tool_name, session_dir_or_path=session_path)


@app.post("/adhocs/run")
def run_adhoc(payload: RunAdhocPayload) -> dict[str, Any]:
    state.record_activity()
    return session_manager.run_adhoc(
        tool_name=payload.tool_name,
        session_dir_or_path=payload.session_path,
        args=payload.args,
    )


@app.websocket("/ws/extension")
async def extension_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    state.extension_ws = websocket
    state.record_activity()
    logger.info("Chrome Extension plugged in cleanly via WebSocket.")
    try:
        while True:
            raw_message = await websocket.receive_text()
            state.record_activity()
            message = json.loads(raw_message)
            msg_type = message.get("type")

            if msg_type == WSMessageType.PING.value or msg_type == "ping":
                continue

            if msg_type == WSMessageType.STATE_CHANGE.value or msg_type == "state_change":
                if message.get("agent_name"):
                    state.agent_name = message.get("agent_name")
                if message.get("group_color"):
                    state.group_color = message.get("group_color")
                new_state = message.get("human_in_control", False)
                if not new_state and state.human_in_control:
                    logger.info("Extension sent release state. Release must go through the /human_release endpoint.")
                else:
                    state.human_in_control = new_state
                    if state.human_in_control:
                        state.takeover_start_time = time.time()
                        if message.get("notes"):
                            state.last_intervention_notes = message.get("notes")
                    logger.info(f"State Sync -> Human In Control: {state.human_in_control}")

            elif msg_type == WSMessageType.COMMAND_RESPONSE.value or msg_type == "command_response":
                cmd_id = message.get("command_id")
                if cmd_id in state.pending_responses:
                    state.pending_responses[cmd_id].set_result(message.get("payload"))

    except WebSocketDisconnect:
        logger.info("Chrome Extension unplugged from AgentSocket bridge.")
        session_manager.handle_disconnect()
    finally:
        state.extension_ws = None
        state.record_activity()


@app.post("/execute")
async def execute_to_extension(command: AgentActionPayload) -> dict[str, Any]:
    state.record_activity()
    t_start = time.time()
    session_title = command.session_title.strip()

    # Non-blocking check: immediately report lock if human is currently in control
    if state.human_in_control:
        return {
            "status": ResponseStatus.HUMAN_LOCKED.value,
            "message": "Human operator is currently in control of the browser session.",
            "last_intervention_notes": state.last_intervention_notes,
            "instructions": "Wait for human operator to click 'Release Control' or check GET /status.",
        }

    # Check if we should inject human notes context from a recent release
    if state.last_intervention_notes:
        injected_context = f"[HUMAN INTERVENTION OVERRIDE LOG]: {state.last_intervention_notes}"
        state.last_intervention_notes = None
        return {
            "status": ResponseStatus.RESUMED_CONTEXT.value,
            "message": injected_context,
            "instructions": "Human operator handoff caught. Adapt steps using log data.",
        }

    # PRIVACY TRIGGER CHECK
    sensitive_keywords = [
        "credential", "password", "payment", "checkout", "bank", "dashboard",
        "scrape", "scraping", "login", "signin", "signup", "creditcard", "cvv",
        "card_number", "personal", "account", "stripe", "paypal",
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
                "notes": f"Security Abort: {reason}",
            }))
        logger.warning(f"Security Abort: Outbound requests locked. {reason}")

        active_sess = session_manager.get_active_session_by_title(session_title)
        if active_sess:
            session_manager.log_event(
                tab_group_id=active_sess.tab_group_id,
                event_type=SessionEventType.SECURITY_ABORT,
                title="Security Abort Triggered",
                start_time=t_start,
                end_time=time.time(),
                payload={"reason": reason, "target_data": "[REDACTED SENSITIVE DATA]"},
            )

        return {
            "status": ResponseStatus.SECURITY_ABORT.value,
            "message": f"Sensitive scope detected. Outbound requests locked. Human intervention required. Reason: {reason}",
        }

    if not state.extension_ws:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": "Extension is offline.",
            "error": {"code": ErrorCode.EXTENSION_OFFLINE.value, "message": "Chrome extension is not plugged into WebSocket gateway."},
        }

    cmd_id = command.id
    loop = asyncio.get_running_loop()
    state.pending_responses[cmd_id] = loop.create_future()

    await state.extension_ws.send_text(json.dumps({
        "type": WSMessageType.EXECUTE_ACTION.value,
        "id": command.id,
        "action_type": command.action_type.value if hasattr(command.action_type, "value") else str(command.action_type),
        "target_data": command.target_data,
        "requires_privacy_check": command.requires_privacy_check,
        "session_title": command.session_title,
    }))

    try:
        result = await asyncio.wait_for(state.pending_responses[cmd_id], timeout=30.0)
        t_end = time.time()

        # If extension returned an error (e.g. user denied authorization), do not persist or store session
        if isinstance(result, dict) and result.get("status") == "error":
            error_data = result.get("error")
            err_code = error_data.get("code", ErrorCode.INTERNAL_ERROR.value) if isinstance(error_data, dict) else ErrorCode.INTERNAL_ERROR.value
            err_msg = error_data.get("message", result.get("message", "Browser action failed.")) if isinstance(error_data, dict) else result.get("message", "Browser action failed.")
            return {
                "status": ResponseStatus.ERROR.value,
                "message": err_msg,
                "error": {"code": err_code, "message": err_msg},
            }

        tab_group_id = None
        tab_id = None
        if isinstance(result, dict):
            tab_group_id = result.get("groupId")
            tab_id = result.get("tabId")

        if tab_group_id is None:
            existing = session_manager.get_active_session_by_title(session_title)
            if existing:
                tab_group_id = existing.tab_group_id
            else:
                tab_group_id = 1

        agent_name = (
            result.get("agent_name")
            if isinstance(result, dict) and result.get("agent_name")
            else (state.agent_name or "Agent")
        )
        group_color = (
            result.get("group_color")
            if isinstance(result, dict) and result.get("group_color")
            else (state.group_color or "purple")
        )

        session = session_manager.get_or_create_session(
            tab_group_id=tab_group_id,
            tab_group_name=session_title,
            agent_name=agent_name,
            group_color=group_color,
        )
        session.agent_name = agent_name
        session.group_color = group_color

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
                payload={"target_url": command.target_data, "result": result},
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
                payload={"script": command.target_data, "output": result.get("output") if isinstance(result, dict) else result, "result": result},
            )
        elif act_val == ActionType.TASK_COMPLETE.value:
            clean_title = session_title.replace("✅", "").strip()
            completed_title = f"✅ {clean_title}"
            session_manager.log_event(
                tab_group_id=tab_group_id,
                event_type=SessionEventType.TASK_COMPLETE,
                title=f"Task Completed: {completed_title}",
                start_time=t_start,
                end_time=t_end,
                tab_id=tab_id,
                tab_group_id_val=tab_group_id,
                payload={"result": result},
            )
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
                payload={"error": ErrorCode.EXECUTION_TIMEOUT.value, "message": "Command execution exceeded 30.0s limit."},
            )
        return {
            "status": ResponseStatus.ERROR.value,
            "message": "Execution engine frame timed out.",
            "error": {"code": ErrorCode.EXECUTION_TIMEOUT.value, "message": "Command execution exceeded 30.0s limit."},
        }
    finally:
        state.pending_responses.pop(cmd_id, None)


@app.post("/human_release")
async def human_release(payload: ReleasePayload) -> dict[str, Any]:
    state.record_activity()
    state.human_in_control = False
    state.last_intervention_notes = payload.notes if payload.notes else "Released by human operator."

    t_now = time.time()
    takeover_dur_ms = 0.0
    if state.takeover_start_time:
        takeover_dur_ms = max(0.0, round((t_now - state.takeover_start_time) * 1000.0, 2))
        state.takeover_start_time = None

    logger.info(f"Human Release Endpoint -> Human In Control: {state.human_in_control}, Notes: {state.last_intervention_notes}, Duration: {takeover_dur_ms}ms")

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
            },
        )

    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.STATE_SYNC.value,
                "human_in_control": False,
                "notes": state.last_intervention_notes,
            }))
        except Exception as e:
            logger.warning(f"Error sending state_sync on release: {e}")

    return {"status": ResponseStatus.SUCCESS.value, "human_in_control": False}


@app.post("/stop")
async def stop_active_task() -> dict[str, Any]:
    state.record_activity()
    state.human_in_control = False
    state.last_intervention_notes = None
    state.takeover_start_time = None

    for gid in list(session_manager.active_sessions.keys()):
        session_manager.finalize_session(
            tab_group_id=gid,
            status=SessionStatus.STOPPED,
            end_reason="user_stopped",
        )

    for cmd_id, future in list(state.pending_responses.items()):
        if not future.done():
            future.set_result({"status": "aborted", "message": "Task terminated by human operator."})
    state.pending_responses.clear()

    logger.info("Task aborted by user takeover stop command.")

    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.STATE_SYNC.value,
                "human_in_control": False,
                "notes": "Task terminated.",
            }))
        except Exception as e:
            logger.warning(f"Error sending state_sync on stop: {e}")

    return {"status": ResponseStatus.SUCCESS.value}
