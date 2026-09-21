"""
AgentSocket - Server Gateway Strip
FastAPI WebSocket and HTTP Hub connecting AI Agent frameworks with the Chrome Extension.
"""

from __future__ import annotations
import asyncio
import json
import os
import platform
import secrets
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    ObserveRequest,
    ObserveResponse,
    ActRequest,
    ActResponse,
    SetIntentRequest,
    ScreenshotRequest,
    TaskCompleteRequest,
    MilestoneStatus,
    PlanMilestone,
    PlanPayload,
    UpdateMilestonePayload,
)
from server.config import (
    get_pid_file_path,
    get_port_file_path,
    get_token_file_path,
    get_db_path,
    get_default_logs_dir,
)
from server.session import session_manager

# Configurable idle timeout (default: 20 minutes = 1200 seconds)
IDLE_TIMEOUT_SECONDS = float(os.environ.get("SOCKET_IDLE_TIMEOUT", "1200"))
PID_FILE_PATH = str(get_pid_file_path())
PORT_FILE_PATH = str(get_port_file_path())
TOKEN_FILE_PATH = str(get_token_file_path())
AUTH_TOKEN_HEADER = "X-AgentSocket-Token"
AUTH_TOKEN_PARAM = "token"


def write_token_file(token: str) -> None:
    token_file = str(get_token_file_path())
    try:
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(token)
    except Exception as e:
        logger.warning(f"Unable to write token file: {e}")


def remove_token_file() -> None:
    token_file = str(get_token_file_path())
    try:
        if os.path.exists(token_file):
            os.remove(token_file)
    except Exception as e:
        logger.warning(f"Unable to remove token file: {e}")


