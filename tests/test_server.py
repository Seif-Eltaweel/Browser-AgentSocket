"""
Integration tests for AgentSocket FastAPI gateway endpoints and state machines.
"""

import unittest
from fastapi.testclient import TestClient
from server.socket_server import app, state
from server.models import ResponseStatus, ActionType
from server.session import session_manager


class TestServerEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.client.headers.update({"X-AgentSocket-Token": state.server_token})
        # Reset state for testing
        state.human_in_control = False
        state.last_intervention_notes = None
        state.extension_ws = None
        state.tab_sessions.clear()
        state.pending_responses.clear()
        state.global_permissions = {"enable_subskills": True, "enable_vision": False}
        state.session_permissions.clear()

    def test_root_endpoint(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "AgentSocket Server is Live")
        self.assertFalse(data["human_in_control"])
        self.assertFalse(data["extension_connected"])

    def test_status_endpoint(self):
        resp = self.client.get("/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "AgentSocket Server is Live")
        self.assertIn("idle_seconds_remaining", data)

    def test_execute_privacy_flag_trigger(self):
        resp = self.client.post("/execute", json={
            "id": "cmd-test-1",
            "action_type": "navigate",
            "target_data": "https://example.com",
            "session_title": "Test Privacy Flag",
            "requires_privacy_check": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.SECURITY_ABORT.value)
        self.assertIn("Sensitive scope detected", data["message"])
        self.assertTrue(state.human_in_control)

    def test_execute_sensitive_keyword_trigger(self):
        resp = self.client.post("/execute", json={
            "id": "cmd-test-2",
            "action_type": "navigate",
            "target_data": "https://mybank.com/login/password",
            "session_title": "Test Sensitive Keywords",
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.SECURITY_ABORT.value)
        self.assertTrue(state.human_in_control)

    def test_execute_human_locked_state(self):
        state.human_in_control = True
        state.last_intervention_notes = "User is doing 2FA"

        resp = self.client.post("/execute", json={
            "id": "cmd-test-3",
            "action_type": "execute_js",
            "target_data": "document.title",
            "session_title": "Test Human Lock",
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.HUMAN_LOCKED.value)
        self.assertEqual(data["last_intervention_notes"], "User is doing 2FA")

    def test_human_release_endpoint(self):
        state.human_in_control = True
        resp = self.client.post("/human_release", json={
            "notes": "Finished MFA successfully."
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.SUCCESS.value)
        self.assertFalse(data["human_in_control"])
        self.assertEqual(state.last_intervention_notes, "Finished MFA successfully.")

    def test_execute_resumed_context_handoff(self):
        # Spec 23 Flaw 4 fix: intervention notes returned as metadata without dropping command
        import json
        state.human_in_control = False
        state.last_intervention_notes = "Manual step finished."

        class MockWS:
            async def send_text(self, text):
                payload = json.loads(text)
                cmd_id = payload.get("id")
                fut = state.find_pending_future(cmd_id)
                if fut and not fut.done():
                    fut.set_result({"status": "success", "url": payload.get("target_data")})

        state.extension_ws = MockWS()

        resp = self.client.post("/execute", json={
            "id": "cmd-test-4",
            "action_type": "navigate",
            "target_data": "https://example.com/items",
            "session_title": "Test Resumed Context",
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.SUCCESS.value)
        self.assertEqual(data["intervention_notes"], "Manual step finished.")
        # Injected notes should be cleared after consumption
        self.assertIsNone(state.last_intervention_notes)

    def test_stop_endpoint(self):
        state.human_in_control = True
        state.last_intervention_notes = "Some notes"

        resp = self.client.post("/stop")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.SUCCESS.value)
        self.assertFalse(state.human_in_control)
        self.assertIsNone(state.last_intervention_notes)

    def test_execute_extension_offline(self):
        state.human_in_control = False
        state.last_intervention_notes = None
        state.extension_ws = None

        resp = self.client.post("/execute", json={
            "id": "cmd-test-5",
            "action_type": "navigate",
            "target_data": "https://example.com/public-docs",
            "session_title": "Test Offline Extension",
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.ERROR.value)
        self.assertEqual(data["message"], "Extension is offline.")

    def test_execute_extension_auth_denied(self):
        import json
        state.human_in_control = False
        state.last_intervention_notes = None

        class MockWS:
            async def send_text(self, text):
                data = json.loads(text)
                cmd_id = data.get("id")
                if cmd_id and cmd_id in state.pending_responses:
                    fut = state.pending_responses[cmd_id]
                    if not fut.done():
                        fut.set_result({
                            "status": "error",
                            "error": {
                                "code": "AUTH_REQUIRED",
                                "message": "Session authorization was denied by the user."
                            }
                        })

        state.extension_ws = MockWS()

        resp = self.client.post("/execute", json={
            "id": "cmd-test-auth-denied",
            "action_type": "navigate",
            "target_data": "https://example.com/test",
            "session_title": "Denied Session Test",
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.ERROR.value)
        self.assertEqual(data["error"]["code"], "AUTH_REQUIRED")

        # Verify that no session was created in session_manager
        active_sess = session_manager.get_active_session_by_title("Denied Session Test")
        self.assertIsNone(active_sess)

    def test_history_rest_endpoints(self):
        # 1. Test GET /history
        resp = self.client.get("/history")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

        # 2. Test GET /session/details for non-existent path
        resp = self.client.get("/session/details?path=non/existent/path")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "error")

        # 3. Test GET /session/artifact for non-existent artifact
        resp = self.client.get("/session/artifact?path=non/existent&name=art.json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "error")

    def test_unauthenticated_request_rejected(self):
        client = TestClient(app)
        resp = client.get("/")
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_invalid_token_rejected(self):
        client = TestClient(app)
        resp = client.get("/", headers={"X-AgentSocket-Token": "invalid-token-12345"})
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_authenticated_via_query_param(self):
        client = TestClient(app)
        resp = client.get(f"/?token={state.server_token}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "AgentSocket Server is Live")

    def test_cors_origin_restriction(self):
        # 1. Allowed origin (localhost)
        resp_local = self.client.get("/", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(resp_local.headers.get("access-control-allow-origin"), "http://localhost:3000")

        # 2. Allowed origin (chrome-extension)
        resp_ext = self.client.get("/", headers={"Origin": "chrome-extension://abcdefghijklmnop"})
        self.assertEqual(resp_ext.headers.get("access-control-allow-origin"), "chrome-extension://abcdefghijklmnop")

        # 3. Disallowed origin (malicious web page)
        resp_evil = self.client.get("/", headers={"Origin": "https://malicious-site.com"})
        self.assertNotEqual(resp_evil.headers.get("access-control-allow-origin"), "https://malicious-site.com")

    def test_websocket_auth_handshake(self):
        from starlette.websockets import WebSocketDisconnect
        unauth_client = TestClient(app)

        # 1. Reject without token
        with self.assertRaises(WebSocketDisconnect) as cm:
            with unauth_client.websocket_connect("/ws/extension"):
                pass
        self.assertEqual(cm.exception.code, 1008)

        # 2. Reject with invalid token
        with self.assertRaises(WebSocketDisconnect) as cm:
            with unauth_client.websocket_connect("/ws/extension?token=bad-token"):
                pass
        self.assertEqual(cm.exception.code, 1008)

        # 3. Connect with valid token and send AUTH_RESPONSE handshake
        with unauth_client.websocket_connect(f"/ws/extension?token={state.server_token}") as ws:
            ws.send_json({
                "type": "AUTH_RESPONSE",
                "session_title": "Test Session Permissions",
                "authorized": True,
                "permissions": {
                    "enable_subskills": False,
                    "enable_vision": True
                }
            })
            import time
            time.sleep(0.1)
            self.assertEqual(state.global_permissions.get("enable_subskills"), False)
            self.assertEqual(state.global_permissions.get("enable_vision"), True)
            self.assertIn("Test Session Permissions", state.session_permissions)
            self.assertEqual(state.session_permissions["Test Session Permissions"]["enable_vision"], True)

    def test_subskills_permission_gate(self):
        state.global_permissions["enable_subskills"] = False
        resp = self.client.post("/subskills/borrow", json={
            "name": "test_skill",
            "session_title": "Test Subskill Session"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "denied")
        self.assertEqual(data["error"]["code"], "PERMISSION_DENIED")

    def test_vision_permission_gate(self):
        # 1. Denied when enable_vision is False
        state.global_permissions["enable_vision"] = False
        resp = self.client.post("/execute", json={
            "id": "cmd-test-vision-denied",
            "action_type": "browser_screenshot",
            "target_data": "",
            "session_title": "Vision Test",
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "denied")
        self.assertEqual(data["error"]["code"], "VISION_DISABLED")

        # 2. Allowed when enable_vision is True (passes gate and reaches extension dispatch)
        state.global_permissions["enable_vision"] = True
        resp = self.client.post("/execute", json={
            "id": "cmd-test-vision-allowed",
            "action_type": "browser_screenshot",
            "target_data": "",
            "session_title": "Vision Test",
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["message"], "Extension is offline.")

    def test_tab_group_takeover_isolation(self):
        # Spec 23 Flaw 3 test: setting takeover on tab_group_id 101 does NOT pause tab_group_id 102
        import json
        state.get_session(101).human_in_control = True
        state.get_session(101).last_intervention_notes = "User solving 2FA on tab 101"

        # Check session 102 is free
        self.assertFalse(state.get_session(102).human_in_control)

        # Query /status for both groups
        status_101 = self.client.get("/status?tab_group_id=101").json()
        self.assertTrue(status_101["human_in_control"])
        self.assertEqual(status_101["last_intervention_notes"], "User solving 2FA on tab 101")

        status_102 = self.client.get("/status?tab_group_id=102").json()
        self.assertFalse(status_102["human_in_control"])
        self.assertIsNone(status_102["last_intervention_notes"])

        # POST /act on group 101 is human_locked
        act_101 = self.client.post("/act", json={
            "tab_group_id": 101,
            "action": "click",
            "element_id": 4
        }).json()
        self.assertEqual(act_101["status"], ResponseStatus.HUMAN_LOCKED.value)
        self.assertEqual(act_101["intervention_notes"], "User solving 2FA on tab 101")

        # POST /act on group 102 executes normally through extension
        class MockWS:
            async def send_text(self, text):
                data = json.loads(text)
                req_id = data.get("request_id")
                fut = state.find_pending_future(req_id)
                if fut and not fut.done():
                    fut.set_result({
                        "status": "success",
                        "mutations_observed": 1,
                        "settle_reason": "quiescence",
                        "duration_ms": 12.5
                    })

        state.extension_ws = MockWS()
        act_102 = self.client.post("/act", json={
            "tab_group_id": 102,
            "action": "click",
            "element_id": 9
        }).json()
        self.assertEqual(act_102["status"], "success")
        self.assertEqual(act_102["element_id"], 9)
        self.assertEqual(act_102["mutations_observed"], 1)

    def test_act_element_rpc_and_notes(self):
        # Spec 23 Flaw 4 test: act_element executes action and returns intervention_notes in ActResponse
        import json
        state.get_session(201).human_in_control = False
        state.get_session(201).last_intervention_notes = "User filled captcha and handed off"

        captured_frames = []

        class MockWS:
            async def send_text(self, text):
                data = json.loads(text)
                captured_frames.append(data)
                req_id = data.get("request_id")
                fut = state.find_pending_future(req_id)
                if fut and not fut.done():
                    fut.set_result({
                        "status": "success",
                        "mutations_observed": 3,
                        "settle_reason": "quiescence",
                        "duration_ms": 35.0
                    })

        state.extension_ws = MockWS()

        resp = self.client.post("/act", json={
            "tab_group_id": 201,
            "action": "type",
            "element_id": 7,
            "text": "Antigravity Agent",
            "clear_first": True,
            "press_enter": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Command must execute normally (NOT dropped)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["action"], "type")
        self.assertEqual(data["element_id"], 7)
        self.assertEqual(data["mutations_observed"], 3)
        self.assertEqual(data["settle_reason"], "quiescence")
        self.assertEqual(data["intervention_notes"], "User filled captcha and handed off")

        # Cache must be cleared on session
        self.assertIsNone(state.get_session(201).last_intervention_notes)

        # Outbound frame must have been dispatched
        self.assertEqual(len(captured_frames), 1)
        self.assertEqual(captured_frames[0]["tab_group_id"], 201)
        self.assertEqual(captured_frames[0]["action"], "type")
        self.assertEqual(captured_frames[0]["element_id"], 7)
        self.assertEqual(captured_frames[0]["text"], "Antigravity Agent")

    def test_observe_page_rpc(self):
        # Spec 23 test: observe_page RPC correlation future
        import json
        class MockWS:
            async def send_text(self, text):
                data = json.loads(text)
                req_id = data.get("request_id")
                fut = state.find_pending_future(req_id)
                if fut and not fut.done():
                    fut.set_result({
                        "status": "success",
                        "url": "https://example.com/search",
                        "title": "Search Page",
                        "viewport": {"width": 1280, "height": 800},
                        "tree_text": "[1] (input) Search\n[2] (button) Submit",
                        "elements": [
                            {"id": 1, "role": "input", "label": "Search"},
                            {"id": 2, "role": "button", "label": "Submit"}
                        ]
                    })

        state.extension_ws = MockWS()

        resp = self.client.post("/observe", json={
            "tab_group_id": 301,
            "take_screenshot": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["url"], "https://example.com/search")
        self.assertEqual(data["title"], "Search Page")
        self.assertIn("[1] (input) Search", data["tree_text"])
        self.assertEqual(len(data["elements"]), 2)

    def test_set_intent_dispatch(self):
        # Spec 23 test: set_intent WebSocket frame dispatch
        import json
        sent_messages = []

        class MockWS:
            async def send_text(self, text):
                sent_messages.append(json.loads(text))

        state.extension_ws = MockWS()

        resp = self.client.post("/set_intent", json={
            "tab_group_id": 401,
            "intent": "Filter apartments by rent",
            "subtext": "Typing 15000 in price filter",
            "phase": "Phase 2/3"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")

        self.assertEqual(len(sent_messages), 1)
        frame = sent_messages[0]
        self.assertEqual(frame["type"], "set_intent")
        self.assertEqual(frame["tab_group_id"], 401)
        self.assertEqual(frame["intent"], "Filter apartments by rent")
        self.assertEqual(frame["subtext"], "Typing 15000 in price filter")
        self.assertEqual(frame["phase"], "Phase 2/3")

    def test_scoped_human_release(self):
        # Spec 23 test: releasing tab 101 does not release tab 102
        state.get_session(101).human_in_control = True
        state.get_session(102).human_in_control = True

        resp = self.client.post("/human_release", json={
            "notes": "Tab 101 released",
            "tab_group_id": 101
        })
        self.assertEqual(resp.status_code, 200)

        self.assertFalse(state.get_session(101).human_in_control)
        self.assertEqual(state.get_session(101).last_intervention_notes, "Tab 101 released")

        # Tab 102 should still be locked
        self.assertTrue(state.get_session(102).human_in_control)


if __name__ == "__main__":
    unittest.main()



