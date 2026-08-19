"""
Agent Bro Hands - Smart Launcher & Subsystem Manager
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

from server.models import (
    ActionType,
    ResponseStatus,
    ErrorCode
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTENSION_DIR = os.path.join(REPO_ROOT, "extension")
PID_FILE_PATH = os.path.join(REPO_ROOT, ".bro_pid")
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"


def is_pid_running(pid: int) -> bool:
    """Checks if a given process ID is actively executing on the OS."""
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            # Query tasklist with CSV output
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

    print(f"[Launcher] Gateway server not detected on port {port}. Spawning background process...")
    cmd = [sys.executable, "-m", "uvicorn", "server.bro_server:app", "--port", str(port), "--host", "127.0.0.1"]

    creation_flags = 0
    if platform.system() == "Windows":
        # CREATE_NEW_PROCESS_GROUP (0x200) | CREATE_NO_WINDOW (0x08000000) | DETACHED_PROCESS (0x8)
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
        print(f"[Launcher] Warning: Could not write PID file: {e}")

    # Wait for server to become live
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_server_running(server_url):
            print(f"[Launcher] Gateway server is live on {server_url} (PID: {proc.pid}).")
            return True
        time.sleep(0.3)

    print(f"[Launcher] Error: Gateway server failed to start within {timeout}s.")
    return False


def launch_chrome_with_extension(extension_dir: str = EXTENSION_DIR, timeout: float = 6.0) -> bool:
    """Launches Chrome with the Agent Bro Hands unpacked extension loaded."""
    chrome_bin = find_chrome_path()
    if not chrome_bin:
        print("[Launcher] Error: Could not locate Chrome or Chromium on this system.")
        return False

    abs_ext_dir = os.path.abspath(extension_dir)
    print(f"[Launcher] Launching Chrome ({chrome_bin}) with extension: {abs_ext_dir}")

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
            print("[Launcher] Chrome Extension connected successfully to gateway bridge.")
            return True
        time.sleep(0.5)

    print("[Launcher] Notice: Chrome launched. Awaiting extension WebSocket handshake.")
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
        print("[Launcher] Extension not connected. Triggering auto-launch for Chrome...")
        launch_chrome_with_extension()
        status = get_gateway_status(server_url)

    return status


def execute_action(
    action_type: str,
    target_data: str,
    requires_privacy_check: bool = False,
    session_title: Optional[str] = "Agent Automation",
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
            print(f"[Launcher] Terminated server PID {pid}.")
        except Exception as e:
            print(f"[Launcher] Error killing PID {pid}: {e}")

    if os.path.exists(PID_FILE_PATH):
        try:
            os.remove(PID_FILE_PATH)
        except Exception:
            pass
    return True


def main():
    parser = argparse.ArgumentParser(description="Agent Bro Hands Smart Launcher & CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status
    subparsers.add_parser("status", help="Get gateway & extension status")

    # start
    subparsers.add_parser("start", help="Ensure gateway & browser are booted and ready")

    # navigate
    nav_parser = subparsers.add_parser("navigate", help="Navigate browser tab to URL")
    nav_parser.add_argument("url", help="Target URL to navigate to")
    nav_parser.add_argument("--privacy", action="store_true", help="Force privacy check gate")
    nav_parser.add_argument("--title", default="Agent Automation", help="Session title")

    # eval
    eval_parser = subparsers.add_parser("eval", help="Execute JavaScript code in active tab")
    eval_parser.add_argument("code", help="JavaScript code string")
    eval_parser.add_argument("--privacy", action="store_true", help="Force privacy check gate")
    eval_parser.add_argument("--title", default="Agent Automation", help="Session title")

    # release
    rel_parser = subparsers.add_parser("release", help="Release human intervention lockout")
    rel_parser.add_argument("--notes", default="", help="Handoff notes for the agent")

    # stop
    subparsers.add_parser("stop", help="Stop running tasks and reset state")

    # kill
    subparsers.add_parser("kill", help="Terminate gateway server background process")

    args = parser.parse_args()

    try:
        if not args.command or args.command == "status":
            status = get_gateway_status()
            print(json.dumps(status, indent=2))

        elif args.command == "start":
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
    except KeyboardInterrupt:
        print("\n[Launcher] Command cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
