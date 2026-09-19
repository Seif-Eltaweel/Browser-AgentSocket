"""
Unit tests for Feature Spec 24: Atomic Operator MCP Tools & Legacy Script Deprecation.
Verifies MCP tool registry, atomic operator schemas, deprecation warnings, and gateway/launcher integration.
"""

import asyncio
import json
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from server import socket_mcp, socket_launcher
from server.socket_server import app, state
from server.models import ResponseStatus, SessionStatus, SessionEventType
from server.session import session_manager


class TestAtomicMCPTools(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.client.headers.update({"X-AgentSocket-Token": state.server_token})
        state.human_in_control = False
        state.last_intervention_notes = None
        state.extension_ws = None
        state.tab_sessions.clear()
        state.pending_responses.clear()
        state.global_permissions = {"enable_subskills": True, "enable_vision": False}
        state.session_permissions.clear()

    def test_mcp_tool_inventory_contains_all_atomic_tools(self):
        """Verifies that all 8 atomic operator tools are registered on the MCPServer."""
        tools = asyncio.run(socket_mcp.server.list_tools())
        tool_names = {t.name for t in tools}

        expected_atomic_tools = {
            "browser_observe",
            "browser_click",
            "browser_type",
            "browser_scroll",
            "browser_key_press",
            "browser_screenshot",
            "task_complete",
            "browser_set_milestone",
        }
        for tool_name in expected_atomic_tools:
            self.assertIn(tool_name, tool_names, f"Expected atomic tool '{tool_name}' to be registered.")

    def test_mcp_tool_schemas(self):
        """Verifies that atomic tools have correct parameter schemas."""
        tools = {t.name: t for t in asyncio.run(socket_mcp.server.list_tools())}

        # browser_observe
        obs_props = tools["browser_observe"].input_schema.get("properties", {})
        self.assertIn("tab_group_id", obs_props)
        self.assertIn("take_screenshot", obs_props)

        # browser_click
        click_props = tools["browser_click"].input_schema.get("properties", {})
        self.assertIn("element_id", click_props)
        self.assertIn("tab_group_id", click_props)
        self.assertIn("wait_settle", click_props)

        # browser_type
        type_props = tools["browser_type"].input_schema.get("properties", {})
        self.assertIn("element_id", type_props)
        self.assertIn("text", type_props)
        self.assertIn("tab_group_id", type_props)
        self.assertIn("clear_first", type_props)
        self.assertIn("press_enter", type_props)

        # browser_scroll
        scroll_props = tools["browser_scroll"].input_schema.get("properties", {})
        self.assertIn("direction", scroll_props)
        self.assertIn("amount", scroll_props)
        self.assertIn("tab_group_id", scroll_props)

        # browser_key_press
        key_props = tools["browser_key_press"].input_schema.get("properties", {})
        self.assertIn("key", key_props)
        self.assertIn("tab_group_id", key_props)

        # browser_screenshot
        snap_props = tools["browser_screenshot"].input_schema.get("properties", {})
        self.assertIn("tab_group_id", snap_props)
        self.assertIn("filename", snap_props)

        # task_complete
        tc_props = tools["task_complete"].input_schema.get("properties", {})
        self.assertIn("result", tc_props)
        self.assertIn("status", tc_props)
        self.assertIn("tab_group_id", tc_props)

        # browser_set_milestone
        ms_props = tools["browser_set_milestone"].input_schema.get("properties", {})
        self.assertIn("milestone_title", ms_props)
        self.assertIn("phase_number", ms_props)
        self.assertIn("total_phases", ms_props)
        self.assertIn("tab_group_id", ms_props)

    def test_legacy_adhoc_tools_purged_from_mcp(self):
        """Spec 33: Verifies that adhoc script execution tools are completely removed from MCP registration."""
        tool_names = [t.name for t in asyncio.run(socket_mcp.server.list_tools())]
        self.assertNotIn("socket_run_adhoc", tool_names)
        self.assertNotIn("socket_promote_adhoc", tool_names)
        self.assertNotIn("socket_list_adhocs", tool_names)

    def test_gateway_screenshot_vision_disabled(self):
        """Verifies that /screenshot returns denied when vision permission is disabled."""
        state.global_permissions["enable_vision"] = False
        resp = self.client.post("/screenshot", json={"tab_group_id": 101, "filename": "test.png"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "denied")
        self.assertEqual(data["error"]["code"], "VISION_DISABLED")

    def test_gateway_screenshot_success(self):
        """Verifies that /screenshot succeeds and dispatches to extension when vision enabled."""
        state.global_permissions["enable_vision"] = True

        class MockWS:
            async def send_text(self, text):
                frame = json.loads(text)
                req_id = frame.get("id")
                if req_id in state.pending_responses:
                    fut = state.pending_responses[req_id]
                    fut.set_result({
                        "status": "success",
                        "data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                    })

        state.extension_ws = MockWS()
        resp = self.client.post("/screenshot", json={"tab_group_id": 201, "filename": "sample_shot.png"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("screenshot_path", data)

    def test_gateway_task_complete(self):
        """Verifies that /task_complete concludes session and returns success."""
        # Create a session to finalize
        session = session_manager.get_or_create_session(
            tab_group_id=505,
            tab_group_name="Checkout Flow",
            agent_name="TestAgent"
        )
        self.assertIn(505, session_manager.active_sessions)

        resp = self.client.post("/task_complete", json={
            "tab_group_id": 505,
            "result": "Items purchased successfully",
            "status": "completed"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["tab_group_id"], 505)

        # Verify session is finalized
        self.assertNotIn(505, session_manager.active_sessions)

    def test_launcher_helpers(self):
        """Verifies that launcher client helper functions call endpoints or handle errors cleanly."""
        with patch("server.socket_launcher.ensure_ready") as mock_ready:
            mock_ready.return_value = {"status": "ok"}
            with patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"status": "success"}
                mock_post.return_value = mock_resp

                # Test each launcher helper
                r_obs = socket_launcher.browser_observe(tab_group_id=1)
                self.assertEqual(r_obs["status"], "success")

                r_click = socket_launcher.browser_click(element_id=4, tab_group_id=1)
                self.assertEqual(r_click["status"], "success")

                r_type = socket_launcher.browser_type(element_id=2, text="hello", tab_group_id=1)
                self.assertEqual(r_type["status"], "success")

                r_scroll = socket_launcher.browser_scroll(direction="down", tab_group_id=1)
                self.assertEqual(r_scroll["status"], "success")

                r_key = socket_launcher.browser_key_press(key="Enter", tab_group_id=1)
                self.assertEqual(r_key["status"], "success")

                r_snap = socket_launcher.browser_screenshot(tab_group_id=1)
                self.assertEqual(r_snap["status"], "success")

                r_tc = socket_launcher.task_complete(result="Done", tab_group_id=1)
                self.assertEqual(r_tc["status"], "success")

                r_ms = socket_launcher.browser_set_milestone("Searching...", phase_number=1, total_phases=3, tab_group_id=1)
                self.assertEqual(r_ms["status"], "success")


if __name__ == "__main__":
    unittest.main()