def get_or_generate_token() -> str:
    env_token = os.environ.get("AGENTSOCKET_TOKEN")
    token_file = str(get_token_file_path())
    if env_token:
        write_token_file(env_token)
        return env_token
    if os.path.exists(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    token = secrets.token_hex(32)
    write_token_file(token)
    return token


class TabSessionState:
    """
    Scoped session state per Chrome Tab Group (Spec 23 Flaw 3 Fix).
    Isolates takeover status, intervention notes, active tab id, and correlation futures.
    """
    def __init__(self, tab_group_id: int) -> None:
        self.tab_group_id: int = tab_group_id
        self.human_in_control: bool = False
        self.last_intervention_notes: str | None = None
        self.active_tab_id: int | None = None
        self.pending_responses: dict[str, asyncio.Future] = {}
        self.takeover_start_time: float | None = None


class PendingResponsesDict(dict):
    """
    Dictionary proxy for pending correlation futures ensuring backward compatibility with state.pending_responses.
    Clearing state.pending_responses clears all tab session pending futures as well.
    """
    def __init__(self, system_state: SystemState, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._system_state = system_state

    def clear(self) -> None:
        super().clear()
        if hasattr(self, "_system_state") and self._system_state:
            for s in list(self._system_state.tab_sessions.values()):
                s.pending_responses.clear()


class SystemState:
    def __init__(self) -> None:
        self.tab_sessions: dict[int, TabSessionState] = {}
        self.extension_ws: WebSocket | None = None
        self.pending_responses: PendingResponsesDict = PendingResponsesDict(self)
        self.last_activity_time: float = time.time()
        self.watchdog_task: asyncio.Task | None = None
        self.agent_name: str | None = None
        self.group_color: str | None = None
        self.server_token: str = get_or_generate_token()
        self.session_permissions: dict[str, dict[str, bool]] = {}
        self.global_permissions: dict[str, bool] = {"enable_subskills": True, "enable_vision": False}

    def get_session(self, tab_group_id: int | None = None) -> TabSessionState:
        gid = tab_group_id if tab_group_id is not None else 0
        if gid not in self.tab_sessions:
            self.tab_sessions[gid] = TabSessionState(gid)
        return self.tab_sessions[gid]

    @property
    def human_in_control(self) -> bool:
        if 0 in self.tab_sessions and self.tab_sessions[0].human_in_control:
            return True
        return any(s.human_in_control for s in self.tab_sessions.values())

    @human_in_control.setter
    def human_in_control(self, val: bool) -> None:
        self.get_session(0).human_in_control = val

    @property
    def last_intervention_notes(self) -> str | None:
        return self.get_session(0).last_intervention_notes

    @last_intervention_notes.setter
    def last_intervention_notes(self, val: str | None) -> None:
        self.get_session(0).last_intervention_notes = val

    @property
    def takeover_start_time(self) -> float | None:
        return self.get_session(0).takeover_start_time

    @takeover_start_time.setter
    def takeover_start_time(self, val: float | None) -> None:
        self.get_session(0).takeover_start_time = val

    def find_pending_future(self, request_id: str) -> asyncio.Future | None:
        if not request_id:
            return None
        for session in self.tab_sessions.values():
            if request_id in session.pending_responses:
                return session.pending_responses[request_id]
        if request_id in self.pending_responses:
            return self.pending_responses[request_id]
        return None

    def pop_pending_future(self, request_id: str) -> asyncio.Future | None:
        if not request_id:
            return None
        fut = None
        for session in self.tab_sessions.values():
            if request_id in session.pending_responses:
                fut = session.pending_responses.pop(request_id, None) or fut
        if request_id in self.pending_responses:
            fut = self.pending_responses.pop(request_id, None) or fut
        return fut

    def record_activity(self) -> None:
        self.last_activity_time = time.time()


state = SystemState()


def write_pid_file() -> None:
    pid_file = str(get_pid_file_path())
    try:
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning(f"Unable to write PID file: {e}")


def remove_pid_file() -> None:
    pid_file = str(get_pid_file_path())
    try:
        if os.path.exists(pid_file):
            os.remove(pid_file)
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
    port_file = str(get_port_file_path())
    try:
        if port is None:
            port = get_bound_port()
        with open(port_file, "w", encoding="utf-8") as f:
            f.write(str(port))
    except Exception as e:
        logger.warning(f"Unable to write port file: {e}")


def remove_port_file() -> None:
    port_file = str(get_port_file_path())
    try:
        if os.path.exists(port_file):
            os.remove(port_file)
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
    if not state.server_token:
        state.server_token = get_or_generate_token()
    write_token_file(state.server_token)
    state.record_activity()
    state.watchdog_task = asyncio.create_task(idle_watchdog_loop())

    yield

    # Shutdown
    if state.watchdog_task and not state.watchdog_task.done():
        state.watchdog_task.cancel()

    # Abort pending responses
    for session in state.tab_sessions.values():
        for cmd_id, future in list(session.pending_responses.items()):
            if not future.done():
                future.set_result({"status": "aborted", "message": "Server shutting down."})
        session.pending_responses.clear()
    for cmd_id, future in list(state.pending_responses.items()):
        if not future.done():
            future.set_result({"status": "aborted", "message": "Server shutting down."})
    state.pending_responses.clear()

    # Close any active sessions
    session_manager.handle_disconnect()

    remove_pid_file()
    remove_port_file()
    remove_token_file()
    logger.info("Server gateway shutdown completed cleanly.")


app = FastAPI(title="AgentSocket Server Gateway", lifespan=lifespan)

# Ephemeral Token HTTP Authentication Middleware (Spec 22 & Spec 30)
@app.middleware("http")
async def verify_gateway_token(request: Request, call_next):
    # CORS preflight requests must bypass auth check
    if request.method == "OPTIONS":
        return await call_next(request)

    client_host = request.client.host if request.client else ""
    is_loopback = client_host in ["127.0.0.1", "localhost", "::1", "testclient"]

    # Public loopback endpoints bypass
    if request.url.path in ["/auth.html", "/api/token", "/health"] and is_loopback:
        return await call_next(request)

    origin = request.headers.get("origin") or ""
    is_extension = origin.startswith("chrome-extension://")

    token = request.headers.get("x-agentsocket-token") or request.query_params.get("token")
    has_valid_token = bool(state.server_token and token == state.server_token)

    if not (has_valid_token or (is_extension and is_loopback)):
        return JSONResponse(
            status_code=401,
            content={
                "status": "error",
                "error": {
                    "code": ErrorCode.UNAUTHORIZED.value,
                    "message": "Invalid or missing gateway token. Provide X-AgentSocket-Token header or ?token= query parameter.",
                },
            },
        )

    return await call_next(request)


ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "chrome-extension://*",
]

# Strict CORS Whitelisting (Spec 22)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^(http://(127\.0\.0\.1|localhost)(:\d+)?|chrome-extension://.*)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Spec 35: Token Endpoint Transport Hardening & CORS Exclusion Middleware
# Registered after CORSMiddleware so it executes first on incoming requests (outermost wrapper)
@app.middleware("http")
async def secure_token_endpoint_middleware(request: Request, call_next):
    if request.url.path == "/api/token":
        origin = request.headers.get("origin")
        sec_fetch_site = request.headers.get("sec-fetch-site")

        # Disallow cross-origin browser fetches to /api/token
        if sec_fetch_site in ("cross-site", "same-site"):
            return JSONResponse(status_code=403, content={"error": "Cross-origin access forbidden"})

        if origin and not origin.startswith("chrome-extension://"):
            return JSONResponse(status_code=403, content={"error": "Origin access forbidden"})

    return await call_next(request)


@app.get("/")
def read_root(tab_group_id: int | None = None) -> dict[str, Any]:
    state.record_activity()
    session = state.get_session(tab_group_id)
    return {
        "status": "AgentSocket Server is Live",
        "extension_connected": state.extension_ws is not None,
        "human_in_control": session.human_in_control,
        "idle_seconds_remaining": max(0.0, IDLE_TIMEOUT_SECONDS - (time.time() - state.last_activity_time)),
    }


@app.get("/status")
def get_status(tab_group_id: int | None = None) -> dict[str, Any]:
    state.record_activity()
    session = state.get_session(tab_group_id)
    return {
        "status": "AgentSocket Server is Live",
        "extension_connected": state.extension_ws is not None,
        "human_in_control": session.human_in_control,
        "last_intervention_notes": session.last_intervention_notes,
        "tab_group_id": session.tab_group_id,
        "idle_seconds_remaining": max(0.0, IDLE_TIMEOUT_SECONDS - (time.time() - state.last_activity_time)),
    }


@app.get("/api/token")
def get_ephemeral_token(request: Request) -> dict[str, str]:
    """Spec 30 & Spec 35: Local token bootstrap endpoint for local browser extensions and tools."""
    client_host = request.client.host if request.client else ""
    if client_host not in ["127.0.0.1", "localhost", "::1", "testclient"]:
        return JSONResponse(status_code=403, content={"error": "Forbidden: localhost only"})

    origin = request.headers.get("origin")
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site in ("cross-site", "same-site"):
        return JSONResponse(status_code=403, content={"error": "Cross-origin access forbidden"})
    if origin and not origin.startswith("chrome-extension://"):
        return JSONResponse(status_code=403, content={"error": "Origin access forbidden"})

    return {"token": state.server_token or ""}


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


# ============================================================================
# Strategic Plan & Milestones Endpoints (Spec 32)
# ============================================================================

@app.post("/plan")
async def register_plan_endpoint(payload: PlanPayload) -> dict[str, Any]:
    state.record_activity()
    plan_res = session_manager.set_session_plan(
        session_title=payload.session_title,
        milestones=payload.milestones,
        active_index=payload.active_milestone_index or 1,
    )

    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.SET_PLAN.value,
                "session_title": payload.session_title,
                "milestones": plan_res["milestones"],
                "active_index": plan_res["active_index"],
                "progress_percent": plan_res["progress_percent"],
            }))
        except Exception as e:
            logger.warning(f"Error forwarding set_plan frame to extension: {e}")

    return {
        "status": "success",
        "session_title": payload.session_title,
        "total_milestones": plan_res["total_milestones"],
        "active_index": plan_res["active_index"],
        "progress_percent": plan_res["progress_percent"],
        "milestones": plan_res["milestones"],
    }


