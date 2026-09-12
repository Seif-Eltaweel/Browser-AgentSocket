"""
Tests for /progress endpoint and progress broadcasting (Spec 17).
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from server.socket_server import app, state
from server.models import WSMessageType


class TestProgressEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        state.extension_ws = None
        state.pending_responses.clear()

    def test_progress_offline_extension(self):
        resp = self.client.post("/progress", json={
            "session_title": "Test Scraping Session",
            "step_current": 4,
            "step_total": 10,
            "step_title": "Scraping page 4"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["progress_percent"], 40)
        self.assertIn("warning", data)  # Extension offline warning

    def test_progress_zero_total_steps(self):
        resp = self.client.post("/progress", json={
            "session_title": "Empty Session",
            "step_current": 0,
            "step_total": 0,
            "step_title": "Done"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["progress_percent"], 100)

    def test_progress_with_active_websocket(self):
        mock_ws = AsyncMock()
        state.extension_ws = mock_ws

        resp = self.client.post("/progress", json={
            "session_title": "Live Automation",
            "step_current": 5,
            "step_total": 20,
            "step_title": "Processing item 5"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["progress_percent"], 25)
        self.assertNotIn("warning", data)

        # Verify WebSocket broadcast was dispatched
        mock_ws.send_text.assert_awaited_once()
        sent_json = mock_ws.send_text.call_args[0][0]
        self.assertIn(WSMessageType.UPDATE_PROGRESS.value, sent_json)
        self.assertIn("Live Automation", sent_json)
        self.assertIn('"progress_percent": 25', sent_json)

    def test_progress_invalid_payload(self):
        resp = self.client.post("/progress", json={
            "session_title": "Invalid Session",
            "step_current": "not-a-number",
            "step_total": 10
        })
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
