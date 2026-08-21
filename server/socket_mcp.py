"""
AgentSocket - Model Context Protocol (MCP) Server
Exposes browser automation and human-in-the-loop socket tools over stdio for MCP clients.
"""

import sys
import os

# Ensure repo root is on Python path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mcp.server import MCPServer
from server import socket_launcher

server = MCPServer("browser-socket")


@server.tool()
def socket_execute(
    action_type: str,
    target_data: str,
    requires_privacy_check: bool = False,
    session_title: str | None = "AgentSocket Task",
) -> dict:
    """
    Ensures gateway and browser extension socket are plugged in, then executes a browser action.
    
    Parameters:
    - action_type: 'navigate' to load a URL, or 'execute_js' to run JavaScript in the active tab.
    - target_data: The target URL (for navigate) or JS expression string (for execute_js).
    - requires_privacy_check: Set to True if this step enters a sensitive scope (e.g. login/payment) requiring immediate human takeover.
    - session_title: Optional label for the tab session group.
    """
    return socket_launcher.execute_action(
        action_type=action_type,
        target_data=target_data,
        requires_privacy_check=requires_privacy_check,
        session_title=session_title,
    )


@server.tool()
def socket_status() -> dict:
    """
    Returns the current gateway socket status, extension connection state, human lockout state, and any intervention notes.
    """
    return socket_launcher.ensure_ready(auto_launch_chrome=False)


@server.tool()
def socket_release_takeover(notes: str = "") -> dict:
    """
    Releases the human operator intervention lockout after completing a manual step in the browser, passing optional handoff notes back to the agent.
    """
    return socket_launcher.release_takeover(notes=notes)


@server.tool()
def socket_stop() -> dict:
    """
    Immediately cancels any active browser automation tasks and resets socket state.
    """
    return socket_launcher.stop_tasks()


@server.tool()
def socket_query_history(
    query_hint: str = "",
    month: str | None = None,
    limit: int = 10
) -> list[dict]:
    """
    Step 1: Scans server/logs/sessions/history_logs/index.json for matching session titles,
    tab group names, status, or date keywords.
    
    Returns lightweight session summary cards and their target session_path.
    """
    return socket_launcher.query_history(
        query_hint=query_hint,
        month=month,
        limit=limit
    )


@server.tool()
def socket_get_session_details(session_path: str) -> dict:
    """
    Step 2: Reads and parses the targeted session.jsonl file from session_path.
    Reconstructs the full chronological thread (step latencies, actions, CDP outputs,
    operator handoff notes, and artifact links) for agent drill-down analysis.
    """
    return socket_launcher.get_session_details(session_path=session_path)


@server.tool()
def socket_get_session_artifact(session_path: str, artifact_name: str) -> dict | str:
    """
    Reads a specific offloaded heavy payload (e.g. scraped JSON data array, DOM HTML dump)
    or returns the absolute file path for a visual screenshot from the session's artifacts/ folder.
    """
    return socket_launcher.get_session_artifact(session_path=session_path, artifact_name=artifact_name)


@server.tool()
def socket_get_session_document(session_path: str) -> str:
    """
    Retrieves or generates the comprehensive consolidated Markdown document (SESSION_DOCUMENT.md / README.md)
    for a given session, including executive overview, playbook summary, inventories of input/output/adhocs/artifacts,
    and the chronological execution timeline thread.
    """
    return socket_launcher.get_session_document(session_path=session_path)


@server.tool()
def socket_list_subskills(query_hint: str = "", tags: str = "") -> list[dict]:
    """
    Step 1 (Subskills): Searches the master registry (subskills_index.json) for reusable tested subskills.
    Returns list of indexed subskills with titles, descriptions, tags, and times borrowed.
    """
    return socket_launcher.list_subskills(query=query_hint, tags=tags)


@server.tool()
def socket_get_subskill(name: str) -> dict:
    """
    Step 2 (Subskills): Retrieves detailed subskill metadata, full playbook contract (sub_skill.md with tested DOM selectors and rules),
    and available adhoc scripts.
    """
    res = socket_launcher.get_subskill(name=name)
    if not res:
        return {"status": "error", "message": f"Subskill '{name}' not found."}
    return res


@server.tool()
def socket_borrow_subskill(
    name: str,
    session_title: str | None = "AgentSocket Task",
    input_file_path: str | None = None
) -> dict:
    """
    Step 3 (Subskills): Clones a subskill's playbook (sub_skill.md) and adhoc tools (adhocs/) into the active
    session workspace, optionally copying input data into input/ folder, incrementing the borrow count, and logging
    a subskill_borrowed event.
    """
    return socket_launcher.borrow_subskill(
        name=name,
        session_title=session_title or "AgentSocket Task",
        input_file_path=input_file_path
    )


@server.tool()
def socket_register_subskill(
    session_path: str,
    name: str,
    display_title: str | None = None,
    description: str | None = None,
    tags: str | None = None,
    adhoc_tools: list[str] | None = None,
) -> dict:
    """
    Step 4 (Subskills): Packages and registers a completed or refined session as a reusable subskill
    into the master registry (subskills_index.json).
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return socket_launcher.register_subskill(
        session_path=session_path,
        name=name,
        display_title=display_title,
        description=description,
        tags=tag_list,
        adhoc_tools=adhoc_tools,
    )


def main():
    """Runs the MCP server over standard I/O (stdio)."""
    server.run("stdio")


if __name__ == "__main__":
    main()