@app.post("/plan/milestone")
async def update_milestone_endpoint(payload: UpdateMilestonePayload) -> dict[str, Any]:
    state.record_activity()
    milestone_res = session_manager.update_session_milestone(
        session_title=payload.session_title,
        milestone_index=payload.milestone_index,
        milestone_title=payload.milestone_title,
        action_detail=payload.action_detail,
        status=payload.status,
    )

    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.SET_MILESTONE.value,
                "session_title": payload.session_title,
                "milestone_index": milestone_res["milestone_index"],
                "milestone_title": milestone_res["milestone_title"],
                "current_action": milestone_res["current_action"],
                "progress_percent": milestone_res["progress_percent"],
            }))
        except Exception as e:
            logger.warning(f"Error forwarding set_milestone frame to extension: {e}")

    return milestone_res



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
    perms = state.session_permissions.get(payload.session_title, state.global_permissions)
    if not perms.get("enable_subskills", True):
        return {
            "status": "denied",
            "error": {"code": "PERMISSION_DENIED", "message": "Subskills and SOP playbooks disabled by user for this session."},
            "message": "Subskills and SOP playbooks disabled by user for this session."
        }
    return session_manager.borrow_subskill(
        name=payload.name,
        target_session_id_or_title_or_path=payload.session_title,
        tab_group_id=payload.tab_group_id,
        input_file_path=payload.input_file_path,
    )


