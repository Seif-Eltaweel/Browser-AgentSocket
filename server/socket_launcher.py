"""
AgentSocket - Smart Launcher & Subsystem Manager
Handles on-demand gateway boot, extension health checks, process lifecycle, and Chrome auto-launch.
"""

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import uuid
from typing import Optional
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

from server.models import (
    ActionType,
    ResponseStatus,
    ErrorCode
)
from server.session_manager import session_manager

EXTENSION_DIR = os.path.join(REPO_ROOT, "extension")
PID_FILE_PATH = os.path.join(REPO_ROOT, ".socket_server.pid")
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"


def is_pid_running(pid: int) -> bool:
    """Checks if a given process ID is actively executing on the OS."""
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                text=True
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


def clean_stale_pid_file():
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


def find_chrome_path() -> Optional[str]:
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
        resp = requests.get(f"{server_url}/status", timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


def get_gateway_status(server_url: str = DEFAULT_SERVER_URL) -> dict:
    """Fetches the current status payload from the gateway server."""
    clean_stale_pid_file()
    try:
        resp = requests.get(f"{server_url}/status", timeout=2.0)
        if resp.status_code == 200:
            return resp.json()
        return {"status": "error", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "offline", "error": str(e), "extension_connected": False, "human_in_control": False}


def ensure_server_running(port: int = 8000, timeout: float = 8.0) -> bool:
    """Ensures the FastAPI gateway server is running, booting it in the background if needed."""
    clean_stale_pid_file()
    server_url = f"http://127.0.0.1:{port}"
    if is_server_running(server_url):
        return True

    print(f"[AgentSocket] Gateway server not detected on port {port}. Spawning background socket process...")
    cmd = [sys.executable, "-m", "uvicorn", "server.socket_server:app", "--port", str(port), "--host", "127.0.0.1"]

    creation_flags = 0
    if platform.system() == "Windows":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000 | 0x00000008

    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        start_new_session=(platform.system() != "Windows"),
    )

    # Save PID
    try:
        with open(PID_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except Exception as e:
        print(f"[AgentSocket] Warning: Could not write PID file: {e}")

    # Wait for server to become live
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_server_running(server_url):
            print(f"[AgentSocket] Gateway server is live on {server_url} (PID: {proc.pid}).")
            return True
        time.sleep(0.3)

    print(f"[AgentSocket] Error: Gateway server failed to start within {timeout}s.")
    return False


def launch_chrome_with_extension(extension_dir: str = EXTENSION_DIR, timeout: float = 6.0) -> bool:
    """Launches Chrome with the AgentSocket unpacked extension loaded."""
    chrome_bin = find_chrome_path()
    if not chrome_bin:
        print("[AgentSocket] Error: Could not locate Chrome or Chromium on this system.")
        return False

    abs_ext_dir = os.path.abspath(extension_dir)
    print(f"[AgentSocket] Launching Chrome ({chrome_bin}) with extension: {abs_ext_dir}")

    chrome_cmd = [
        chrome_bin,
        f"--load-extension={abs_ext_dir}",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    creation_flags = 0
    if platform.system() == "Windows":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000 | 0x00000008

    subprocess.Popen(
        chrome_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        start_new_session=(platform.system() != "Windows"),
    )

    # Poll server to verify WebSocket connection
    start_time = time.time()
    while time.time() - start_time < timeout:
        status = get_gateway_status()
        if status.get("extension_connected"):
            print("[AgentSocket] Chrome Extension plugged in successfully to gateway socket.")
            return True
        time.sleep(0.5)

    print("[AgentSocket] Notice: Chrome launched. Awaiting extension WebSocket handshake.")
    return True


def ensure_ready(server_url: str = DEFAULT_SERVER_URL, auto_launch_chrome: bool = True) -> dict:
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
                "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": "Server process did not become healthy."}
            }

    status = get_gateway_status(server_url)
    if not status.get("extension_connected") and auto_launch_chrome:
        print("[AgentSocket] Extension not connected. Triggering auto-launch for Chrome...")
        launch_chrome_with_extension()
        status = get_gateway_status(server_url)

    return status


