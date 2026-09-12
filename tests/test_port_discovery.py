"""
Tests for port discovery, .socket_server.port lifecycle, and multi-port resolution (Spec 17).
"""

import os
import unittest
from unittest.mock import patch
from server.socket_launcher import (
    PORT_FILE_PATH,
    resolve_server_url,
    clean_stale_port_file,
    send_progress
)
from server.socket_server import write_port_file, remove_port_file


class TestPortDiscovery(unittest.TestCase):

    def setUp(self):
        clean_stale_port_file()

    def tearDown(self):
        clean_stale_port_file()

    def test_write_and_remove_port_file(self):
        write_port_file(8001)
        self.assertTrue(os.path.exists(PORT_FILE_PATH))
        with open(PORT_FILE_PATH, "r", encoding="utf-8") as f:
            port_val = int(f.read().strip())
        self.assertEqual(port_val, 8001)

        remove_port_file()
        self.assertFalse(os.path.exists(PORT_FILE_PATH))

    def test_resolve_url_from_env_url(self):
        with patch.dict(os.environ, {"AGENTSOCKET_URL": "http://127.0.0.1:9999"}):
            url = resolve_server_url()
            self.assertEqual(url, "http://127.0.0.1:9999")

    def test_resolve_url_from_env_port(self):
        with patch.dict(os.environ, {"AGENTSOCKET_PORT": "8888"}, clear=False):
            if "AGENTSOCKET_URL" in os.environ:
                del os.environ["AGENTSOCKET_URL"]
            url = resolve_server_url()
            self.assertEqual(url, "http://127.0.0.1:8888")

    def test_resolve_url_from_port_file(self):
        # Clear env variables
        with patch.dict(os.environ, {}, clear=True):
            write_port_file(8002)
            url = resolve_server_url()
            self.assertEqual(url, "http://127.0.0.1:8002")

    @patch("requests.post")
    def test_send_progress_helper(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "status": "success",
            "progress_percent": 50
        }

        resp = send_progress(
            session_title="Discovery Test",
            step_current=5,
            step_total=10,
            step_title="Halfway there",
            server_url="http://127.0.0.1:8000"
        )
        self.assertEqual(resp["status"], "success")
        self.assertEqual(resp["progress_percent"], 50)
        mock_post.assert_called_once_with(
            "http://127.0.0.1:8000/progress",
            json={
                "session_title": "Discovery Test",
                "step_current": 5,
                "step_total": 10,
                "step_title": "Halfway there"
            },
            timeout=5.0
        )


if __name__ == "__main__":
    unittest.main()
