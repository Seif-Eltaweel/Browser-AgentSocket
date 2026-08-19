"""
Agent Bro Hands - Model Context Protocol (MCP) Server
Exposes browser automation and human-in-the-loop control tools over stdio for MCP clients.
"""

import sys
import os

# Ensure repo root is on Python path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mcp.server import MCPServer
from server import bro_launcher

server = MCPServer("bro-hands")


@server.tool()
def bro_execute(
    action_type: str,
    target_data: str,
    requires_privacy_check: bool = False,
    session_title: str | None = "MCP Automation",
) -> dict:
    """
    Ensures gateway and browser extension are alive, then executes a browser action.
    
    Parameters:
    - action_type: 'navigate' to load a URL, or 'execute_js' to run JavaScript in the active tab.
    - target_data: The target URL (for navigate) or JS expression string (for execute_js).
    - requires_privacy_check: Set to True if this step enters a sensitive scope (e.g. login/payment) requiring immediate human takeover.
    - session_title: Optional label for the tab session group.
    """
    return bro_launcher.execute_action(
        action_type=action_type,
        target_data=target_data,
        requires_privacy_check=requires_privacy_check,
        session_title=session_title,
    )


@server.tool()
def bro_status() -> dict:
    """
    Returns the current gateway status, extension connection state, human lockout state, and any intervention notes.
    """
    return bro_launcher.ensure_ready(auto_launch_chrome=False)


@server.tool()
def bro_release_takeover(notes: str = "") -> dict:
    """
    Releases the human operator intervention lockout after completing a manual step in the browser, passing optional handoff notes back to the agent.
    """
    return bro_launcher.release_takeover(notes=notes)


@server.tool()
def bro_stop() -> dict:
    """
    Immediately cancels any active browser automation tasks and resets state.
    """
    return bro_launcher.stop_tasks()


def main():
    """Runs the MCP server over standard I/O (stdio)."""
    server.run("stdio")


if __name__ == "__main__":
    main()