def execute_action(
    action_type: str,
    target_data: str,
    requires_privacy_check: bool = False,
    session_title: Optional[str] = "AgentSocket Task",
    group_color: Optional[str] = "purple",
    server_url: str = DEFAULT_SERVER_URL,
) -> dict:
    """Ensures environment is ready and sends action payload to /execute."""
    ensure_ready(server_url)
    payload = {
        "id": str(uuid.uuid4()),
        "action_type": action_type,
        "target_data": target_data,
        "requires_privacy_check": requires_privacy_check,
        "session_title": session_title,
        "group_color": group_color,
    }
    try:
        resp = requests.post(f"{server_url}/execute", json=payload, timeout=35.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Execution request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)}
        }


def release_takeover(notes: str = "", server_url: str = DEFAULT_SERVER_URL) -> dict:
    """Releases human intervention lockout."""
    ensure_ready(server_url, auto_launch_chrome=False)
    try:
        resp = requests.post(f"{server_url}/human_release", json={"notes": notes}, timeout=5.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Human release request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)}
        }


def stop_tasks(server_url: str = DEFAULT_SERVER_URL) -> dict:
    """Stops active tasks and resets state."""
    ensure_ready(server_url, auto_launch_chrome=False)
    try:
        resp = requests.post(f"{server_url}/stop", timeout=5.0)
        return resp.json()
    except Exception as e:
        return {
            "status": ResponseStatus.ERROR.value,
            "message": f"Stop request failed: {e}",
            "error": {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)}
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
            print(f"[AgentSocket] Terminated server PID {pid}.")
        except Exception as e:
            print(f"[AgentSocket] Error killing PID {pid}: {e}")

    if os.path.exists(PID_FILE_PATH):
        try:
            os.remove(PID_FILE_PATH)
        except Exception:
            pass
    return True