@app.post("/subskills/register")
def register_subskill(payload: RegisterSubskillPayload) -> dict[str, Any]:
    state.record_activity()
    if not state.global_permissions.get("enable_subskills", True):
        return {
            "status": "denied",
            "error": {"code": "PERMISSION_DENIED", "message": "Subskills and SOP playbooks disabled by user."},
            "message": "Subskills and SOP playbooks disabled by user."
        }
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
    token = websocket.headers.get("x-agentsocket-token") or websocket.query_params.get("token")
    has_valid_token = bool(state.server_token and token == state.server_token)

    # Invariant: Origin header alone NEVER bypasses authentication (Spec 35)
    if not has_valid_token:
        logger.warning(
            "Rejecting unauthenticated WebSocket connection attempt on /ws/extension (token invalid or missing)."
        )
        await websocket.close(code=1008, reason="Unauthorized: invalid or missing gateway token")
        return

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

            if msg_type in (WSMessageType.AUTH_RESPONSE.value, "auth_response", "AUTH_RESPONSE"):
                auth_status = message.get("status")
                perms = message.get("permissions") or {}
                tab_group_name = message.get("tab_group_name") or message.get("session_title")
                if tab_group_name:
                    state.session_permissions[tab_group_name] = perms
                state.global_permissions = perms
                logger.info(f"Extension Consent Handshake -> status: {auth_status}, permissions: {perms}")
                continue

            if msg_type == WSMessageType.STATE_CHANGE.value or msg_type == "state_change":
                if message.get("agent_name"):
                    state.agent_name = message.get("agent_name")
                if message.get("group_color"):
                    state.group_color = message.get("group_color")
                new_state = bool(message.get("human_in_control", False))
                notes = message.get("notes") or ""
                gid = message.get("tab_group_id") or message.get("groupId")
                
                target_sessions = [state.get_session(gid)] if gid is not None and int(gid) > 0 else list(state.tab_sessions.values())
                if 0 not in state.tab_sessions:
                    target_sessions.append(state.get_session(0))

                for session in target_sessions:
                    session.human_in_control = new_state
                    if new_state:
                        session.takeover_start_time = time.time()
                        if notes:
                            session.last_intervention_notes = notes
                    else:
                        if notes:
                            session.last_intervention_notes = notes
                    logger.info(f"State Sync [Group {session.tab_group_id}] -> Human In Control: {session.human_in_control}")

            elif msg_type in (
                WSMessageType.COMMAND_RESPONSE.value,
                "command_response",
                WSMessageType.OBSERVE_RESPONSE.value,
                "observe_response",
                WSMessageType.ACT_RESPONSE.value,
                "act_response",
            ):
                cmd_id = message.get("request_id") or message.get("command_id") or message.get("id")
                fut = state.find_pending_future(cmd_id)
                logger.info(f"Incoming WS response frame: type={msg_type}, id={cmd_id}, fut_found={fut is not None}")
                if fut and not fut.done():
                    fut.set_result(message.get("payload") if "payload" in message else message)

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

    tab_group_id = command.tab_group_id
    if tab_group_id is None:
        active_sess = session_manager.get_active_session_by_title(session_title)
        if active_sess:
            tab_group_id = active_sess.tab_group_id
        else:
            tab_group_id = 0

    session = state.get_session(tab_group_id)

    # Non-blocking check: immediately report lock if human is currently in control for this tab group
    if session.human_in_control:
        return {
            "status": ResponseStatus.HUMAN_LOCKED.value,
            "message": "Human operator is currently in control of the browser session.",
            "last_intervention_notes": session.last_intervention_notes,
            "instructions": "Wait for human operator to click 'Release Control' or check GET /status.",
        }

    # Flaw 4 Fix: Non-dropping execution!
    # Check if we should inject human notes context from a recent release without dropping command
    intervention_notes_meta = None
    if session.last_intervention_notes:
        intervention_notes_meta = session.last_intervention_notes
        session.last_intervention_notes = None

    # VISION PERMISSION ENFORCEMENT (Spec 22)
    act_val = command.action_type.value if hasattr(command.action_type, "value") else str(command.action_type)
    if act_val in (ActionType.BROWSER_SCREENSHOT.value, "browser_screenshot"):
        perms = state.session_permissions.get(session_title, state.global_permissions)
        if not perms.get("enable_vision", False):
            return {
                "status": "denied",
                "error": {
                    "code": "VISION_DISABLED",
                    "message": "Screenshot blocked: 'enable_vision' is disabled in extension consent settings."
                },
                "message": "Vision disabled by user"
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
        session.human_in_control = True
        session.takeover_start_time = time.time()
        if state.extension_ws:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.STATE_SYNC.value,
                "human_in_control": True,
                "tab_group_id": session.tab_group_id,
                "notes": f"Security Abort: {reason}",
            }))
        logger.warning(f"Security Abort [Group {session.tab_group_id}]: Outbound requests locked. {reason}")

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
        res = {
            "status": ResponseStatus.ERROR.value,
            "message": "Extension is offline.",
            "error": {"code": ErrorCode.EXTENSION_OFFLINE.value, "message": "Chrome extension is not plugged into WebSocket gateway."},
        }
        if intervention_notes_meta:
            res["intervention_notes"] = intervention_notes_meta
            res["last_intervention_notes"] = intervention_notes_meta
        return res

    cmd_id = command.id
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    session.pending_responses[cmd_id] = fut
    state.pending_responses[cmd_id] = fut

    await state.extension_ws.send_text(json.dumps({
        "type": WSMessageType.EXECUTE_ACTION.value,
        "id": command.id,
        "action_type": command.action_type.value if hasattr(command.action_type, "value") else str(command.action_type),
        "target_data": command.target_data,
        "requires_privacy_check": command.requires_privacy_check,
        "session_title": command.session_title,
        "tab_group_id": session.tab_group_id,
    }))

    try:
        result = await asyncio.wait_for(fut, timeout=30.0)
        t_end = time.time()

        # If extension returned an error (e.g. user denied authorization), do not persist or store session
        if isinstance(result, dict) and result.get("status") == "error":
            error_data = result.get("error")
            err_code = error_data.get("code", ErrorCode.INTERNAL_ERROR.value) if isinstance(error_data, dict) else ErrorCode.INTERNAL_ERROR.value
            err_msg = error_data.get("message", result.get("message", "Browser action failed.")) if isinstance(error_data, dict) else result.get("message", "Browser action failed.")
            err_res = {
                "status": ResponseStatus.ERROR.value,
                "message": err_msg,
                "error": {"code": err_code, "message": err_msg},
            }
            if intervention_notes_meta:
                err_res["intervention_notes"] = intervention_notes_meta
                err_res["last_intervention_notes"] = intervention_notes_meta
            return err_res

        tab_group_id = None
        tab_id = None
        if isinstance(result, dict):
            tab_group_id = result.get("groupId")
            tab_id = result.get("tabId")

        if tab_group_id is None:
            tab_group_id = session.tab_group_id or 1

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

        sess_obj = session_manager.get_or_create_session(
            tab_group_id=tab_group_id,
            tab_group_name=session_title,
            agent_name=agent_name,
            group_color=group_color,
        )
        sess_obj.agent_name = agent_name
        sess_obj.group_color = group_color

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

        success_res = {"status": ResponseStatus.SUCCESS.value, "result": result}
        if intervention_notes_meta:
            success_res["intervention_notes"] = intervention_notes_meta
            success_res["last_intervention_notes"] = intervention_notes_meta
        return success_res
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
        to_res = {
            "status": ResponseStatus.ERROR.value,
            "message": "Execution engine frame timed out.",
            "error": {"code": ErrorCode.EXECUTION_TIMEOUT.value, "message": "Command execution exceeded 30.0s limit."},
        }
        if intervention_notes_meta:
            to_res["intervention_notes"] = intervention_notes_meta
            to_res["last_intervention_notes"] = intervention_notes_meta
        return to_res
    finally:
        state.pop_pending_future(cmd_id)


