"""
Unit tests for Launcher utilities and process manager.
"""

import os
import unittest
from server.bro_launcher import (
    find_chrome_path,
    is_pid_running,
    clean_stale_pid_file,
    get_gateway_status,
    PID_FILE_PATH
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


if __name__ == "__main__":
    unittest.main()