# ============================================================================
# Session History & Introspection Helpers (Spec 11)
# ============================================================================
def query_history(
    query_hint: str = "",
    month: Optional[str] = None,
    limit: int = 10,
    server_url: str = DEFAULT_SERVER_URL,
) -> list[dict]:
    """Queries past sessions from server or directly via SessionManager."""
    if is_server_running(server_url):
        try:
            params = {"query": query_hint, "limit": limit}
            if month:
                params["month"] = month
            resp = requests.get(f"{server_url}/history", params=params, timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return session_manager.query_history(query_hint=query_hint, month=month, limit=limit)


def get_session_details(session_path: str, server_url: str = DEFAULT_SERVER_URL) -> dict:
    """Retrieves full chronological events thread for a session."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/session/details", params={"path": session_path}, timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return session_manager.get_session_details(session_path=session_path)


def get_session_artifact(session_path: str, artifact_name: str, server_url: str = DEFAULT_SERVER_URL) -> dict | str:
    """Retrieves an offloaded payload or artifact path."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/session/artifact", params={"path": session_path, "name": artifact_name}, timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return session_manager.get_session_artifact(session_path=session_path, artifact_name=artifact_name)


def get_session_document(session_path: str, server_url: str = DEFAULT_SERVER_URL) -> str:
    """Generates and retrieves the full consolidated session document."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/session/document", params={"path": session_path}, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("document_markdown", "")
        except Exception:
            pass
    return session_manager.generate_session_document(session_dir_or_path=session_path)


def export_all_timeline(month: Optional[str] = None, output_path: Optional[str] = None) -> str:
    """Exports master history report to Markdown."""
    return session_manager.export_all_to_markdown(month=month, output_path=output_path)


# ============================================================================
# Subskills & Borrowing Engine Helpers (Spec 13)
# ============================================================================
def list_subskills(
    query: str = "",
    tags: Optional[str] = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> list[dict]:
    """Lists registered subskills from gateway server or session_manager."""
    if is_server_running(server_url):
        try:
            params = {}
            if query:
                params["query"] = query
            if tags:
                params["tags"] = tags
            resp = requests.get(f"{server_url}/subskills", params=params, timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return session_manager.list_subskills(query=query, tags=tag_list)


def get_subskill(name: str, server_url: str = DEFAULT_SERVER_URL) -> Optional[dict]:
    """Retrieves detailed subskill info including playbook markdown."""
    if is_server_running(server_url):
        try:
            resp = requests.get(f"{server_url}/subskills/{name}", timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    return data.get("data")
        except Exception:
            pass
    return session_manager.get_subskill(name=name)


def borrow_subskill(
    name: str,
    session_title: Optional[str] = "AgentSocket Task",
    tab_group_id: Optional[int] = None,
    input_file_path: Optional[str] = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict:
    """Borrows a subskill into an active session workspace."""
    if is_server_running(server_url):
        try:
            payload = {
                "name": name,
                "session_title": session_title,
                "tab_group_id": tab_group_id,
                "input_file_path": input_file_path,
            }
            resp = requests.post(f"{server_url}/subskills/borrow", json=payload, timeout=8.0)
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
    display_title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    adhoc_tools: Optional[list[str]] = None,
    subskill_markdown: Optional[str] = None,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict:
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
            resp = requests.post(f"{server_url}/subskills/register", json=payload, timeout=8.0)
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


def print_history_table(summaries: list[dict]):
    """Formats session summaries into a clean ASCII table."""
    if not summaries:
        print("\n[History] No recorded browser sessions found.\n")
        return

    print("\n" + "=" * 110)
    print(f"{'SESSION ID':<30} | {'TAB GROUP':<25} | {'STATUS':<10} | {'DUR(s)':<8} | {'ACTS':<5} | {'TAKOVR':<6} | {'PATH'}")
    print("=" * 110)
    for s in summaries:
        sid = s.get("session_id", "")[:28]
        title = s.get("tab_group_name", "")[:23]
        status = s.get("status", "")[:9]
        dur_ms = s.get("duration_ms")
        dur_str = f"{dur_ms/1000.0:.1f}s" if dur_ms else "N/A"
        acts = str(s.get("action_count", 0))
        tak = str(s.get("takeover_count", 0))
        spath = s.get("session_path", "")
        print(f"{sid:<30} | {title:<25} | {status:<10} | {dur_str:<8} | {acts:<5} | {tak:<6} | {spath}")
    print("=" * 110 + "\n")


def print_subskills_table(subskills: list[dict]):
    """Formats subskills into a clean ASCII table."""
    if not subskills:
        print("\n[Subskills] No registered subskills found.\n")
        return

    print("\n" + "=" * 115)
    print(f"{'SUBSKILL NAME':<26} | {'DISPLAY TITLE':<30} | {'BORROWED':<9} | {'TAGS':<20} | {'LATEST SESSION'}")
    print("=" * 115)
    for s in subskills:
        name = s.get("name", "")[:25]
        title = s.get("display_title", "")[:28]
        borrowed = str(s.get("times_borrowed", 0))
        tags_str = ", ".join(s.get("tags", []))[:18]
        path = s.get("latest_session_path", "")
        print(f"{name:<26} | {title:<30} | {borrowed:<9} | {tags_str:<20} | {path}")
    print("=" * 115 + "\n")


def print_subskill_details(details: dict):
    """Displays formatted details of a single subskill."""
    if not details:
        print("\n[Subskills] Subskill not found.\n")
        return

    name = details.get("name", "")
    title = details.get("display_title", "")
    desc = details.get("description", "")
    tags = ", ".join(details.get("tags", []))
    borrowed = details.get("times_borrowed", 0)
    sess_path = details.get("latest_session_path", "")
    tools = details.get("available_adhoc_tools", [])
    playbook = details.get("playbook_markdown", "")

    print("\n" + "=" * 80)
    print(f"📦 Subskill: {title} (`{name}`)")
    print("=" * 80)
    print(f"• Description   : {desc}")
    print(f"• Tags          : {tags}")
    print(f"• Times Borrowed: {borrowed}")
    print(f"• Source Session: {sess_path}")
    print(f"• Adhoc Tools   : {', '.join(tools) if tools else 'None'}")
    print("-" * 80)
    print("📖 Playbook Contract (sub_skill.md):")
    print(playbook if playbook else "*No playbook markdown content.*")
    print("=" * 80 + "\n")


def print_session_logs(details: dict):
    """Formats session.jsonl events into a tree-structured chronological thread."""
    if details.get("status") == "error":
        print(f"\n[Logs Error] {details.get('message')}\n")
        return

    formatted_thread = details.get("formatted_thread")
    if not formatted_thread:
        formatted_thread = session_manager.format_session_thread(details)

    try:
        print("\n" + formatted_thread + "\n")
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_str = formatted_thread.encode(enc, errors="replace").decode(enc)
        print("\n" + safe_str + "\n")


def main():
    parser = argparse.ArgumentParser(description="AgentSocket Smart Launcher & CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status
    subparsers.add_parser("status", help="Get gateway & extension socket status")

    # plug / start
    subparsers.add_parser("plug", help="Plug in: Ensure gateway & browser are booted and ready")
    subparsers.add_parser("start", help="Alias for 'plug'")

    # navigate
    nav_parser = subparsers.add_parser("navigate", help="Navigate browser tab to URL")
    nav_parser.add_argument("url", help="Target URL to navigate to")
    nav_parser.add_argument("--privacy", action="store_true", help="Force privacy check gate")
    nav_parser.add_argument("--title", default="AgentSocket Task", help="Session title")

    # eval
    eval_parser = subparsers.add_parser("eval", help="Execute JavaScript code in active tab")
    eval_parser.add_argument("code", help="JavaScript code string")
    eval_parser.add_argument("--privacy", action="store_true", help="Force privacy check gate")
    eval_parser.add_argument("--title", default="AgentSocket Task", help="Session title")

    # release
    rel_parser = subparsers.add_parser("release", help="Release human intervention lockout")
    rel_parser.add_argument("--notes", default="", help="Handoff notes for the agent")

    # stop
    subparsers.add_parser("stop", help="Stop running tasks and reset state")

    # kill
    subparsers.add_parser("kill", help="Terminate gateway server background process")

    # history
    hist_parser = subparsers.add_parser("history", help="List past browser sessions from index.json")
    hist_parser.add_argument("--month", default=None, help="Filter by month (e.g. 2026-08)")
    hist_parser.add_argument("--query", "-q", default="", help="Search keyword for titles/paths/status")
    hist_parser.add_argument("--limit", type=int, default=10, help="Maximum number of sessions to return")
    hist_parser.add_argument("--json", action="store_true", help="Output raw JSON array")

    # logs
    logs_parser = subparsers.add_parser("logs", help="Display chronological event thread from session.jsonl")
    logs_parser.add_argument("--path", required=True, help="Session directory path (e.g. server/logs/2026-08-21/...)")
    logs_parser.add_argument("--json", action="store_true", help="Output raw JSON format")

    # doc
    doc_parser = subparsers.add_parser("doc", help="Display or regenerate consolidated session document (SESSION_DOCUMENT.md)")
    doc_parser.add_argument("--path", required=True, help="Session directory path (e.g. server/logs/2026-08-21/...)")
    doc_parser.add_argument("--json", action="store_true", help="Output raw JSON format")

    # export-all
    exp_parser = subparsers.add_parser("export-all", help="Export unified master session timeline to Markdown")
    exp_parser.add_argument("--month", default=None, help="Filter by month (e.g. 2026-08)")
    exp_parser.add_argument("--out", default="./ALL_SESSIONS_TIMELINE.md", help="Output markdown file path")

    # subskills
    subskills_parser = subparsers.add_parser("subskills", help="Manage and borrow reusable browser subskills")
    subskills_sub = subskills_parser.add_subparsers(dest="subskills_command", help="Subskills action")

    # subskills list
    sk_list = subskills_sub.add_parser("list", help="List registered subskills")
    sk_list.add_argument("--query", "-q", default="", help="Search keywords")
    sk_list.add_argument("--tags", "-t", default=None, help="Comma-separated tags")
    sk_list.add_argument("--json", action="store_true", help="Output raw JSON")

    # subskills show
    sk_show = subskills_sub.add_parser("show", help="Show subskill playbook and details")
    sk_show.add_argument("name", help="Slug name of subskill")
    sk_show.add_argument("--json", action="store_true", help="Output raw JSON")

    # subskills borrow
    sk_borrow = subskills_sub.add_parser("borrow", help="Borrow subskill into active session")
    sk_borrow.add_argument("name", help="Slug name of subskill to borrow")
    sk_borrow.add_argument("--title", default="AgentSocket Task", help="Target session title")
    sk_borrow.add_argument("--gid", type=int, default=None, help="Target tab group ID")
    sk_borrow.add_argument("--input", default=None, help="Path of input file to copy into input/ folder")
    sk_borrow.add_argument("--json", action="store_true", help="Output raw JSON")

    # subskills register
    sk_reg = subskills_sub.add_parser("register", help="Register a session as a reusable subskill")
    sk_reg.add_argument("--session", required=True, help="Path to session folder")
    sk_reg.add_argument("--name", required=True, help="Slug identifier for subskill")
    sk_reg.add_argument("--title", default=None, help="Display title")
    sk_reg.add_argument("--description", default=None, help="Detailed description")
    sk_reg.add_argument("--tags", default=None, help="Comma-separated tags")
    sk_reg.add_argument("--tools", default=None, help="Comma-separated adhoc tool filenames")
    sk_reg.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    try:
        if not args.command or args.command == "status":
            status = get_gateway_status()
            print(json.dumps(status, indent=2))

        elif args.command in ("plug", "start"):
            status = ensure_ready()
            print(json.dumps(status, indent=2))

        elif args.command == "navigate":
            res = execute_action("navigate", args.url, requires_privacy_check=args.privacy, session_title=args.title)
            print(json.dumps(res, indent=2))

        elif args.command == "eval":
            res = execute_action("execute_js", args.code, requires_privacy_check=args.privacy, session_title=args.title)
            print(json.dumps(res, indent=2))

        elif args.command == "release":
            res = release_takeover(args.notes)
            print(json.dumps(res, indent=2))

        elif args.command == "stop":
            res = stop_tasks()
            print(json.dumps(res, indent=2))

        elif args.command == "kill":
            kill_server()

        elif args.command == "history":
            results = query_history(query_hint=args.query, month=args.month, limit=args.limit)
            if getattr(args, "json", False):
                print(json.dumps(results, indent=2))
            else:
                print_history_table(results)

        elif args.command == "logs":
            details = get_session_details(session_path=args.path)
            if getattr(args, "json", False):
                print(json.dumps(details, indent=2))
            else:
                print_session_logs(details)

        elif args.command == "doc":
            doc_text = get_session_document(session_path=args.path)
            if getattr(args, "json", False):
                print(json.dumps({"session_path": args.path, "document_markdown": doc_text}, indent=2))
            else:
                print("\n" + doc_text + "\n")

        elif args.command == "export-all":
            out_path = args.out
            md = export_all_timeline(month=args.month, output_path=out_path)
            print(f"[AgentSocket] Exported master session history timeline ({len(md)} chars) to: {out_path}")

        elif args.command == "subskills":
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

    except KeyboardInterrupt:
        print("\n[AgentSocket] Command cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()


