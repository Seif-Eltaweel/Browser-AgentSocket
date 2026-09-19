"""
AgentSocket - Smart Launcher & Subsystem Manager
Handles on-demand gateway boot, extension health checks, process lifecycle, Chrome auto-launch, and declarative CLI dispatch.
"""

from __future__ import annotations
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any, Callable
import requests

# Ensure UTF-8 output encoding for cross-platform emojis and unicode tree symbols
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from server.logger import logger
from server.models import ActionType, ErrorCode, ResponseStatus
from server.session import (
    format_session_thread,
    print_history_table,
    print_session_logs,
    print_subskill_details,
    print_subskills_table,
    session_manager,
)

EXTENSION_DIR = os.path.join(REPO_ROOT, "extension")
PID_FILE_PATH = os.path.join(REPO_ROOT, ".socket_server.pid")
PORT_FILE_PATH = os.path.join(REPO_ROOT, ".socket_server.port")
TOKEN_FILE_PATH = os.path.join(REPO_ROOT, ".socket_server.token")
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
AUTH_TOKEN_HEADER = "X-AgentSocket-Token"


def get_gateway_token() -> str | None:
    """Reads the ephemeral gateway token from file or environment."""
    env_tok = os.environ.get("AGENTSOCKET_TOKEN")
    if env_tok:
        return env_tok
    if os.path.exists(TOKEN_FILE_PATH):
        try:
            with open(TOKEN_FILE_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    return None


def get_auth_headers() -> dict[str, str]:
    """Constructs headers including X-AgentSocket-Token if available."""
    token = get_gateway_token()
    if token:
        return {AUTH_TOKEN_HEADER: token}
    return {}

# Named platform-specific subprocess creation flags
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
WIN_CREATE_FLAGS = (
    subprocess.CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS
) if platform.system() == "Windows" else 0


def is_pid_running(pid: int) -> bool:
    """Checks if a given process ID is actively executing on the OS."""
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                creationflags=CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                text=True,
            )
            return str(pid) in out
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def clean_stale_pid_file() -> None:
    """Removes PID file if the corresponding process is not running."""
    if os.path.exists(PID_FILE_PATH):
        try:
            with open(PID_FILE_PATH, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if not is_pid_running(pid):
                os.remove(PID_FILE_PATH)
        except Exception:
            try:
                os.remove(PID_FILE_PATH)
            except Exception:
                pass


def clean_stale_port_file() -> None:
    """Removes port file if the corresponding server process is not running."""
    if os.path.exists(PORT_FILE_PATH):
        try:
            if os.path.exists(PID_FILE_PATH):
                with open(PID_FILE_PATH, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip())
                if not is_pid_running(pid):
                    os.remove(PORT_FILE_PATH)
            else:
                os.remove(PORT_FILE_PATH)
        except Exception:
            try:
                os.remove(PORT_FILE_PATH)
            except Exception:
                pass


def resolve_server_url(default_port: int = 8000) -> str:
    """
    Resolves the active AgentSocket server URL using a priority waterfall:
    1. Environment variable: AGENTSOCKET_URL or AGENTSOCKET_PORT
    2. File discovery: .socket_server.port (validated against PID / status)
    3. Multi-port probe: [8000, 8001, 8002, 8003, 8080, 8500, 9000]
    4. Fallback to default
    """
    # 1. Environment variables
    env_url = os.environ.get("AGENTSOCKET_URL")
    if env_url:
        return env_url.rstrip("/")

    env_port = os.environ.get("AGENTSOCKET_PORT")
    if env_port:
        try:
            p = int(env_port)
            return f"http://127.0.0.1:{p}"
        except ValueError:
            pass

    # 2. File discovery (.socket_server.port)
    if os.path.exists(PORT_FILE_PATH):
        try:
            with open(PORT_FILE_PATH, "r", encoding="utf-8") as f:
                port_val = int(f.read().strip())
            candidate_url = f"http://127.0.0.1:{port_val}"
            # Trust port file unless a stale dead PID is confirmed
            if not os.path.exists(PID_FILE_PATH) or is_process_running(PID_FILE_PATH) or is_server_running(candidate_url):
                return candidate_url
            else:
                clean_stale_port_file()
        except Exception:
            pass

    # 3. Multi-port probing
    candidate_ports = [8000, 8001, 8002, 8003, 8080, 8500, 9000]
    for p in candidate_ports:
        candidate_url = f"http://127.0.0.1:{p}"
        if is_server_running(candidate_url):
            return candidate_url

    # 4. Fallback
    return f"http://127.0.0.1:{default_port}"



def find_chrome_path() -> str | None:
    """Detects the Google Chrome or Chromium executable across Windows, macOS, and Linux."""
    system = platform.system()

    if system == "Windows":
        candidate_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            shutil.which("chrome"),
            shutil.which("chrome.exe"),
            # Fallback to Edge if Chrome is missing
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            shutil.which("msedge"),
        ]
        # Also check Windows Registry
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            val, _ = winreg.QueryValueEx(key, "")
            if val and os.path.exists(val):
                candidate_paths.insert(0, val)
        except Exception:
            pass

    elif system == "Darwin":  # macOS
        candidate_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            shutil.which("google-chrome"),
            shutil.which("chromium"),
        ]
    else:  # Linux / BSD
        candidate_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
        ]

    for path in candidate_paths:
        if path and os.path.exists(path):
            return os.path.abspath(path)

    return None


