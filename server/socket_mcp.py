"""
AgentSocket - Model Context Protocol (MCP) Server
Exposes browser automation and human-in-the-loop socket tools over stdio for MCP clients.
"""

from __future__ import annotations
import os
import sys
from typing import Any

# Ensure repo root is on Python path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mcp.server import MCPServer
from server.logger import logger
from server import socket_launcher

server = MCPServer("browser-socket")


# ============================================================================
# Atomic Operator MCP Tools (Spec 24)
# ============================================================================

@server.tool()
def browser_observe(
    tab_group_id: int | None = None,
    take_screenshot: bool = False,
) -> dict[str, Any]:
    """
    Captures ARIA tree, assigns ephemeral numeric badges [1]..[N], and returns structured DOM snapshot.
    """
    try:
        return socket_launcher.browser_observe(
            tab_group_id=tab_group_id,
            take_screenshot=take_screenshot,
        )
    except Exception as e:
        logger.error(f"MCP browser_observe error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def browser_click(
    element_id: int,
    tab_group_id: int | None = None,
    wait_settle: bool = True,
) -> dict[str, Any]:
    """
    Dispatches native focus, mouse/pointer events on the element and awaits adaptive settlement.
    """
    try:
        return socket_launcher.browser_click(
            element_id=element_id,
            tab_group_id=tab_group_id,
            wait_settle=wait_settle,
        )
    except Exception as e:
        logger.error(f"MCP browser_click error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def browser_type(
    element_id: int,
    text: str,
    tab_group_id: int | None = None,
    clear_first: bool = False,
    press_enter: bool = False,
) -> dict[str, Any]:
    """
    Sets element value via prototype setter, dispatches change events, and settles.
    """
    try:
        return socket_launcher.browser_type(
            element_id=element_id,
            text=text,
            tab_group_id=tab_group_id,
            clear_first=clear_first,
            press_enter=press_enter,
        )
    except Exception as e:
        logger.error(f"MCP browser_type error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def browser_scroll(
    direction: str,
    amount: int | None = None,
    tab_group_id: int | None = None,
) -> dict[str, Any]:
    """
    Scrolls viewport ("down", "up", "top", "bottom").
    """
    try:
        return socket_launcher.browser_scroll(
            direction=direction,
            amount=amount,
            tab_group_id=tab_group_id,
        )
    except Exception as e:
        logger.error(f"MCP browser_scroll error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def browser_key_press(
    key: str,
    tab_group_id: int | None = None,
) -> dict[str, Any]:
    """
    Sends native keyboard events ("Enter", "Escape", "Tab", etc.).
    """
    try:
        return socket_launcher.browser_key_press(
            key=key,
            tab_group_id=tab_group_id,
        )
    except Exception as e:
        logger.error(f"MCP browser_key_press error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def browser_screenshot(
    tab_group_id: int | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """
    Captures high-res screenshot (if vision permission granted by user).
    """
    try:
        return socket_launcher.browser_screenshot(
            tab_group_id=tab_group_id,
            filename=filename,
        )
    except Exception as e:
        logger.error(f"MCP browser_screenshot error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def task_complete(
    result: str | None = None,
    status: str = "completed",
    tab_group_id: int | None = None,
) -> dict[str, Any]:
    """
    Concludes task, finalizes session documentation, and resets HUD state.
    """
    try:
        return socket_launcher.task_complete(
            result=result,
            status=status,
            tab_group_id=tab_group_id,
        )
    except Exception as e:
        logger.error(f"MCP task_complete error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def browser_set_milestone(
    milestone_title: str,
    phase_number: int | None = None,
    total_phases: int | None = None,
    tab_group_id: int | None = None,
) -> dict[str, Any]:
    """
    Updates HUD phase badge and intent ticker for complex workflows.
    """
    try:
        return socket_launcher.browser_set_milestone(
            milestone_title=milestone_title,
            phase_number=phase_number,
            total_phases=total_phases,
            tab_group_id=tab_group_id,
        )
    except Exception as e:
        logger.error(f"MCP browser_set_milestone error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def socket_execute(
    action_type: str,
    target_data: str,
    session_title: str,
    requires_privacy_check: bool = False,
) -> dict[str, Any]:
    """
    Ensures gateway and browser extension socket are plugged in, then executes a browser action.

    Parameters:
    - action_type: 'navigate' to load a URL, 'execute_js' to run JavaScript in the active tab, or 'task_complete' to finalize.
    - target_data: The target URL (for navigate) or JS expression string (for execute_js).
    - session_title: Descriptive title provided by the agent for this browser task/tab group.
    - requires_privacy_check: Set to True if this step enters a sensitive scope (e.g. login/payment) requiring immediate human takeover.
    """
    try:
        return socket_launcher.execute_action(
            action_type=action_type,
            target_data=target_data,
            requires_privacy_check=requires_privacy_check,
            session_title=session_title,
        )
    except Exception as e:
        logger.error(f"MCP socket_execute error: {e}")
        return {"status": "error", "message": f"MCP execution failed: {e}"}


@server.tool()
def socket_status() -> dict[str, Any]:
    """
    Returns the current gateway socket status, extension connection state, human lockout state, and any intervention notes.
    """
    try:
        return socket_launcher.ensure_ready(auto_launch_chrome=False)
    except Exception as e:
        logger.error(f"MCP socket_status error: {e}")
        return {"status": "error", "message": str(e), "extension_connected": False, "human_in_control": False}


@server.tool()
def socket_release_takeover(notes: str = "") -> dict[str, Any]:
    """
    Releases the human operator intervention lockout after completing a manual step in the browser, passing optional handoff notes back to the agent.
    """
    try:
        return socket_launcher.release_takeover(notes=notes)
    except Exception as e:
        logger.error(f"MCP socket_release_takeover error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def socket_stop() -> dict[str, Any]:
    """
    Immediately cancels any active browser automation tasks and resets socket state.
    """
    try:
        return socket_launcher.stop_tasks()
    except Exception as e:
        logger.error(f"MCP socket_stop error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def socket_query_history(
    query_hint: str = "",
    month: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Step 1: Scans server/logs/sessions/history_logs/index.json for matching session titles,
    tab group names, status, or date keywords.

    Returns lightweight session summary cards and their target session_path.
    """
    try:
        return socket_launcher.query_history(
            query_hint=query_hint,
            month=month,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"MCP socket_query_history error: {e}")
        return []


@server.tool()
def socket_get_session_details(session_path: str) -> dict[str, Any]:
    """
    Step 2: Reads and parses the targeted session.jsonl file from session_path.
    Reconstructs the full chronological thread (step latencies, actions, CDP outputs,
    operator handoff notes, and artifact links) for agent drill-down analysis.
    """
    try:
        return socket_launcher.get_session_details(session_path=session_path)
    except Exception as e:
        logger.error(f"MCP socket_get_session_details error: {e}")
        return {"status": "error", "message": str(e), "events": []}


@server.tool()
def socket_get_session_artifact(session_path: str, artifact_name: str) -> dict[str, Any] | str:
    """
    Reads a specific offloaded heavy payload (e.g. scraped JSON data array, DOM HTML dump)
    or returns the absolute file path for a visual screenshot from the session's artifacts/ folder.
    """
    try:
        return socket_launcher.get_session_artifact(session_path=session_path, artifact_name=artifact_name)
    except Exception as e:
        logger.error(f"MCP socket_get_session_artifact error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def socket_get_session_document(session_path: str) -> str:
    """
    Retrieves or generates the comprehensive consolidated Markdown document (SESSION_DOCUMENT.md / README.md)
    for a given session, including executive overview, playbook summary, inventories of input/output/adhocs/artifacts,
    and the chronological execution timeline thread.
    """
    try:
        return socket_launcher.get_session_document(session_path=session_path)
    except Exception as e:
        logger.error(f"MCP socket_get_session_document error: {e}")
        return f"*Error retrieving session document: {e}*"


@server.tool()
def socket_list_subskills(query_hint: str = "", tags: str = "") -> list[dict[str, Any]]:
    """
    Step 1 (Subskills): Searches the master registry (subskills_index.json) for reusable tested subskills.
    Returns list of indexed subskills with titles, descriptions, tags, and times borrowed.
    """
    try:
        return socket_launcher.list_subskills(query=query_hint, tags=tags)
    except Exception as e:
        logger.error(f"MCP socket_list_subskills error: {e}")
        return []


@server.tool()
def socket_get_subskill(name: str) -> dict[str, Any]:
    """
    Step 2 (Subskills): Retrieves detailed subskill metadata, full playbook contract (sub_skill.md with tested DOM selectors and rules),
    and available adhoc scripts.
    """
    try:
        res = socket_launcher.get_subskill(name=name)
        if not res:
            return {"status": "error", "message": f"Subskill '{name}' not found."}
        return res
    except Exception as e:
        logger.error(f"MCP socket_get_subskill error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def socket_borrow_subskill(
    name: str,
    session_title: str,
    input_file_path: str | None = None,
) -> dict[str, Any]:
    """
    Step 3 (Subskills): Clones a subskill's playbook (sub_skill.md) and adhoc tools (adhocs/) into the active
    session workspace, optionally copying input data into input/ folder, incrementing the borrow count, and logging
    a subskill_borrowed event.
    """
    try:
        return socket_launcher.borrow_subskill(
            name=name,
            session_title=session_title,
            input_file_path=input_file_path,
        )
    except Exception as e:
        logger.error(f"MCP socket_borrow_subskill error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def socket_register_subskill(
    session_path: str,
    name: str,
    display_title: str | None = None,
    description: str | None = None,
    tags: str | None = None,
    adhoc_tools: list[str] | None = None,
) -> dict[str, Any]:
    """
    Step 4 (Subskills): Packages and registers a completed or refined session as a permanent reusable subskill
    into the master central vault (server/subskills/).
    """
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        return socket_launcher.register_subskill(
            session_path=session_path,
            name=name,
            display_title=display_title,
            description=description,
            tags=tag_list,
            adhoc_tools=adhoc_tools,
        )
    except Exception as e:
        logger.error(f"MCP socket_register_subskill error: {e}")
        return {"status": "error", "message": str(e)}


@server.tool()
def socket_promote_adhoc(
    session_path: str = "",
    tool_name: str = "",
    target_vault: str = "universal",
    subskill_name: str | None = None,
) -> dict[str, Any]:
    """
    [DEPRECATED] Adhoc script promotion is deprecated on this branch.
    Subskills are Markdown SOP playbooks, not Python scripts.
    """
    return {
        "status": "error",
        "deprecated": True,
        "message": (
            "socket_promote_adhoc is deprecated on this branch. "
            "Subskills are now Markdown SOP playbooks (sub_skill.md), not executable Python scripts."
        ),
    }


@server.tool()
def socket_list_adhocs() -> list[dict[str, Any]]:
    """
    [DEPRECATED] Lists adhoc tools. Legacy Python adhocs are deprecated in favor of atomic operator tools.
    """
    return []


@server.tool()
def socket_run_adhoc(
    tool_name: str,
    session_path: str | None = None,
    args: list[str] | None = None,
) -> dict[str, Any]:
    """
    [DEPRECATED] Adhoc script execution is deprecated on this branch.
    Use atomic operator tools (browser_observe, browser_click, browser_type, browser_scroll, browser_key_press) instead.
    """
    return {
        "status": "warning",
        "deprecated": True,
        "message": (
            f"socket_run_adhoc is deprecated on this branch. Please use atomic operator tools instead: "
            "browser_observe, browser_click, browser_type, browser_scroll, browser_key_press."
        ),
    }


def main() -> None:
    """Runs the MCP server over standard I/O (stdio)."""
    server.run("stdio")


if __name__ == "__main__":
    main()
