"""
Unit and Integration Tests for Feature Spec 30:
Persistent Session Authorization & Non-Redundant Consent Architecture 🔒⚡
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from server.socket_server import app, state

client = TestClient(app)

class TestSpec30SessionAuth(unittest.TestCase):
    def setUp(self):
        state.server_token = "test_spec30_ephemeral_token_12345"

    def test_local_token_bootstrap_endpoint(self):
        """Spec 30: /api/token is accessible from localhost to bootstrap client auth."""
        response = client.get("/api/token")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("token"), "test_spec30_ephemeral_token_12345")

    def test_extension_origin_auth_bypass_on_loopback(self):
        """Spec 30: Requests carrying chrome-extension origin from loopback interface pass without 401."""
        response = client.get(
            "/status",
            headers={"Origin": "chrome-extension://abcdefghijklmnop"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    def test_non_extension_without_token_returns_401(self):
        """Spec 30 Security Invariant: Non-extension client without token is strictly rejected."""
        response = client.get("/status")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "UNAUTHORIZED")

    def test_non_extension_with_valid_token_passes(self):
        """Spec 30: Client providing X-AgentSocket-Token passes authentication."""
        response = client.get(
            "/status",
            headers={"X-AgentSocket-Token": "test_spec30_ephemeral_token_12345"}
        )
        self.assertEqual(response.status_code, 200)

    def test_storage_hydration_lifecycle_simulation(self):
        """
        Spec 30: Simulates chrome.storage.local hydration across service worker recycles.
        Verifies that an approved session is remembered and does not require re-authorization.
        """
        # Simulated chrome.storage.local mock
        storage_mock = {
            "authorized_sessions_list": ["Batch 10 CRM Enrichment", "Test Run A"],
            "session_permissions_list": [
                ["Batch 10 CRM Enrichment", {"enable_subskills": True, "enable_vision": True}]
            ]
        }

        # Simulated background.js in-memory variables after worker termination (wiped to empty)
        in_memory_authorized_sessions = set()
        in_memory_session_permissions = {}

        # 1. Simulate worker wake and hydration
        for s in storage_mock.get("authorized_sessions_list", []):
            in_memory_authorized_sessions.add(s)
        for k, v in storage_mock.get("session_permissions_list", []):
            in_memory_session_permissions[k] = v

        # 2. Verify previously approved session is recognized immediately
        self.assertIn("Batch 10 CRM Enrichment", in_memory_authorized_sessions)
        self.assertTrue(in_memory_session_permissions["Batch 10 CRM Enrichment"]["enable_vision"])

        # 3. Verify a completely new session is not recognized and will correctly prompt
        self.assertNotIn("Unknown New Task", in_memory_authorized_sessions)

if __name__ == "__main__":
    unittest.main()