# ============================================================================
# Atomic OODA RPC Dispatch Handlers (Spec 23)
# ============================================================================

async def observe_page(
    tab_group_id: int | None = None,
    take_screenshot: bool = False,
    session_title: str | None = None,
    action_detail: str | None = None,
) -> dict[str, Any]:
    state.record_activity()
    if tab_group_id is None and session_title:
        active_sess = session_manager.get_active_session_by_title(session_title)
        if active_sess:
            tab_group_id = active_sess.tab_group_id
    session = state.get_session(tab_group_id)

    if action_detail:
        session_manager.update_session_milestone(
            session_title=session_title or "",
            action_detail=action_detail,
            tab_group_id=session.tab_group_id,
        )
        if state.extension_ws:
            try:
                active_sess = session_manager.get_active_session_by_group_id(session.tab_group_id)
                m_title = ""
                m_idx = 1
                prog_pct = 0
                if active_sess and active_sess.milestones:
                    m_idx = active_sess.active_milestone_index or 1
                    if 1 <= m_idx <= len(active_sess.milestones):
                        m_title = active_sess.milestones[m_idx - 1].title
                    completed = sum(1 for m in active_sess.milestones if m.status in (MilestoneStatus.COMPLETED, "completed"))
                    prog_pct = int((completed / len(active_sess.milestones)) * 100)
                await state.extension_ws.send_text(json.dumps({
                    "type": WSMessageType.SET_MILESTONE.value,
                    "session_title": session_title or (active_sess.tab_group_name if active_sess else ""),
                    "milestone_index": m_idx,
                    "milestone_title": m_title,
                    "current_action": action_detail,
                    "progress_percent": prog_pct,
                }))
            except Exception as e:
                logger.warning(f"Failed to dispatch milestone ticker on observe: {e}")

    if session.human_in_control:
        return {
            "status": ResponseStatus.HUMAN_LOCKED.value,
            "url": "",
            "title": "",
            "viewport": {},
            "tree_text": "",
            "elements": [],
            "message": "Human operator is currently in control of the browser session.",
            "last_intervention_notes": session.last_intervention_notes,
        }

    if not state.extension_ws:
        return {
            "status": ResponseStatus.ERROR.value,
            "url": "",
            "title": "",
            "viewport": {},
            "tree_text": "",
            "elements": [],
            "message": "Extension is offline.",
            "error": {
                "code": ErrorCode.EXTENSION_OFFLINE.value,
                "message": "Chrome extension is not plugged into WebSocket gateway."
            }
        }

    if take_screenshot and not state.global_permissions.get("enable_vision", False):
        take_screenshot = False

    request_id = f"obs_{uuid.uuid4().hex[:8]}"
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    session.pending_responses[request_id] = fut
    state.pending_responses[request_id] = fut

    outbound_frame = {
        "type": WSMessageType.EXECUTE_ACTION.value,
        "action_type": ActionType.OBSERVE_PAGE.value,
        "request_id": request_id,
        "id": request_id,
        "command_id": request_id,
        "tab_group_id": session.tab_group_id,
        "session_title": session_title,
        "take_screenshot": take_screenshot,
        "target_data": {"take_screenshot": take_screenshot, "action_detail": action_detail},
        "options": {"take_screenshot": take_screenshot, "action_detail": action_detail},
    }

    try:
        await state.extension_ws.send_text(json.dumps(outbound_frame))
        result = await asyncio.wait_for(fut, timeout=15.0)

        logger.info(f"observe_page fut resolved with result: {result}")
        if isinstance(result, dict):
            status = result.get("status", "success")
            res_dict = {
                "status": status,
                "url": result.get("url", ""),
                "title": result.get("title", ""),
                "viewport": result.get("viewport", {}),
                "tree_text": result.get("tree_text", result.get("treeText", "")),
                "elements": result.get("elements", []),
                "screenshot_path": result.get("screenshot_path", result.get("screenshotPath")),
            }
            if "message" in result:
                res_dict["message"] = result["message"]
            if "error" in result:
                res_dict["error"] = result["error"]
            return res_dict
        return {"status": "success", "data": result}
    except asyncio.TimeoutError:
        return {
            "status": ResponseStatus.ERROR.value,
            "url": "",
            "title": "",
            "viewport": {},
            "tree_text": "",
            "elements": [],
            "message": "Observation timed out after 15.0s limit.",
            "error": {
                "code": ErrorCode.EXECUTION_TIMEOUT.value,
                "message": "observe_page exceeded 15.0s correlation limit."
            }
        }
    finally:
        state.pop_pending_future(request_id)


