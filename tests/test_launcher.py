"""
Unit tests for AgentSocket Launcher utilities and process manager.
"""

import os
import sys
import unittest

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from server.socket_launcher import (
    find_chrome_path,
    is_pid_running,
    clean_stale_pid_file,
    get_gateway_status,
    PID_FILE_PATH,
    query_history,
    get_session_details,
    get_session_artifact,
    get_session_document,
    get_session_thread,
    build_cli_parser,
    export_all_timeline,
    print_history_table,
    print_session_logs,
)


class TestLauncher(unittest.TestCase):

    def test_find_chrome_path(self):
        # Should return string or None without crashing
        path = find_chrome_path()
        if path:
            self.assertTrue(os.path.exists(path))

    def test_is_pid_running_invalid(self):
        self.assertFalse(is_pid_running(-1))
        self.assertFalse(is_pid_running(0))
        self.assertFalse(is_pid_running(99999999))

    def test_clean_stale_pid_file(self):
        # Write dummy dead PID
        with open(PID_FILE_PATH, "w", encoding="utf-8") as f:
            f.write("99999999")

        clean_stale_pid_file()
        self.assertFalse(os.path.exists(PID_FILE_PATH))

    def test_get_gateway_status_offline(self):
        status = get_gateway_status("http://127.0.0.1:59999")
        self.assertEqual(status["status"], "offline")
        self.assertFalse(status["extension_connected"])

    def test_history_helpers_offline(self):
        # Even when server is offline, helpers should fall back directly to SessionManager without crashing
        res = query_history(server_url="http://127.0.0.1:59999")
        self.assertIsInstance(res, list)

        details = get_session_details("server/logs/dummy_path", server_url="http://127.0.0.1:59999")
        self.assertIn("status", details)

        art = get_session_artifact("server/logs/dummy_path", "test.json", server_url="http://127.0.0.1:59999")
        self.assertIn("status", art)

        # Test printing functions do not throw exceptions
        print_history_table([])
        print_history_table([{"session_id": "sess_1", "tab_group_name": "Test", "status": "completed"}])
        print_session_logs({"status": "error", "message": "None"})
        print_session_logs({"status": "success", "events": [{"event_id": "evt_1", "type": "navigate", "duration_ms": 12.0, "title": "Test"}]})

    def test_thread_cli_parser(self):
        parser = build_cli_parser()
        args = parser.parse_args(["thread", "--path", "server/logs/2026-08-21/dummy_session"])
        self.assertEqual(args.command, "thread")
        self.assertEqual(args.path, "server/logs/2026-08-21/dummy_session")
        self.assertFalse(args.json)


if __name__ == "__main__":
    unittest.main()

