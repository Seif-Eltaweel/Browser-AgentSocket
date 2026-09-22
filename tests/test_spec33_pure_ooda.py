"""
Unit and Integration Tests for Feature Spec 33:
Total Purge of Adhoc Scripts Architecture & Absolute OODA Primacy Enforcement 🛡️🚫
"""

import asyncio
import os
import tempfile
import unittest

from server import socket_launcher, socket_mcp
from server.subskills.manager import SubskillsManager
from server.db import init_db


class TestSpec33PureOODAEnforcement(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_spec33.db")
        init_db(self.db_path)
        self.subskills_mgr = SubskillsManager(db_path=self.db_path)

    def test_socket_mcp_adhoc_tools_completely_purged(self):
        """Spec 33: MCP adhoc tools are completely purged from MCP registration."""
        tools = asyncio.run(socket_mcp.server.list_tools())
        tool_names = [t.name for t in tools]
        self.assertNotIn("socket_run_adhoc", tool_names)
        self.assertNotIn("socket_promote_adhoc", tool_names)
        self.assertNotIn("socket_list_adhocs", tool_names)
        self.assertFalse(hasattr(socket_mcp, "socket_run_adhoc"))
        self.assertFalse(hasattr(socket_mcp, "socket_promote_adhoc"))
        self.assertFalse(hasattr(socket_mcp, "socket_list_adhocs"))

    def test_socket_launcher_adhoc_tools_hard_deprecated(self):
        """Spec 33: Launcher adhoc functions return ADHOC_ARCHITECTURE_DEPRECATED error."""
        res_run = socket_launcher.run_adhoc("scraper.py")
        self.assertEqual(res_run.get("status"), "error")
        self.assertEqual(res_run.get("code"), "ADHOC_ARCHITECTURE_DEPRECATED")

        res_promote = socket_launcher.promote_adhoc("some/session", "scraper.py")
        self.assertEqual(res_promote.get("status"), "error")
        self.assertEqual(res_promote.get("code"), "ADHOC_ARCHITECTURE_DEPRECATED")

        res_list = socket_launcher.list_adhocs()
        self.assertEqual(res_list, [])

    def test_subskills_borrow_pure_markdown_zero_adhocs(self):
        """Spec 33: Borrowing a subskill creates pure sub_skill.md with zero adhocs folder."""
        target_dir = os.path.join(self.temp_dir, "session_test")
        res = self.subskills_mgr.borrow_subskill("example-sop", target_dir)
        self.assertEqual(res.get("status"), "success")

        # Verify sub_skill.md exists
        self.assertTrue(os.path.isfile(os.path.join(target_dir, "sub_skill.md")))

        # Verify zero adhocs directory exists in session
        self.assertFalse(os.path.exists(os.path.join(target_dir, "adhocs")))

    def test_skill_markdown_negative_constraint_present(self):
        """Spec 33: SKILL.md files enforce strict prohibition against generated scripts."""
        for skill_path in [
            "SKILL.md",
            os.path.join(".agents", "skills", "browser-socket", "SKILL.md"),
        ]:
            self.assertTrue(os.path.isfile(skill_path), f"Missing skill file: {skill_path}")
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("STRICT PROHIBITION: NO GENERATED BROWSER AUTOMATION SCRIPTS", content)
            self.assertIn("The AI Model IS the Automation Engine", content)
            self.assertIn("Retired Architecture (Spec 33)", content)

    def test_mcp_inventory_has_all_atomic_ooda_tools(self):
        """Spec 33: MCP tool registry exposes all 8 atomic OODA tools."""
        tools = asyncio.run(socket_mcp.server.list_tools())
        tool_names = {t.name for t in tools}

        expected_atomic = [
            "browser_observe",
            "browser_click",
            "browser_type",
            "browser_scroll",
            "browser_key_press",
            "browser_screenshot",
            "task_complete",
            "browser_set_milestone",
        ]
        for t in expected_atomic:
            self.assertIn(t, tool_names, f"Expected atomic OODA tool '{t}' in MCP registry.")


if __name__ == "__main__":
    unittest.main()