async def act_element(payload: ActRequest) -> dict[str, Any]:
    state.record_activity()
    if payload.tab_group_id is None and payload.session_title:
        active_sess = session_manager.get_active_session_by_title(payload.session_title)
        if active_sess:
            payload.tab_group_id = active_sess.tab_group_id
    session = state.get_session(payload.tab_group_id)

    if session.human_in_control:
        return {
            "status": ResponseStatus.HUMAN_LOCKED.value,
            "action": payload.action,
            "element_id": payload.element_id,
            "duration_ms": 0.0,
            "mutations_observed": 0,
            "settle_reason": "human_locked",
            "intervention_notes": session.last_intervention_notes,
            "message": "Human operator is currently in control of the browser session.",
        }

    if payload.action_detail:
        session_manager.update_session_milestone(
            session_title=payload.session_title or "",
            action_detail=payload.action_detail,
            tab_group_id=session.tab_group_id,
        )
        if state.extension_ws:
            try:
                active_sess = session_manager.get_active_session_by_group_id(session.tab_group_id)
                m_title = ""
                m_idx = 1
                prog_pct = 0
                if active_sess and active_sess.milestones:
                    m_idx = active_sess.active_milestone_index or 1
                    if 1 <= m_idx <= len(active_sess.milestones):
                        m_title = active_sess.milestones[m_idx - 1].title
                    completed = sum(1 for m in active_sess.milestones if m.status in (MilestoneStatus.COMPLETED, "completed"))
                    prog_pct = int((completed / len(active_sess.milestones)) * 100)
                await state.extension_ws.send_text(json.dumps({
                    "type": WSMessageType.SET_MILESTONE.value,
                    "session_title": payload.session_title or (active_sess.tab_group_name if active_sess else ""),
                    "milestone_index": m_idx,
                    "milestone_title": m_title,
                    "current_action": payload.action_detail,
                    "progress_percent": prog_pct,
                }))
            except Exception as e:
                logger.warning(f"Failed to dispatch milestone ticker on act: {e}")

    # Flaw 4 Fix: Extract intervention notes and clear cache without dropping action payload!
    intervention_notes = None
    if session.last_intervention_notes:
        intervention_notes = session.last_intervention_notes
        session.last_intervention_notes = None

    if not state.extension_ws:
        return {
            "status": ResponseStatus.ERROR.value,
            "action": payload.action,
            "element_id": payload.element_id,
            "duration_ms": 0.0,
            "mutations_observed": 0,
            "settle_reason": "error",
            "intervention_notes": intervention_notes,
            "message": "Extension is offline.",
            "error": {
                "code": ErrorCode.EXTENSION_OFFLINE.value,
                "message": "Chrome extension is not plugged into WebSocket gateway."
            }
        }

    request_id = f"act_{uuid.uuid4().hex[:8]}"
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    session.pending_responses[request_id] = fut
    state.pending_responses[request_id] = fut

    outbound_frame = {
        "type": WSMessageType.EXECUTE_ACTION.value,
        "action_type": ActionType.ACT_ELEMENT.value,
        "request_id": request_id,
        "id": request_id,
        "command_id": request_id,
        "tab_group_id": session.tab_group_id,
        "session_title": payload.session_title,
        "target_data": payload.model_dump(),
        "payload": payload.model_dump(),
        "action": payload.action,
        "element_id": payload.element_id,
        "text": payload.text,
        "clear_first": payload.clear_first,
        "press_enter": payload.press_enter,
        "direction": payload.direction,
        "amount": payload.amount,
        "key": payload.key,
        "wait_settle": payload.wait_settle,
        "action_detail": payload.action_detail,
    }

    t0 = time.time()
    try:
        await state.extension_ws.send_text(json.dumps(outbound_frame))
        result = await asyncio.wait_for(fut, timeout=15.0)
        dur_ms = round((time.time() - t0) * 1000.0, 2)

        if isinstance(result, dict):
            status = result.get("status", "success")
            mutations = result.get("mutations_observed", result.get("mutations", 0))
            reason = result.get("settle_reason", result.get("settleReason", "quiescence"))
            res_dur = result.get("duration_ms", dur_ms)
            return {
                "status": status,
                "action": payload.action,
                "element_id": payload.element_id,
                "duration_ms": float(res_dur),
                "mutations_observed": int(mutations),
                "settle_reason": str(reason),
                "intervention_notes": intervention_notes,
            }

        return {
            "status": "success",
            "action": payload.action,
            "element_id": payload.element_id,
            "duration_ms": dur_ms,
            "mutations_observed": 0,
            "settle_reason": "quiescence",
            "intervention_notes": intervention_notes,
        }
    except asyncio.TimeoutError:
        dur_ms = round((time.time() - t0) * 1000.0, 2)
        return {
            "status": ResponseStatus.ERROR.value,
            "action": payload.action,
            "element_id": payload.element_id,
            "duration_ms": dur_ms,
            "mutations_observed": 0,
            "settle_reason": "timeout",
            "intervention_notes": intervention_notes,
            "message": "Action execution timed out after 15.0s limit.",
            "error": {
                "code": ErrorCode.EXECUTION_TIMEOUT.value,
                "message": "act_element exceeded 15.0s correlation limit."
            }
        }
    finally:
        state.pop_pending_future(request_id)


async def set_intent(
    tab_group_id: int | None = None,
    intent: str = "",
    subtext: str = "",
    phase: str | None = None,
) -> None:
    state.record_activity()
    session = state.get_session(tab_group_id)
    if state.extension_ws:
        outbound_frame = {
            "type": "set_intent",
            "tab_group_id": session.tab_group_id,
            "intent": intent,
            "subtext": subtext,
            "phase": phase,
        }
        try:
            await state.extension_ws.send_text(json.dumps(outbound_frame))
        except Exception as e:
            logger.warning(f"Failed to send set_intent to extension: {e}")


