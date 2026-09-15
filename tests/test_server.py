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
        state.human_in_control = False
        state.last_intervention_notes = "Manual step finished."

        resp = self.client.post("/execute", json={
            "id": "cmd-test-4",
            "action_type": "navigate",
            "target_data": "https://example.com/checkout",
            "session_title": "Test Resumed Context",
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.RESUMED_CONTEXT.value)
        self.assertIn("Manual step finished.", data["message"])
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


if __name__ == "__main__":
    unittest.main()