def is_server_running(server_url: str = DEFAULT_SERVER_URL) -> bool:
    """Checks if the FastAPI gateway server is responding."""
    try:
        resp = requests.get(f"{server_url}/status", headers=get_auth_headers(), timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


def get_gateway_status(server_url: str = DEFAULT_SERVER_URL) -> dict[str, Any]:
    """Fetches the current status payload from the gateway server."""
    clean_stale_pid_file()
    try:
        resp = requests.get(f"{server_url}/status", headers=get_auth_headers(), timeout=2.0)
        if resp.status_code == 200:
            return resp.json()
        return {"status": "error", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "offline", "error": str(e), "extension_connected": False, "human_in_control": False}


def ensure_server_running(port: int = 8000, timeout: float = 8.0) -> bool:
    """Ensures the FastAPI gateway server is running, booting it in the background if needed."""
    clean_stale_pid_file()
    clean_stale_port_file()
    server_url = f"http://127.0.0.1:{port}"
    if is_server_running(server_url):
        return True

    logger.info(f"Gateway server not detected on port {port}. Spawning background socket process...")
    cmd = [sys.executable, "-m", "uvicorn", "server.socket_server:app", "--port", str(port), "--host", "127.0.0.1"]

    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=WIN_CREATE_FLAGS,
        start_new_session=(platform.system() != "Windows"),
    )

    try:
        with open(PID_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
        with open(PORT_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(str(port))
    except Exception as e:
        logger.warning(f"Could not write PID/port file: {e}")

    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_server_running(server_url):
            logger.info(f"Gateway server is live on {server_url} (PID: {proc.pid}).")
            return True
        time.sleep(0.3)

    logger.error(f"Gateway server failed to start within {timeout}s.")
    return False


def launch_chrome_with_extension(extension_dir: str = EXTENSION_DIR, timeout: float = 6.0) -> bool:
    """Launches Chrome with the AgentSocket unpacked extension loaded."""
    chrome_bin = find_chrome_path()
    if not chrome_bin:
        logger.error("Could not locate Chrome or Chromium on this system.")
        return False

    abs_ext_dir = os.path.abspath(extension_dir)
    logger.info(f"Launching Chrome ({chrome_bin}) with extension: {abs_ext_dir}")

    chrome_cmd = [
        chrome_bin,
        f"--load-extension={abs_ext_dir}",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    subprocess.Popen(
        chrome_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=WIN_CREATE_FLAGS,
        start_new_session=(platform.system() != "Windows"),
    )

    start_time = time.time()
    while time.time() - start_time < timeout:
        status = get_gateway_status()
        if status.get("extension_connected"):
            logger.info("Chrome Extension plugged in successfully to gateway socket.")
            return True
        time.sleep(0.5)

    logger.info("Chrome launched. Awaiting extension WebSocket handshake.")
    return True


def ensure_ready(server_url: str = DEFAULT_SERVER_URL, auto_launch_chrome: bool = True) -> dict[str, Any]:
    """
    Guarantees the subsystem is fully initialized:
    1. Boots FastAPI server if inactive.
    2. Auto-launches Chrome with extension if not connected.
    """
    if not is_server_running(server_url):
        if not ensure_server_running():
            return {
                "status": ResponseStatus.ERROR.value,
                "message": "Failed to start FastAPI gateway server.",
                "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": "Server process did not become healthy."},
            }

    status = get_gateway_status(server_url)
    if not status.get("extension_connected") and auto_launch_chrome:
        logger.info("Extension not connected. Triggering auto-launch for Chrome...")
        launch_chrome_with_extension()
        status = get_gateway_status(server_url)

    return status


def execute_action(
    action_type: str,
    target_data: str,
    session_title: str,
    requires_privacy_check: bool = False,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Ensures environment is ready and sends action payload to /execute."""
    ensure_ready(server_url)
    payload = {
        "id": str(uuid.uuid4()),
        "action_type": action_type,
        "target_data": target_data,
        "requires_privacy_check": requires_privacy_check,
        "session_title": session_title,
    }
    try:
        resp = requests.post(f"{server_url}/execute", json=payload, headers=get_auth_headers(), timeout=35.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Execution request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


# ============================================================================
# Strategic Plan & Milestones Client Helpers (Spec 32)
# ============================================================================

def session_set_plan(
    session_title: str,
    milestones: list[dict[str, Any] | str],
    active_index: int = 1,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Registers strategic execution milestones with the gateway and extension HUD (Spec 32)."""
    ensure_ready(server_url)
    payload = {
        "session_title": session_title,
        "milestones": milestones,
        "active_milestone_index": active_index,
    }
    try:
        resp = requests.post(f"{server_url}/plan", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Plan registration failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def session_update_milestone(
    session_title: str,
    milestone_index: int | None = None,
    milestone_title: str | None = None,
    action_detail: str | None = None,
    status: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Updates active milestone state or action detail with the gateway and extension HUD (Spec 32)."""
    ensure_ready(server_url)
    payload: dict[str, Any] = {"session_title": session_title}
    if milestone_index is not None:
        payload["milestone_index"] = milestone_index
    if milestone_title is not None:
        payload["milestone_title"] = milestone_title
    if action_detail is not None:
        payload["action_detail"] = action_detail
    if status is not None:
        payload["status"] = status
    try:
        resp = requests.post(f"{server_url}/plan/milestone", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Milestone update failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


# ============================================================================
# Atomic Operator Client Helpers (Spec 24)
# ============================================================================

def browser_observe(
    tab_group_id: int | None = None,
    session_title: str | None = None,
    take_screenshot: bool = False,
    action_detail: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Captures ARIA tree, assigns ephemeral numeric badges [1]..[N], and returns structured DOM snapshot."""
    ensure_ready(server_url)
    payload = {
        "tab_group_id": tab_group_id,
        "session_title": session_title,
        "take_screenshot": take_screenshot,
        "action_detail": action_detail,
    }
    try:
        resp = requests.post(f"{server_url}/observe", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Observation request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def browser_click(
    element_id: int,
    tab_group_id: int | None = None,
    session_title: str | None = None,
    action_detail: str | None = None,
    wait_settle: bool = True,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Dispatches native focus, mouse/pointer events on the element and awaits adaptive settlement."""
    ensure_ready(server_url)
    payload = {
        "action": "click",
        "element_id": element_id,
        "tab_group_id": tab_group_id,
        "session_title": session_title,
        "action_detail": action_detail,
        "wait_settle": wait_settle,
    }
    try:
        resp = requests.post(f"{server_url}/act", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Click request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def browser_type(
    element_id: int,
    text: str,
    tab_group_id: int | None = None,
    session_title: str | None = None,
    action_detail: str | None = None,
    clear_first: bool = False,
    press_enter: bool = False,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Sets element value via prototype setter, dispatches change events, and settles."""
    ensure_ready(server_url)
    payload = {
        "action": "type",
        "element_id": element_id,
        "text": text,
        "tab_group_id": tab_group_id,
        "session_title": session_title,
        "action_detail": action_detail,
        "clear_first": clear_first,
        "press_enter": press_enter,
    }
    try:
        resp = requests.post(f"{server_url}/act", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Type request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def browser_scroll(
    direction: str,
    amount: int | None = None,
    tab_group_id: int | None = None,
    session_title: str | None = None,
    action_detail: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Scrolls viewport ('down', 'up', 'top', 'bottom')."""
    ensure_ready(server_url)
    payload = {
        "action": "scroll",
        "direction": direction,
        "amount": amount,
        "tab_group_id": tab_group_id,
        "session_title": session_title,
        "action_detail": action_detail,
    }
    try:
        resp = requests.post(f"{server_url}/act", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Scroll request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def browser_key_press(
    key: str,
    tab_group_id: int | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Sends native keyboard events ('Enter', 'Escape', 'Tab', etc.)."""
    ensure_ready(server_url)
    payload = {
        "action": "key_press",
        "key": key,
        "tab_group_id": tab_group_id,
    }
    try:
        resp = requests.post(f"{server_url}/act", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Key press request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def browser_screenshot(
    tab_group_id: int | None = None,
    filename: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Captures high-res screenshot (if vision permission granted by user)."""
    ensure_ready(server_url)
    payload = {
        "tab_group_id": tab_group_id,
        "filename": filename,
    }
    try:
        resp = requests.post(f"{server_url}/screenshot", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Screenshot request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def task_complete(
    result: str | None = None,
    status: str = "completed",
    tab_group_id: int | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Concludes task, finalizes session documentation, and resets HUD state."""
    ensure_ready(server_url)
    payload = {
        "tab_group_id": tab_group_id,
        "result": result,
        "status": status,
    }
    try:
        resp = requests.post(f"{server_url}/task_complete", json=payload, headers=get_auth_headers(), timeout=20.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Task complete request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def browser_set_milestone(
    milestone_title: str,
    phase_number: int | None = None,
    total_phases: int | None = None,
    tab_group_id: int | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Updates HUD phase badge and intent ticker for complex workflows."""
    ensure_ready(server_url)
    phase_str = None
    if phase_number is not None and total_phases is not None:
        phase_str = f"Phase {phase_number}/{total_phases}"
    elif phase_number is not None:
        phase_str = f"Phase {phase_number}"

    payload = {
        "tab_group_id": tab_group_id,
        "intent": milestone_title,
        "subtext": "",
        "phase": phase_str,
    }
    try:
        resp = requests.post(f"{server_url}/set_intent", json=payload, headers=get_auth_headers(), timeout=5.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Set milestone request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def send_progress(
    session_title: str,
    step_current: int,
    step_total: int,
    step_title: str,
    server_url: str | None = None,
) -> dict[str, Any]:
    """Dispatches a progress update to the gateway server."""
    url = server_url or resolve_server_url()
    payload = {
        "session_title": session_title,
        "step_current": step_current,
        "step_total": step_total,
        "step_title": step_title,
    }
    try:
        resp = requests.post(f"{url}/progress", json=payload, headers=get_auth_headers(), timeout=5.0)
        return resp.json()
    except Exception as e:
        return {
            "status": "warning",
            "message": f"Could not dispatch progress to {url}: {e}",
            "progress_percent": int((step_current / max(1, step_total)) * 100),
        }


def release_takeover(notes: str = "", server_url: str = DEFAULT_SERVER_URL) -> dict[str, Any]:
    """Releases human intervention lockout."""
    ensure_ready(server_url, auto_launch_chrome=False)
    try:
        resp = requests.post(f"{server_url}/human_release", json={"notes": notes}, headers=get_auth_headers(), timeout=5.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Human release request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def stop_tasks(server_url: str = DEFAULT_SERVER_URL) -> dict[str, Any]:
    """Stops active tasks and resets state."""
    ensure_ready(server_url, auto_launch_chrome=False)
    try:
        resp = requests.post(f"{server_url}/stop", headers=get_auth_headers(), timeout=5.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Stop request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        }


def kill_server() -> bool:
    """Terminates the running gateway server process."""
    pid = None
    if os.path.exists(PID_FILE_PATH):
        try:
            with open(PID_FILE_PATH, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
        except Exception:
            pass

    if pid:
        try:
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, 9)
            logger.info(f"Terminated server PID {pid}.")
        except Exception as e:
            logger.error(f"Error killing PID {pid}: {e}")

    if os.path.exists(PID_FILE_PATH):
        try:
            os.remove(PID_FILE_PATH)
        except Exception:
            pass
    if os.path.exists(PORT_FILE_PATH):
        try:
            os.remove(PORT_FILE_PATH)
        except Exception:
            pass
    return True


# ============================================================================
# Session History & Introspection Helpers
# ============================================================================
def query_history(
    query_hint: str = "",
    month: str | None = None,
    limit: int = 10,
    server_url: str = DEFAULT_SERVER_URL,
) -> list[dict[str, Any]]:
    """Queries past sessions from server or directly via SessionManager."""
    if is_server_running(server_url):
        try:
            params = {"query": query_hint, "limit": limit}
            if month:
                params["month"] = month
            resp = requests.get(f"{server_url}/history", params=params, headers=get_auth_headers(), timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return session_manager.query_history(query_hint=query_hint, month=month, limit=limit)


def get_session_details(session_path: str, server_url: str = DEFAULT_SERVER_URL) -> dict[str, Any]:
    """Retrieves full chronological events thread for a session."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/session/details", params={"path": session_path}, headers=get_auth_headers(), timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return session_manager.get_session_details(session_path=session_path)


def get_session_artifact(session_path: str, artifact_name: str, server_url: str = DEFAULT_SERVER_URL) -> dict[str, Any] | str:
    """Retrieves an offloaded payload or artifact path."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/session/artifact", params={"path": session_path, "name": artifact_name}, headers=get_auth_headers(), timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return session_manager.get_session_artifact(session_path=session_path, artifact_name=artifact_name)


def get_session_document(session_path: str, server_url: str = DEFAULT_SERVER_URL) -> str:
    """Generates and retrieves the full consolidated session document."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/session/document", params={"path": session_path}, headers=get_auth_headers(), timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("document_markdown", "")
        except Exception:
            pass
    return session_manager.generate_session_document(session_dir_or_path=session_path)


def get_session_thread(session_path: str, server_url: str = DEFAULT_SERVER_URL) -> str:
    """Generates and retrieves the dedicated standalone thread markdown (THREAD.md)."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/session/thread", params={"path": session_path}, headers=get_auth_headers(), timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("thread_markdown", "")
        except Exception:
            pass
    return session_manager.generate_thread_document(session_dir_or_path=session_path)


def export_all_timeline(month: str | None = None, output_path: str | None = None) -> str:
    """Exports master history report to Markdown."""
    return session_manager.export_all_to_markdown(month=month, output_path=output_path)


# ============================================================================
# Subskills & Borrowing Engine Helpers
# ============================================================================
def list_subskills(
    query: str = "",
    tags: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> list[dict[str, Any]]:
    """Lists registered subskills from gateway server or session_manager."""
    if is_server_running(server_url):
        try:
            params = {}
            if query:
                params["query"] = query
            if tags:
                params["tags"] = tags
            resp = requests.get(f"{server_url}/subskills", params=params, headers=get_auth_headers(), timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return session_manager.list_subskills(query=query, tags=tag_list)


def get_subskill(name: str, server_url: str = DEFAULT_SERVER_URL) -> dict[str, Any] | None:
    """Retrieves detailed subskill info including playbook markdown."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/subskills/{name}", headers=get_auth_headers(), timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    return data.get("data")
        except Exception:
            pass
    return session_manager.get_subskill(name=name)


def borrow_subskill(
    name: str,
    session_title: str,
    tab_group_id: int | None = None,
    input_file_path: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Borrows a subskill into an active session workspace."""
    if is_server_running(server_url):
        try:
            payload = {
                "name": name,
                "session_title": session_title,
                "tab_group_id": tab_group_id,
                "input_file_path": input_file_path,
            }
            resp = requests.post(f"{server_url}/subskills/borrow", json=payload, headers=get_auth_headers(), timeout=8.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return session_manager.borrow_subskill(
        name=name,
        target_session_id_or_title_or_path=session_title,
        tab_group_id=tab_group_id,
        input_file_path=input_file_path,
    )


def register_subskill(
    session_path: str,
    name: str,
    display_title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    adhoc_tools: list[str] | None = None,
    subskill_markdown: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Registers or updates a session as a reusable subskill."""
    if is_server_running(server_url):
        try:
            payload = {
                "session_path": session_path,
                "name": name,
                "display_title": display_title,
                "description": description,
                "tags": tags,
                "adhoc_tools": adhoc_tools,
                "subskill_markdown": subskill_markdown,
            }
            resp = requests.post(f"{server_url}/subskills/register", json=payload, headers=get_auth_headers(), timeout=8.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return session_manager.register_subskill(
        session_path=session_path,
        name=name,
        display_title=display_title,
        description=description,
        tags=tags,
        adhoc_tools=adhoc_tools,
        subskill_markdown=subskill_markdown,
    )


# ============================================================================
# Central Adhocs Vault & Resolution API Helpers (Permanently Retired - Spec 33)
# ============================================================================
def list_adhocs(server_url: str = DEFAULT_SERVER_URL) -> list[dict[str, Any]]:
    """[PERMANENTLY RETIRED - Spec 33] Returns empty list."""
    return []


def promote_adhoc(
    session_path: str,
    tool_name: str,
    target: str = "universal",
    subskill_name: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """[PERMANENTLY RETIRED - Spec 33] Returns deprecation error."""
    return {
        "status": "error",
        "code": "ADHOC_ARCHITECTURE_DEPRECATED",
        "message": (
            "Adhoc script promotion has been permanently retired under Spec 33. "
            "All browser automation MUST be driven turn-by-turn using atomic OODA tools."
        ),
    }


def resolve_adhoc(
    tool_name: str,
    session_path: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """[PERMANENTLY RETIRED - Spec 33] Returns deprecation error."""
    return {
        "found": False,
        "error": "Adhoc script resolution has been permanently retired under Spec 33.",
    }


def run_adhoc(
    tool_name: str,
    session_path: str | None = None,
    args: list[str] | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """[PERMANENTLY RETIRED - Spec 33] Returns deprecation error."""
    return {
        "status": "error",
        "code": "ADHOC_ARCHITECTURE_DEPRECATED",
        "message": (
            "Adhoc script execution has been permanently retired under Spec 33. "
            "All browser automation MUST be driven turn-by-turn using atomic OODA tools: "
            "browser_observe, browser_click, browser_type, browser_scroll, browser_key_press."
        ),
    }


def session_set_plan(
    session_title: str,
    milestones: list[str] | list[dict[str, Any]],
    active_index: int = 1,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Registers strategic execution milestones for a session."""
    if is_server_running(server_url):
        try:
            payload = {
                "session_title": session_title,
                "milestones": milestones,
                "active_milestone_index": active_index,
            }
            resp = requests.post(f"{server_url}/plan", json=payload, headers=get_auth_headers(), timeout=8.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Failed to post plan to gateway: {e}")
    return session_manager.set_session_plan(
        session_title=session_title,
        milestones=milestones,
        active_index=active_index,
    )


def session_update_milestone(
    session_title: str,
    milestone_index: int | None = None,
    milestone_title: str | None = None,
    action_detail: str | None = None,
    status: str | None = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, Any]:
    """Updates active milestone state or broadcasts live ticker detail."""
    if is_server_running(server_url):
        try:
            payload = {
                "session_title": session_title,
                "milestone_index": milestone_index,
                "milestone_title": milestone_title,
                "action_detail": action_detail,
                "status": status,
            }
            resp = requests.post(f"{server_url}/plan/milestone", json=payload, headers=get_auth_headers(), timeout=8.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Failed to post milestone update to gateway: {e}")
    return session_manager.update_session_milestone(
        session_title=session_title,
        milestone_index=milestone_index,
        milestone_title=milestone_title,
        action_detail=action_detail,
        status=status,
    )



# ============================================================================
# Declarative CLI Command Handlers
# ============================================================================
def cmd_status(args: argparse.Namespace) -> None:
    status = get_gateway_status()
    print(json.dumps(status, indent=2))


def cmd_plug(args: argparse.Namespace) -> None:
    status = ensure_ready()
    print(json.dumps(status, indent=2))


def cmd_navigate(args: argparse.Namespace) -> None:
    res = execute_action("navigate", args.url, requires_privacy_check=args.privacy, session_title=args.title)
    print(json.dumps(res, indent=2))


def cmd_eval(args: argparse.Namespace) -> None:
    res = execute_action("execute_js", args.code, requires_privacy_check=args.privacy, session_title=args.title)
    print(json.dumps(res, indent=2))


def cmd_release(args: argparse.Namespace) -> None:
    res = release_takeover(args.notes)
    print(json.dumps(res, indent=2))


def cmd_stop(args: argparse.Namespace) -> None:
    res = stop_tasks()
    print(json.dumps(res, indent=2))


def cmd_kill(args: argparse.Namespace) -> None:
    kill_server()


def cmd_history(args: argparse.Namespace) -> None:
    results = query_history(query_hint=args.query, month=args.month, limit=args.limit)
    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
    else:
        print_history_table(results)


def cmd_logs(args: argparse.Namespace) -> None:
    details = get_session_details(session_path=args.path)
    if getattr(args, "json", False):
        print(json.dumps(details, indent=2))
    else:
        print_session_logs(details)


def cmd_doc(args: argparse.Namespace) -> None:
    doc_text = get_session_document(session_path=args.path)
    if getattr(args, "json", False):
        print(json.dumps({"session_path": args.path, "document_markdown": doc_text}, indent=2))
    else:
        print("\n" + doc_text + "\n")


def cmd_thread(args: argparse.Namespace) -> None:
    thread_text = get_session_thread(session_path=args.path)
    if getattr(args, "json", False):
        print(json.dumps({"session_path": args.path, "thread_markdown": thread_text}, indent=2))
    else:
        print("\n" + thread_text + "\n")


def cmd_export_all(args: argparse.Namespace) -> None:
    out_path = args.out
    md = export_all_timeline(month=args.month, output_path=out_path)
    print(f"[AgentSocket] Exported master session history timeline ({len(md)} chars) to: {out_path}")


def cmd_subskills(args: argparse.Namespace) -> None:
    if not args.subskills_command or args.subskills_command == "list":
        results = list_subskills(query=getattr(args, "query", ""), tags=getattr(args, "tags", None))
        if getattr(args, "json", False):
            print(json.dumps(results, indent=2))
        else:
            print_subskills_table(results)

    elif args.subskills_command == "show":
        details = get_subskill(name=args.name)
        if getattr(args, "json", False):
            print(json.dumps(details, indent=2))
        else:
            print_subskill_details(details)

    elif args.subskills_command == "borrow":
        res = borrow_subskill(
            name=args.name,
            session_title=args.title,
            tab_group_id=args.gid,
            input_file_path=args.input,
        )
        print(json.dumps(res, indent=2))

    elif args.subskills_command == "register":
        tag_list = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        tool_list = [t.strip() for t in args.tools.split(",") if t.strip()] if args.tools else None
        res = register_subskill(
            session_path=args.session,
            name=args.name,
            display_title=args.title,
            description=args.description,
            tags=tag_list,
            adhoc_tools=tool_list,
        )
        print(json.dumps(res, indent=2))


def cmd_progress(args: argparse.Namespace) -> None:
    res = send_progress(
        session_title=args.title,
        step_current=args.current,
        step_total=args.total,
        step_title=args.step_title,
    )
    print(json.dumps(res, indent=2))


def cmd_adhocs(args: argparse.Namespace) -> None:
    print(json.dumps({
        "status": "error",
        "code": "ADHOC_ARCHITECTURE_DEPRECATED",
        "message": (
            "Adhoc script execution has been permanently retired under Spec 33. "
            "All browser automation MUST be driven turn-by-turn using atomic OODA tools "
            "(browser_observe, browser_click, browser_type, browser_scroll, task_complete)."
        )
    }, indent=2))


COMMAND_DISPATCH: dict[str, Callable[[argparse.Namespace], None]] = {
    "status": cmd_status,
    "plug": cmd_plug,
    "start": cmd_plug,
    "navigate": cmd_navigate,
    "eval": cmd_eval,
    "progress": cmd_progress,
    "release": cmd_release,
    "stop": cmd_stop,
    "kill": cmd_kill,
    "history": cmd_history,
    "logs": cmd_logs,
    "doc": cmd_doc,
    "thread": cmd_thread,
    "export-all": cmd_export_all,
    "subskills": cmd_subskills,
}


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentSocket Smart Launcher & CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("status", help="Get gateway & extension socket status")
    subparsers.add_parser("plug", help="Plug in: Ensure gateway & browser are booted and ready")
    subparsers.add_parser("start", help="Alias for 'plug'")

    nav_parser = subparsers.add_parser("navigate", help="Navigate browser tab to URL")
    nav_parser.add_argument("url", help="Target URL to navigate to")
    nav_parser.add_argument("--privacy", action="store_true", help="Force privacy check gate")
    nav_parser.add_argument("--title", default="AgentSocket Task", help="Session title")

    prog_parser = subparsers.add_parser("progress", help="Broadcast progress update to active session HUD")
    prog_parser.add_argument("--title", default="AgentSocket Task", help="Session title")
    prog_parser.add_argument("--current", type=int, required=True, help="Current step number")
    prog_parser.add_argument("--total", type=int, required=True, help="Total step count")
    prog_parser.add_argument("--step-title", default=None, help="Step description or label")

    eval_parser = subparsers.add_parser("eval", help="Execute JavaScript code in active tab")
    eval_parser.add_argument("code", help="JavaScript code string")
    eval_parser.add_argument("--privacy", action="store_true", help="Force privacy check gate")
    eval_parser.add_argument("--title", default="AgentSocket Task", help="Session title")

    rel_parser = subparsers.add_parser("release", help="Release human intervention lockout")
    rel_parser.add_argument("--notes", default="", help="Handoff notes for the agent")

    subparsers.add_parser("stop", help="Stop running tasks and reset state")
    subparsers.add_parser("kill", help="Terminate gateway server background process")

    hist_parser = subparsers.add_parser("history", help="List past browser sessions from index.json")
    hist_parser.add_argument("--month", default=None, help="Filter by month (e.g. 2026-08)")
    hist_parser.add_argument("--query", "-q", default="", help="Search keyword for titles/paths/status")
    hist_parser.add_argument("--limit", type=int, default=10, help="Maximum number of sessions to return")
    hist_parser.add_argument("--json", action="store_true", help="Output raw JSON array")

    logs_parser = subparsers.add_parser("logs", help="Display chronological event thread from session.jsonl")
    logs_parser.add_argument("--path", required=True, help="Session directory path (e.g. server/logs/2026-08-21/...)")
    logs_parser.add_argument("--json", action="store_true", help="Output raw JSON format")

    doc_parser = subparsers.add_parser("doc", help="Display or regenerate consolidated session document")
    doc_parser.add_argument("--path", required=True, help="Session directory path (e.g. server/logs/2026-08-21/...)")
    doc_parser.add_argument("--json", action="store_true", help="Output raw JSON format")

    thread_parser = subparsers.add_parser("thread", help="Display or regenerate standalone execution thread (THREAD.md)")
    thread_parser.add_argument("--path", required=True, help="Session directory path (e.g. server/logs/2026-08-21/...)")
    thread_parser.add_argument("--json", action="store_true", help="Output raw JSON format")

    exp_parser = subparsers.add_parser("export-all", help="Export unified master session timeline to Markdown")
    exp_parser.add_argument("--month", default=None, help="Filter by month (e.g. 2026-08)")
    exp_parser.add_argument("--out", default="./ALL_SESSIONS_TIMELINE.md", help="Output markdown file path")

    subskills_parser = subparsers.add_parser("subskills", help="Manage and borrow reusable browser subskills")
    subskills_sub = subskills_parser.add_subparsers(dest="subskills_command", help="Subskills action")

    sk_list = subskills_sub.add_parser("list", help="List registered subskills")
    sk_list.add_argument("--query", "-q", default="", help="Search keywords")
    sk_list.add_argument("--tags", "-t", default=None, help="Comma-separated tags")
    sk_list.add_argument("--json", action="store_true", help="Output raw JSON")

    sk_show = subskills_sub.add_parser("show", help="Show subskill playbook and details")
    sk_show.add_argument("name", help="Slug name of subskill")
    sk_show.add_argument("--json", action="store_true", help="Output raw JSON")

    sk_borrow = subskills_sub.add_parser("borrow", help="Borrow subskill into active session")
    sk_borrow.add_argument("name", help="Slug name of subskill to borrow")
    sk_borrow.add_argument("--title", required=True, help="Target session title provided by agent")
    sk_borrow.add_argument("--gid", type=int, default=None, help="Target tab group ID")
    sk_borrow.add_argument("--input", default=None, help="Path of input file to copy into input/ folder")
    sk_borrow.add_argument("--json", action="store_true", help="Output raw JSON")

    sk_reg = subskills_sub.add_parser("register", help="Register a session as a reusable subskill")
    sk_reg.add_argument("--session", required=True, help="Path to session folder")
    sk_reg.add_argument("--name", required=True, help="Slug identifier for subskill")
    sk_reg.add_argument("--title", default=None, help="Display title")
    sk_reg.add_argument("--description", default=None, help="Detailed description")
    sk_reg.add_argument("--tags", default=None, help="Comma-separated tags")
    sk_reg.add_argument("--tools", default=None, help="Comma-separated adhoc tool filenames")
    sk_reg.add_argument("--json", action="store_true", help="Output raw JSON")

    return parser


def main() -> None:
    parser = build_cli_parser()
    args = parser.parse_args()
    cmd = args.command or "status"

    handler = COMMAND_DISPATCH.get(cmd)
    if handler:
        try:
            handler(args)
        except KeyboardInterrupt:
            print("\n[AgentSocket] Command cancelled by user.")
            sys.exit(0)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