async def capture_screenshot(
    tab_group_id: int | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    state.record_activity()
    session = state.get_session(tab_group_id)

    if session.human_in_control:
        return {
            "status": ResponseStatus.HUMAN_LOCKED.value,
            "message": "Human operator is currently in control of the browser session.",
            "last_intervention_notes": session.last_intervention_notes,
        }

    # Check global vision permission
    if not state.global_permissions.get("enable_vision", False):
        return {
            "status": "denied",
            "error": {
                "code": "VISION_DISABLED",
                "message": "Screenshot blocked: 'enable_vision' is disabled in extension consent settings."
            },
            "message": "Vision disabled by user"
        }

    if not state.extension_ws:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": "Extension is offline.",
            "error": {
                "code": ErrorCode.EXTENSION_OFFLINE.value,
                "message": "Chrome extension is not plugged into WebSocket gateway."
            }
        }

    request_id = f"snap_{uuid.uuid4().hex[:8]}"
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    session.pending_responses[request_id] = fut
    state.pending_responses[request_id] = fut

    active_sess = session_manager.get_active_session_by_group_id(session.tab_group_id)
    session_title = active_sess.tab_group_name if active_sess else "Browser Task"

    outbound_frame = {
        "type": WSMessageType.EXECUTE_ACTION.value,
        "id": request_id,
        "command_id": request_id,
        "action_type": ActionType.BROWSER_SCREENSHOT.value,
        "target_data": filename or "",
        "session_title": session_title,
        "tab_group_id": session.tab_group_id,
    }

    try:
        await state.extension_ws.send_text(json.dumps(outbound_frame))
        result = await asyncio.wait_for(fut, timeout=15.0)

        data_url = None
        if isinstance(result, dict):
            if result.get("status") == "denied":
                return result
            data_url = result.get("data")
        elif isinstance(result, str):
            data_url = result

        saved_path = None
        if data_url and isinstance(data_url, str) and "base64," in data_url:
            import base64
            try:
                _, b64_data = data_url.split("base64,", 1)
                img_bytes = base64.b64decode(b64_data)
                save_dir = active_sess.artifacts_dir if active_sess else os.path.join(str(get_default_logs_dir()), "screenshots")
                os.makedirs(save_dir, exist_ok=True)
                fname = filename or f"screenshot_{int(time.time() * 1000)}.png"
                if not fname.endswith(".png"):
                    fname += ".png"
                saved_path = os.path.join(save_dir, fname)
                with open(saved_path, "wb") as f:
                    f.write(img_bytes)
            except Exception as e:
                logger.warning(f"Failed to write screenshot file: {e}")

        return {
            "status": "success",
            "screenshot_path": saved_path,
            "filename": os.path.basename(saved_path) if saved_path else filename,
            "data": data_url[:100] + "..." if data_url and len(data_url) > 100 else data_url,
            "message": "Screenshot captured successfully."
        }
    except asyncio.TimeoutError:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": "Screenshot capture timed out after 15.0s limit.",
            "error": {
                "code": ErrorCode.EXECUTION_TIMEOUT.value,
                "message": "capture_screenshot exceeded 15.0s correlation limit."
            }
        }
    finally:
        state.pop_pending_future(request_id)


async def finalize_task_complete(
    tab_group_id: int | None = None,
    result: str | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    state.record_activity()
    gid = tab_group_id or 0
    t_now = time.time()

    active_sess = session_manager.get_active_session_by_group_id(gid)
    if not active_sess and gid == 0 and session_manager.active_sessions:
        active_sess = list(session_manager.active_sessions.values())[0]

    session_title = active_sess.tab_group_name if active_sess else "Browser Task"
    actual_gid = active_sess.tab_group_id if active_sess else gid

    clean_title = session_title.replace("✅", "").strip()
    completed_title = f"✅ {clean_title}"
    session_manager.log_event(
        tab_group_id=actual_gid,
        event_type=SessionEventType.TASK_COMPLETE,
        title=f"Task Completed: {completed_title}",
        start_time=t_now,
        end_time=t_now,
        tab_id=getattr(active_sess, "active_tab_id", None) if active_sess else None,
        tab_group_id_val=actual_gid,
        payload={"result": result, "status": status},
    )

    sess_status = SessionStatus.COMPLETED if status == "completed" else SessionStatus.STOPPED
    session_manager.finalize_session(tab_group_id=actual_gid, status=sess_status, end_reason="task_complete")

    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": WSMessageType.EXECUTE_ACTION.value,
                "id": f"tc_{uuid.uuid4().hex[:8]}",
                "action_type": ActionType.TASK_COMPLETE.value,
                "target_data": result or "",
                "session_title": session_title,
                "tab_group_id": actual_gid,
            }))
            await set_intent(tab_group_id=actual_gid, intent="", subtext="", phase=None)
        except Exception as e:
            logger.warning(f"Failed to dispatch task complete to extension: {e}")

    if actual_gid in state.tab_sessions:
        tab_sess = state.tab_sessions[actual_gid]
        tab_sess.human_in_control = False
        tab_sess.last_intervention_notes = None

    return {
        "status": "success",
        "tab_group_id": actual_gid,
        "result": result,
        "message": f"Task concluded, session documentation finalized, and HUD state reset for tab group {actual_gid}."
    }


@app.post("/observe")
async def observe_endpoint(payload: ObserveRequest) -> dict[str, Any]:
    state.record_activity()
    return await observe_page(
        tab_group_id=payload.tab_group_id,
        take_screenshot=payload.take_screenshot,
        session_title=payload.session_title,
        action_detail=payload.action_detail,
    )


@app.post("/act")
async def act_endpoint(payload: ActRequest) -> dict[str, Any]:
    state.record_activity()
    return await act_element(payload=payload)


