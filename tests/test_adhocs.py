"""
Tests for Universal Standard Adhoc Tool Suite (server/templates/adhocs/)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from server.session import seed_universal_adhocs

ADHOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server", "templates", "adhocs")

EXPECTED_ADHOCS = [
    "navigate.py",
    "write_input.py",
    "type_input.py",
    "click_element.py",
    "extract_text.py",
    "scroll_page.py",
    "eval_js.py",
    "take_screenshot.py",
]


class TestAdhocs(unittest.TestCase):
    def test_all_universal_adhocs_exist(self):
        self.assertTrue(os.path.isdir(ADHOCS_DIR), f"Directory {ADHOCS_DIR} does not exist.")
        for tool_name in EXPECTED_ADHOCS:
            tool_path = os.path.join(ADHOCS_DIR, tool_name)
            self.assertTrue(os.path.isfile(tool_path), f"Universal adhoc {tool_name} is missing.")

    def test_adhoc_cli_help(self):
        # Verify that all tools run with --help without syntax or runtime errors
        for tool_name in EXPECTED_ADHOCS:
            tool_path = os.path.join(ADHOCS_DIR, tool_name)
            cmd = [sys.executable, tool_path, "--help"]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{tool_name} failed --help with error:\n{proc.stderr}")
            self.assertIn("usage:", proc.stdout.lower())

    def test_central_vault_adhocs(self):
        central_adhocs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server", "adhocs")
        self.assertTrue(os.path.isdir(central_adhocs_dir))
        expected_central = [
            "probe_dom.py",
            "export_csv.py",
            "download_media.py",
            "scroll_page.py",
            "navigate.py",
            "click_element.py",
        ]
        for tool_name in expected_central:
            tool_path = os.path.join(central_adhocs_dir, tool_name)
            self.assertTrue(os.path.isfile(tool_path), f"Central vault adhoc {tool_name} is missing.")
            proc = subprocess.run([sys.executable, tool_path, "--help"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{tool_name} failed --help: {proc.stderr}")
            self.assertIn("usage:", proc.stdout.lower())


if __name__ == "__main__":
    unittest.main()
