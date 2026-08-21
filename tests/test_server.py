"""
Integration tests for AgentSocket FastAPI gateway endpoints and state machines.
"""

import unittest
from fastapi.testclient import TestClient
from server.socket_server import app, state
from server.models import ResponseStatus, ActionType


class TestServerEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        # Reset state for testing
        state.human_in_control = False
        state.last_intervention_notes = None
        state.extension_ws = None
        state.pending_responses.clear()

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
            "requires_privacy_check": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], ResponseStatus.ERROR.value)
        self.assertEqual(data["message"], "Extension is offline.")

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


if __name__ == "__main__":
    unittest.main()