@app.post("/set_intent")
async def set_intent_endpoint(payload: SetIntentRequest) -> dict[str, Any]:
    state.record_activity()
    await set_intent(
        tab_group_id=payload.tab_group_id,
        intent=payload.intent,
        subtext=payload.subtext,
        phase=payload.phase,
    )
    return {"status": "success"}


@app.post("/screenshot")
async def screenshot_endpoint(payload: ScreenshotRequest) -> dict[str, Any]:
    state.record_activity()
    return await capture_screenshot(tab_group_id=payload.tab_group_id, filename=payload.filename)


@app.post("/task_complete")
async def task_complete_endpoint(payload: TaskCompleteRequest) -> dict[str, Any]:
    state.record_activity()
    return await finalize_task_complete(
        tab_group_id=payload.tab_group_id,
        result=payload.result,
        status=payload.status,
    )


@app.post("/human_release")
async def human_release(payload: ReleasePayload) -> dict[str, Any]:
    state.record_activity()
    t_now = time.time()
    notes = payload.notes if payload.notes else "Released by human operator."

    if payload.tab_group_id is not None:
        target_sessions = [state.get_session(payload.tab_group_id)]
    else:
        target_sessions = list(state.tab_sessions.values())
        if not target_sessions:
            target_sessions = [state.get_session(0)]

    for session in target_sessions:
        session.human_in_control = False
        session.last_intervention_notes = notes
        takeover_dur_ms = 0.0
        if session.takeover_start_time:
            takeover_dur_ms = max(0.0, round((t_now - session.takeover_start_time) * 1000.0, 2))
            session.takeover_start_time = None
        logger.info(f"Human Release [Group {session.tab_group_id}] -> Human In Control: False, Notes: {notes}, Duration: {takeover_dur_ms}ms")

        if session.tab_group_id in session_manager.active_sessions:
            session_manager.log_event(
                tab_group_id=session.tab_group_id,
                event_type=SessionEventType.HUMAN_RELEASE,
                title="Human Operator Release Handoff",
                start_time=t_now - (takeover_dur_ms / 1000.0),
                end_time=t_now,
                payload={
                    "notes": notes,
                    "takeover_duration_ms": takeover_dur_ms,
                },
            )

    if state.extension_ws:
        try:
            sync_payload = {
                "type": WSMessageType.STATE_SYNC.value,
                "human_in_control": False,
                "notes": notes,
            }
            if payload.tab_group_id is not None:
                sync_payload["tab_group_id"] = payload.tab_group_id
            await state.extension_ws.send_text(json.dumps(sync_payload))
        except Exception as e:
            logger.warning(f"Error sending state_sync on release: {e}")

    return {"status": ResponseStatus.SUCCESS.value, "human_in_control": False}


@app.post("/stop")
async def stop_active_task(tab_group_id: int | None = None) -> dict[str, Any]:
    state.record_activity()
    if tab_group_id is not None:
        sessions_to_stop = [state.get_session(tab_group_id)]
    else:
        sessions_to_stop = list(state.tab_sessions.values())
        if not sessions_to_stop:
            sessions_to_stop = [state.get_session(0)]

    for session in sessions_to_stop:
        session.human_in_control = False
        session.last_intervention_notes = None
        session.takeover_start_time = None
        for cmd_id, future in list(session.pending_responses.items()):
            if not future.done():
                future.set_result({"status": "aborted", "message": "Task terminated by human operator."})
        session.pending_responses.clear()

        if session.tab_group_id in session_manager.active_sessions:
            session_manager.finalize_session(
                tab_group_id=session.tab_group_id,
                status=SessionStatus.STOPPED,
                end_reason="user_stopped",
            )

    if tab_group_id is None:
        for cmd_id, future in list(state.pending_responses.items()):
            if not future.done():
                future.set_result({"status": "aborted", "message": "Task terminated by human operator."})
        state.pending_responses.clear()

        for gid in list(session_manager.active_sessions.keys()):
            session_manager.finalize_session(
                tab_group_id=gid,
                status=SessionStatus.STOPPED,
                end_reason="user_stopped",
            )

    logger.info(f"Task aborted by user takeover stop command (tab_group_id={tab_group_id}).")

    if state.extension_ws:
        try:
            stop_sync = {
                "type": WSMessageType.STATE_SYNC.value,
                "human_in_control": False,
                "notes": "Task terminated.",
            }
            if tab_group_id is not None:
                stop_sync["tab_group_id"] = tab_group_id
            await state.extension_ws.send_text(json.dumps(stop_sync))

            # Broadcast hide_glow and clear_badges to clear all HUD artifacts and badging
            await state.extension_ws.send_text(json.dumps({
                "type": "hide_glow",
                "session_title": "",
            }))
            await state.extension_ws.send_text(json.dumps({
                "type": "clear_badges",
                "session_title": "",
            }))
        except Exception as e:
            logger.warning(f"Error sending state_sync / clear on stop: {e}")

    return {"status": ResponseStatus.SUCCESS.value}


@app.post("/clear_badges")
async def clear_badges_endpoint(tab_group_id: int | None = None) -> dict[str, Any]:
    state.record_activity()
    if state.extension_ws:
        try:
            await state.extension_ws.send_text(json.dumps({
                "type": "clear_badges",
                "tab_group_id": tab_group_id,
            }))
        except Exception as e:
            logger.warning(f"Error broadcasting clear_badges: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "success", "message": "Clear badges broadcast sent."}
