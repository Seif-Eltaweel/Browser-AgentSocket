import asyncio
import json
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configurable idle timeout (default: 20 minutes = 1200 seconds)
IDLE_TIMEOUT_SECONDS = float(os.environ.get("BRO_IDLE_TIMEOUT", "1200"))
PID_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".bro_pid")

class AgentActionPayload(BaseModel):
    id: str
    action_type: Literal["navigate", "execute_js", "task_complete"]
    target_data: str
    requires_privacy_check: bool
    session_title: str | None = None
    group_color: str | None = None

class ReleasePayload(BaseModel):
    notes: str | None = None

class SystemState:
    def __init__(self):
        self.extension_ws: WebSocket | None = None
        self.human_in_control: bool = False
        self.last_intervention_notes: str | None = None
        self.pending_responses: dict[str, asyncio.Future] = {}
        self.last_activity_time: float = time.time()
        self.watchdog_task: asyncio.Task | None = None

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
            idle_duration = time.time() - state.last_activity_time
            if idle_duration >= IDLE_TIMEOUT_SECONDS:
                print(f"\n[WATCHDOG] Idle duration {idle_duration:.1f}s exceeded limit of {IDLE_TIMEOUT_SECONDS}s.")
                print("[WATCHDOG] Cleanly shutting down background gateway process...\n")
                remove_pid_file()
                # Schedule immediate process termination
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
    remove_pid_file()

app = FastAPI(title="Agent Bro Hands Server Gateway", lifespan=lifespan)

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
        "status": "Agent Bro Hands Server is Live", 
        "extension_connected": state.extension_ws is not None,
        "human_in_control": state.human_in_control,
        "idle_seconds_remaining": max(0.0, IDLE_TIMEOUT_SECONDS - (time.time() - state.last_activity_time))
    }

@app.get("/status")
def get_status():
    state.record_activity()
    return {
        "status": "Agent Bro Hands Server is Live",
        "extension_connected": state.extension_ws is not None,
        "human_in_control": state.human_in_control,
        "last_intervention_notes": state.last_intervention_notes,
        "idle_seconds_remaining": max(0.0, IDLE_TIMEOUT_SECONDS - (time.time() - state.last_activity_time))
    }

@app.websocket("/ws/extension")
async def extension_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.extension_ws = websocket
    state.record_activity()
    print("\n[SUCCESS] ==========================================")
    print("[Bridge] Chrome Extension pipeline linked cleanly via WebSocket.")
    print("====================================================\n")
    try:
        while True:
            raw_message = await websocket.receive_text()
            state.record_activity()
            message = json.loads(raw_message)
            msg_type = message.get("type")
            
            if msg_type == "ping":
                continue
            
            if msg_type == "state_change":
                new_state = message.get("human_in_control", False)
                if not new_state and state.human_in_control:
                    print("[Bridge] Info: Extension sent release state. Release must go through the /human_release endpoint.")
                else:
                    state.human_in_control = new_state
                    if state.human_in_control and message.get("notes"):
                        state.last_intervention_notes = message.get("notes")
                    print(f"[Bridge] State Sync -> Human In Control: {state.human_in_control}")
            
            elif msg_type == "command_response":
                cmd_id = message.get("command_id")
                if cmd_id in state.pending_responses:
                    state.pending_responses[cmd_id].set_result(message.get("payload"))
                    
    except WebSocketDisconnect:
        print("\n[DISCONNECT] Chrome Extension detached from bridge channel.\n")
    finally:
        state.extension_ws = None
        state.record_activity()

@app.post("/execute")
async def execute_to_extension(command: AgentActionPayload):
    state.record_activity()
    
    # Non-blocking check: immediately report lock if human is currently in control
    if state.human_in_control:
        return {
            "status": "human_locked",
            "message": "Human operator is currently in control of the browser session.",
            "last_intervention_notes": state.last_intervention_notes,
            "instructions": "Wait for human operator to click 'Release Control' or check GET /status."
        }

    # Check if we should inject human notes context from a recent release
    if state.last_intervention_notes:
        injected_context = f"[HUMAN INTERVENTION OVERRIDE LOG]: {state.last_intervention_notes}"
        state.last_intervention_notes = None  
        return {
            "status": "resumed_context",
            "message": injected_context,
            "instructions": "Human operator handoff caught. Adapt steps using log data."
        }

    # PRIVACY TRIGGER
    sensitive_keywords = [
        "credential", "password", "payment", "checkout", "bank", "dashboard", 
        "scrape", "scraping", "login", "signin", "signup", "creditcard", "cvv", 
        "card_number", "personal", "account", "checkout", "stripe", "paypal"
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
        if state.extension_ws:
            await state.extension_ws.send_text(json.dumps({
                "type": "state_sync",
                "human_in_control": True,
                "notes": f"Security Abort: {reason}"
            }))
        print(f"[SECURITY ABORT] Outbound requests locked. {reason}")
        return {
            "status": "security_abort",
            "message": f"Sensitive scope detected. Outbound requests locked. Human intervention required. Reason: {reason}"
        }

    if not state.extension_ws:
        return {"status": "error", "message": "Extension is offline."}

    cmd_id = command.id
    loop = asyncio.get_running_loop()
    state.pending_responses[cmd_id] = loop.create_future()

    # Enforce AgentActionPayload schema inside WS frame
    await state.extension_ws.send_text(json.dumps({
        "type": "execute_action",
        "id": command.id,
        "action_type": command.action_type,
        "target_data": command.target_data,
        "requires_privacy_check": command.requires_privacy_check,
        "session_title": command.session_title,
        "group_color": command.group_color
    }))

    try:
        result = await asyncio.wait_for(state.pending_responses[cmd_id], timeout=30.0)
        return {"status": "success", "result": result}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "Execution engine frame timed out."}
    finally:
        state.pending_responses.pop(cmd_id, None)

@app.post("/human_release")
async def human_release(payload: ReleasePayload):
    state.record_activity()
    state.human_in_control = False
    state.last_intervention_notes = payload.notes if payload.notes else "Released by human operator."
    print(f"[Bridge] Human Release Endpoint -> Human In Control: {state.human_in_control}, Notes: {state.last_intervention_notes}")
    
    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": "state_sync",
                "human_in_control": False,
                "notes": state.last_intervention_notes
            }))
        except Exception as e:
            print(f"[Bridge] Error sending state_sync on release: {e}")
            
    return {"status": "success", "human_in_control": False}

@app.post("/stop")
async def stop_active_task():
    state.record_activity()
    state.human_in_control = False
    state.last_intervention_notes = None
    # Cancel all pending future responses
    for cmd_id, future in list(state.pending_responses.items()):
        if not future.done():
            future.set_result({"status": "aborted", "message": "Task terminated by human operator."})
    print("[Bridge] Task aborted by user takeover stop command.")
    
    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": "state_sync",
                "human_in_control": False,
                "notes": "Task terminated."
            }))
        except Exception as e:
            print(f"[Bridge] Error sending state_sync on stop: {e}")

    return {"status": "success"}
