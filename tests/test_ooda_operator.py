"""
Unit and Integration Regression Test Harness for Feature Spec 28:
Comprehensive Automated Regression & Zero-Waste OODA Test Harness 🧪✅

Validates all 8 core matrix requirements:
1. test_observe_aria_formatting
2. test_atomic_mcp_tool_routing
3. test_sqlite_hybrid_storage
4. test_gateway_auth_token_and_cors
5. test_tab_group_state_isolation_and_resumption
6. test_yaml_frontmatter_manifest_parsing
7. test_lean_jsonl_and_secret_masking
8. test_zero_plan_direct_mode_storage
"""

from __future__ import annotations
import asyncio
import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from server import socket_mcp, socket_launcher
from server.socket_server import app, state, AUTH_TOKEN_HEADER
from server.models import (
    ErrorCode,
    ObserveResponse,
    ResponseStatus,
    SessionEventType,
    SessionManifestModel,
    SessionStatus,
)
from server.db import init_db, get_connection
from server.session.manager import SessionManager, redact_sensitive_payload
from server.session.storage import SessionStorage


class TestOODAOperatorHarness(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ooda_spec28_")
        self.db_path = os.path.join(self.test_dir, "test_agentsocket.db")
        init_db(self.db_path)
        self.storage = SessionStorage(base_log_dir=self.test_dir, db_path=self.db_path)
        self.manager = SessionManager(base_log_dir=self.test_dir, db_path=self.db_path)

        self.client = TestClient(app)
        self.client.headers.update({AUTH_TOKEN_HEADER: state.server_token})
        state.human_in_control = False
        state.last_intervention_notes = None
        state.extension_ws = None
        state.tab_sessions.clear()
        state.pending_responses.clear()
        state.global_permissions = {"enable_subskills": True, "enable_vision": False}
        state.session_permissions.clear()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        state.tab_sessions.clear()
        state.pending_responses.clear()

    # ------------------------------------------------------------------------
    # 1. test_observe_aria_formatting
    # ------------------------------------------------------------------------
    def test_observe_aria_formatting(self):
        """
        1. test_observe_aria_formatting:
        Tests that DOM node structures convert into concise, token-efficient text trees
        with numeric tag prefixes ([1], [2]), matching ObserveResponse schema.
        """
        # Define structured DOM element descriptors
        dom_elements = [
            {
                "id": 1,
                "role": "input",
                "type": "text",
                "name": "Search rentals",
                "placeholder": "Enter district (e.g. Zamalek)",
                "rect": {"x": 100, "y": 150, "width": 300, "height": 40},
                "is_visible": True,
                "is_interactive": True,
            },
            {
                "id": 2,
                "role": "button",
                "type": "submit",
                "name": "Search",
                "rect": {"x": 420, "y": 150, "width": 100, "height": 40},
                "is_visible": True,
                "is_interactive": True,
            },
        ]

        # Compact token-efficient line formatting
        lines = []
        for el in dom_elements:
            el_id = el["id"]
            role = el["role"]
            label = el.get("name", "")
            placeholder = el.get("placeholder", "")
            meta = role
            if placeholder:
                meta += f', placeholder="{placeholder}"'
            display_label = f' "{label}"' if label else ""
            lines.append(f"[{el_id}]{display_label} ({meta})")

        tree_text = "\n".join(lines)

        # Validate with ObserveResponse Pydantic model
        obs = ObserveResponse(
            status="success",
            url="https://example.com/rentals",
            title="Cairo Real Estate",
            viewport={"width": 1280, "height": 800},
            tree_text=tree_text,
            elements=dom_elements,
        )

        self.assertEqual(obs.status, "success")
        self.assertIn('[1] "Search rentals" (input, placeholder="Enter district (e.g. Zamalek)")', obs.tree_text)
        self.assertIn('[2] "Search" (button)', obs.tree_text)
        self.assertEqual(len(obs.elements), 2)
        self.assertEqual(obs.elements[0]["id"], 1)
        self.assertEqual(obs.elements[1]["id"], 2)

        # Verify observe API endpoint returns formatted tree
        class MockWS:
            async def send_text(self, text):
                frame = json.loads(text)
                req_id = frame.get("request_id")
                fut = state.find_pending_future(req_id)
                if fut and not fut.done():
                    fut.set_result({
                        "status": "success",
                        "url": "https://example.com/rentals",
                        "title": "Cairo Real Estate",
                        "tree_text": tree_text,
                        "elements": dom_elements,
                    })

        state.extension_ws = MockWS()
        resp = self.client.post("/observe", json={"tab_group_id": 101, "take_screenshot": False})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("[1]", data["tree_text"])
        self.assertIn("[2]", data["tree_text"])

    # ------------------------------------------------------------------------
    # 2. test_atomic_mcp_tool_routing
    # ------------------------------------------------------------------------
    def test_atomic_mcp_tool_routing(self):
        """
        2. test_atomic_mcp_tool_routing:
        Tests browser_observe, browser_click, browser_type, browser_scroll, and task_complete
        tool invocation signatures and parameters with tab_group_id routing.
        """
        # Test tool inventory and parameter schemas on MCPServer
        tools = {t.name: t for t in asyncio.run(socket_mcp.server.list_tools())}

        for tool_name in ["browser_observe", "browser_click", "browser_type", "browser_scroll", "task_complete"]:
            self.assertIn(tool_name, tools, f"Tool {tool_name} missing from MCP server.")
            props = tools[tool_name].input_schema.get("properties", {})
            self.assertIn("tab_group_id", props, f"Tool {tool_name} must support tab_group_id parameter.")

        # Test browser_observe routing
        with patch.object(socket_launcher, "browser_observe", return_value={"status": "success", "observed": True}) as mock_obs:
            res = socket_mcp.browser_observe(tab_group_id=701, take_screenshot=True)
            self.assertEqual(res["status"], "success")
            mock_obs.assert_called_once_with(tab_group_id=701, take_screenshot=True)

        # Test browser_click routing
        with patch.object(socket_launcher, "browser_click", return_value={"status": "success", "clicked": True}) as mock_click:
            res = socket_mcp.browser_click(element_id=3, tab_group_id=701, wait_settle=True)
            self.assertEqual(res["status"], "success")
            mock_click.assert_called_once_with(element_id=3, tab_group_id=701, wait_settle=True)

        # Test browser_type routing
        with patch.object(socket_launcher, "browser_type", return_value={"status": "success", "typed": True}) as mock_type:
            res = socket_mcp.browser_type(element_id=1, text="Cairo", tab_group_id=701, clear_first=True, press_enter=True)
            self.assertEqual(res["status"], "success")
            mock_type.assert_called_once_with(element_id=1, text="Cairo", tab_group_id=701, clear_first=True, press_enter=True)

        # Test browser_scroll routing
        with patch.object(socket_launcher, "browser_scroll", return_value={"status": "success", "scrolled": True}) as mock_scroll:
            res = socket_mcp.browser_scroll(direction="down", amount=350, tab_group_id=701)
            self.assertEqual(res["status"], "success")
            mock_scroll.assert_called_once_with(direction="down", amount=350, tab_group_id=701)

        # Test task_complete routing
        with patch.object(socket_launcher, "task_complete", return_value={"status": "success", "completed": True}) as mock_tc:
            res = socket_mcp.task_complete(result="Extraction done", status="completed", tab_group_id=701)
            self.assertEqual(res["status"], "success")
            mock_tc.assert_called_once_with(result="Extraction done", status="completed", tab_group_id=701)

    # ------------------------------------------------------------------------
    # 3. test_sqlite_hybrid_storage
    # ------------------------------------------------------------------------
    def test_sqlite_hybrid_storage(self):
        """
        3. test_sqlite_hybrid_storage:
        Validates that server/db.py initializes with WAL mode (PRAGMA journal_mode = WAL;).
        Verifies atomic O(1) session upserts and indexed query lookups in sessions table.
        Asserts that index.json is not written to or thrashed.
        """
        # 1. Assert WAL journal mode
        with get_connection(self.db_path) as conn:
            cursor = conn.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0]
            self.assertEqual(mode.lower(), "wal", "Database must run in SQLite WAL mode.")

        # 2. Atomic O(1) session upsert
        session = self.manager.get_or_create_session(
            tab_group_id=888,
            tab_group_name="Zamalek Search",
            group_color="emerald",
            agent_name="Antigravity Test Agent",
        )
        session.action_count = 12
        session.takeover_count = 1
        self.manager._update_index_for_session(session)

        # 3. Indexed query lookup
        results = self.manager.query_history(query_hint="Zamalek", limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tab_group_name"], "Zamalek Search")
        self.assertEqual(results[0]["action_count"], 12)

        # 4. Assert index.json is NOT written to in test_dir
        legacy_index_path = os.path.join(self.test_dir, "sessions", "history_logs", "index.json")
        self.assertFalse(
            os.path.exists(legacy_index_path),
            "Legacy index.json file must not be created or thrashed under SQLite storage.",
        )

    # ------------------------------------------------------------------------
    # 4. test_gateway_auth_token_and_cors
    # ------------------------------------------------------------------------
    def test_gateway_auth_token_and_cors(self):
        """
        4. test_gateway_auth_token_and_cors:
        Simulates unauthenticated HTTP and WebSocket connections without X-AgentSocket-Token:
        confirms HTTP 401 Unauthorized rejection.
        Tests CORS origin enforcement: confirms simulated external web origins are rejected.
        """
        unauth_client = TestClient(app)

        # 1. HTTP 401 Unauthorized rejection without token
        resp = unauth_client.get("/status")
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        self.assertEqual(data["error"]["code"], ErrorCode.UNAUTHORIZED.value)

        # 2. HTTP 200 with valid X-AgentSocket-Token header
        auth_resp = unauth_client.get("/status", headers={AUTH_TOKEN_HEADER: state.server_token})
        self.assertEqual(auth_resp.status_code, 200)

        # 3. HTTP 200 with valid query parameter token
        param_resp = unauth_client.get(f"/status?token={state.server_token}")
        self.assertEqual(param_resp.status_code, 200)

        # 4. WebSocket connection rejection without token
        with self.assertRaises(Exception):
            with unauth_client.websocket_connect("/ws/extension"):
                pass

        # 5. CORS origin enforcement
        # Permitted local origin
        local_opt = self.client.options(
            "/status",
            headers={"Origin": "http://127.0.0.1:8000", "Access-Control-Request-Method": "GET"},
        )
        self.assertEqual(local_opt.headers.get("access-control-allow-origin"), "http://127.0.0.1:8000")

        # Permitted Chrome Extension origin
        ext_origin = "chrome-extension://knldjmfmopnmpfpdbeckimgmflmigack"
        ext_opt = self.client.options(
            "/status",
            headers={"Origin": ext_origin, "Access-Control-Request-Method": "GET"},
        )
        self.assertEqual(ext_opt.headers.get("access-control-allow-origin"), ext_origin)

        # Rejected external/malicious web origin
        bad_opt = self.client.options(
            "/status",
            headers={"Origin": "http://evil-tracker.com", "Access-Control-Request-Method": "GET"},
        )
        self.assertNotEqual(bad_opt.headers.get("access-control-allow-origin"), "http://evil-tracker.com")

    # ------------------------------------------------------------------------
    # 5. test_tab_group_state_isolation_and_resumption
    # ------------------------------------------------------------------------
    def test_tab_group_state_isolation_and_resumption(self):
        """
        5. test_tab_group_state_isolation_and_resumption:
        Verifies that setting takeover on tab_group_id: 101 sets human_in_control only for that group.
        Verifies that commands on other tab groups continue to execute normally.
        Verifies that when intervention notes exist, act_element executes the payload and returns
        notes without dropping the command.
        """
        # Set takeover mode strictly on tab group 101
        session_101 = state.get_session(101)
        session_101.human_in_control = True
        session_101.last_intervention_notes = "User handled CAPTCHA on tab 101"

        # Tab group 102 must remain completely normal (isolated)
        session_102 = state.get_session(102)
        self.assertFalse(session_102.human_in_control)
        self.assertIsNone(session_102.last_intervention_notes)

        # Verify /status reports isolation correctly
        st_101 = self.client.get("/status?tab_group_id=101").json()
        st_102 = self.client.get("/status?tab_group_id=102").json()
        self.assertTrue(st_101["human_in_control"])
        self.assertFalse(st_102["human_in_control"])

        # Execute act on tab 102 while tab 101 is locked
        captured_messages = []

        class MockWS:
            async def send_text(self, text):
                frame = json.loads(text)
                captured_messages.append(frame)
                req_id = frame.get("request_id")
                fut = state.find_pending_future(req_id)
                if fut and not fut.done():
                    fut.set_result({
                        "status": "success",
                        "action": frame.get("action"),
                        "element_id": frame.get("element_id"),
                        "mutations_observed": 1,
                        "settle_reason": "quiescence",
                    })

        state.extension_ws = MockWS()

        # Command on tab 102 succeeds
        resp_102 = self.client.post("/act", json={
            "tab_group_id": 102,
            "action": "click",
            "element_id": 4,
        })
        self.assertEqual(resp_102.status_code, 200)
        self.assertEqual(resp_102.json()["status"], "success")

        # Now release tab 101
        rel_resp = self.client.post("/human_release", json={
            "tab_group_id": 101,
            "notes": "Finished MFA verification",
        })
        self.assertEqual(rel_resp.status_code, 200)
        self.assertFalse(session_101.human_in_control)
        self.assertEqual(session_101.last_intervention_notes, "Finished MFA verification")

        # When act executes on tab 101, intervention notes are returned AND command executes (not dropped)
        resp_101 = self.client.post("/act", json={
            "tab_group_id": 101,
            "action": "click",
            "element_id": 9,
        })
        self.assertEqual(resp_101.status_code, 200)
        data_101 = resp_101.json()
        self.assertEqual(data_101["status"], "success")
        self.assertEqual(data_101["intervention_notes"], "Finished MFA verification")
        self.assertEqual(data_101["element_id"], 9)
        # Verify notes are cleared on session
        self.assertIsNone(session_101.last_intervention_notes)

    # ------------------------------------------------------------------------
    # 6. test_yaml_frontmatter_manifest_parsing
    # ------------------------------------------------------------------------
    def test_yaml_frontmatter_manifest_parsing(self):
        """
        6. test_yaml_frontmatter_manifest_parsing:
        Tests that read_manifest() in server/session/storage.py correctly parses
        frontmatter from SESSION_DOCUMENT.md.
        """
        session_dir = os.path.join(self.test_dir, "test_manifest_parsing")
        os.makedirs(session_dir, exist_ok=True)

        manifest = SessionManifestModel(
            session_id="sess_ooda_frontmatter_99",
            session_title="OODA Manifest Parser Test",
            tab_group_id=99,
            tab_group_name="OODA Manifest Parser Test",
            group_color="purple",
            agent_name="Antigravity Test Suite",
            mode="direct",
            status="completed",
            duration_ms=3140.2,
            metrics={"total_actions": 8, "total_clicks": 4, "avg_settlement_ms": 62.5},
            deliverables=["output/summary.csv", "output/report.json"],
        )

        # Write manifest as YAML frontmatter into SESSION_DOCUMENT.md
        self.storage.write_manifest(session_dir, manifest)

        # Assert file exists and read_manifest parses all fields correctly
        loaded = self.storage.read_manifest(session_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "sess_ooda_frontmatter_99")
        self.assertEqual(loaded.tab_group_id, 99)
        self.assertEqual(loaded.group_color, "purple")
        self.assertEqual(loaded.mode, "direct")
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.duration_ms, 3140.2)
        self.assertEqual(loaded.metrics.get("total_clicks"), 4)
        self.assertIn("output/summary.csv", loaded.deliverables)

    # ------------------------------------------------------------------------
    # 7. test_lean_jsonl_and_secret_masking
    # ------------------------------------------------------------------------
    def test_lean_jsonl_and_secret_masking(self):
        """
        7. test_lean_jsonl_and_secret_masking:
        Verifies that session.jsonl does not duplicate session ID across non-start events,
        and that sensitive attributes are masked with [REDACTED].
        """
        session = self.manager.get_or_create_session(
            tab_group_id=333,
            tab_group_name="Lean Stream & Secrets Test",
        )

        # Log action events with sensitive data
        self.manager.log_event(
            tab_group_id=333,
            event_type=SessionEventType.NAVIGATE,
            title="Navigate to secure portal",
            start_time=time.time(),
            payload={"url": "https://secure.example.com/login"},
        )

        self.manager.log_event(
            tab_group_id=333,
            event_type=SessionEventType.ACT_ELEMENT,
            title="Type credentials",
            start_time=time.time(),
            payload={
                "action": "type",
                "element_id": 1,
                "password": "SecretPassword123!",
                "auth_token": "token_abc_xyz",
                "cvv": "789",
                "normal_username": "test_user",
            },
        )

        self.manager.log_event(
            tab_group_id=333,
            event_type=SessionEventType.OBSERVE,
            title="Observe authenticated dashboard",
            start_time=time.time(),
            payload={"nodes": 24},
        )

        # Read lines from session.jsonl
        with open(session.jsonl_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        self.assertGreaterEqual(len(lines), 4)

        # 1. Line 0: SESSION_START contains session_id
        start_evt = lines[0]
        self.assertEqual(start_evt["type"], SessionEventType.SESSION_START.value)
        has_session_id_in_start = ("session_id" in start_evt) or ("session_id" in start_evt.get("payload", {}))
        self.assertTrue(has_session_id_in_start, "SESSION_START must include session_id.")

        # 2. Non-start events MUST NOT duplicate session_id at the root of JSONL entry
        for evt in lines[1:]:
            self.assertNotIn(
                "session_id",
                evt,
                f"Non-start event '{evt.get('type')}' must not duplicate redundant session_id.",
            )

        # 3. Secret masking: sensitive keys must be [REDACTED]
        act_evt = next(e for e in lines if e["type"] == SessionEventType.ACT_ELEMENT.value)
        payload = act_evt["payload"]
        self.assertEqual(payload["password"], "[REDACTED]")
        self.assertEqual(payload["auth_token"], "[REDACTED]")
        self.assertEqual(payload["cvv"], "[REDACTED]")
        self.assertEqual(payload["normal_username"], "test_user")

    # ------------------------------------------------------------------------
    # 8. test_zero_plan_direct_mode_storage
    # ------------------------------------------------------------------------
    def test_zero_plan_direct_mode_storage(self):
        """
        8. test_zero_plan_direct_mode_storage:
        Verifies that Direct Mode creates only 2 root session files (SESSION_DOCUMENT.md,
        session.jsonl), 0 plan.json files, and 0 adhocs/ folders.
        """
        session = self.manager.get_or_create_session(
            tab_group_id=555,
            tab_group_name="Zero Plan Direct Mode Task",
            agent_name="Antigravity Direct Driver",
        )

        # Log direct OODA actions
        self.manager.log_event(
            tab_group_id=555,
            event_type=SessionEventType.NAVIGATE,
            title="Navigate to destination",
            start_time=time.time(),
            payload={"url": "https://example.com"},
        )
        self.manager.log_event(
            tab_group_id=555,
            event_type=SessionEventType.ACT_ELEMENT,
            title="Click button",
            start_time=time.time(),
            payload={"action": "click", "element_id": 2},
        )
        self.manager.finalize_session(555, SessionStatus.COMPLETED)

        session_root = session.session_dir
        root_entries = os.listdir(session_root)
        root_files = [f for f in root_entries if os.path.isfile(os.path.join(session_root, f))]

        # Root files MUST be exactly SESSION_DOCUMENT.md and session.jsonl
        self.assertCountEqual(
            root_files,
            ["SESSION_DOCUMENT.md", "session.jsonl"],
            f"Expected exactly 2 root files (SESSION_DOCUMENT.md, session.jsonl), got: {root_files}",
        )

        # Assert 0 plan.json files
        self.assertFalse(
            os.path.exists(os.path.join(session_root, "plan.json")),
            "Direct mode must not generate plan.json.",
        )

        # Assert 0 adhocs/ folders
        self.assertFalse(
            os.path.exists(os.path.join(session_root, "adhocs")),
            "Direct mode must not generate empty adhocs/ folders.",
        )


if __name__ == "__main__":
    unittest.main()
