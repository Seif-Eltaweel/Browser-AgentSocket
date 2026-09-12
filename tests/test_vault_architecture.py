"""
Unit & Integration Tests for Spec 18: Central Subskills & Adhocs Vault Architecture
Tests zero data loss on log wipe, deduplication across sessions, 3-tier hierarchical resolution,
and continuous tool promotion pipeline.
"""

import json
import os
import shutil
import tempfile
import unittest
from fastapi.testclient import TestClient

from server.models import (
    SessionEventType,
    SessionManifestModel,
    SubskillModel,
)
from server.session_manager import SessionManager
from server.socket_server import app


class TestVaultArchitecture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="vault_test_")
        self.logs_dir = os.path.join(self.temp_dir, "logs")
        self.subskills_dir = os.path.join(self.temp_dir, "subskills")
        self.adhocs_dir = os.path.join(self.temp_dir, "adhocs")

        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.subskills_dir, exist_ok=True)
        os.makedirs(self.adhocs_dir, exist_ok=True)

        # Seed universal adhocs into test adhocs_dir
        with open(os.path.join(self.adhocs_dir, "probe_dom.py"), "w", encoding="utf-8") as f:
            f.write("# Universal probe_dom.py\nprint('universal probe')\n")
        with open(os.path.join(self.adhocs_dir, "export_csv.py"), "w", encoding="utf-8") as f:
            f.write("# Universal export_csv.py\nprint('universal export')\n")

        self.manager = SessionManager(
            base_log_dir=self.logs_dir,
            subskills_dir=self.subskills_dir,
            adhocs_dir=self.adhocs_dir,
        )
        self.client = TestClient(app)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_zero_data_loss_on_log_deletion(self):
        """
        Acceptance Criteria 1: Zero Data Loss on Log Deletion.
        Wiping server/logs/* and running list_subskills() and borrow_subskill()
        must succeed without errors.
        """
        # 1. Register a subskill from an initial session
        sess = self.manager.get_or_create_session(tab_group_id=10, tab_group_name="Init Run")
        with open(os.path.join(sess.session_dir, "sub_skill.md"), "w", encoding="utf-8") as f:
            f.write("# Tested Subskill Playbook\nVerified selectors: `.btn`")
        with open(os.path.join(sess.adhocs_dir, "custom_extractor.py"), "w", encoding="utf-8") as f:
            f.write("# Custom extractor\nprint('extracted')\n")

        reg_res = self.manager.register_subskill(
            session_path=sess.session_dir,
            name="resilient-subskill",
            display_title="Resilient Subskill",
            description="Playbook that survives log wipes.",
            tags=["resilient", "vault"],
            adhoc_tools=["custom_extractor.py"],
        )
        self.assertEqual(reg_res["status"], "success")

        # Verify it was saved inside subskills vault, NOT logs
        vault_path = os.path.join(self.subskills_dir, "resilient-subskill")
        self.assertTrue(os.path.isdir(vault_path))
        self.assertTrue(os.path.isfile(os.path.join(vault_path, "sub_skill.md")))
        self.assertTrue(os.path.isfile(os.path.join(vault_path, "adhocs", "custom_extractor.py")))

        # 2. TOTAL LOG WIPEOUT: Wipe everything in self.logs_dir!
        for item in os.listdir(self.logs_dir):
            item_path = os.path.join(self.logs_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)

        # Clear active memory sessions to simulate fresh reboot
        self.manager.active_sessions.clear()
        self.manager.title_to_group_id.clear()

        # 3. Assert list_subskills() and get_subskill() still succeed with full data
        all_skills = self.manager.list_subskills()
        self.assertEqual(len(all_skills), 1)
        self.assertEqual(all_skills[0]["name"], "resilient-subskill")

        details = self.manager.get_subskill("resilient-subskill")
        self.assertIsNotNone(details)
        self.assertIn("Verified selectors: `.btn`", details["playbook_markdown"])
        self.assertIn("custom_extractor.py", details["available_adhoc_tools"])

        # 4. Assert borrow_subskill() into a new post-wipe session succeeds without error
        borrow_res = self.manager.borrow_subskill(
            name="resilient-subskill",
            target_session_id_or_title_or_path="Post Wipe Task",
            tab_group_id=99,
        )
        self.assertEqual(borrow_res["status"], "success")
        target_dir = borrow_res["target_session_dir"]

        # Check playbook copied and manifest created
        self.assertTrue(os.path.isfile(os.path.join(target_dir, "sub_skill.md")))
        self.assertTrue(os.path.isfile(os.path.join(target_dir, "session_manifest.json")))

        # Check tool resolution works from central vault
        resolved = self.manager.resolve_adhoc("custom_extractor.py", target_dir)
        self.assertTrue(resolved["found"])
        self.assertEqual(resolved["tier"], "subskill")

    def test_deduplication_across_sessions(self):
        """
        Acceptance Criteria 2: Deduplication Verification.
        Running 10 sessions borrowing the same subskill creates 10 session manifests,
        with 0 redundant copies of adhoc scripts.
        """
        # Register a subskill with multiple tools
        sess = self.manager.get_or_create_session(tab_group_id=50, tab_group_name="Master Session")
        with open(os.path.join(sess.session_dir, "sub_skill.md"), "w", encoding="utf-8") as f:
            f.write("# Master Playbook")
        for tool_name in ["tool_a.py", "tool_b.py", "tool_c.py"]:
            with open(os.path.join(sess.adhocs_dir, tool_name), "w", encoding="utf-8") as f:
                f.write(f"# {tool_name}\n")

        self.manager.register_subskill(
            session_path=sess.session_dir,
            name="multi-tool-skill",
            adhoc_tools=["tool_a.py", "tool_b.py", "tool_c.py"],
        )

        # Borrow into 10 distinct sessions
        session_dirs = []
        for i in range(1, 11):
            res = self.manager.borrow_subskill(
                name="multi-tool-skill",
                target_session_id_or_title_or_path=f"Batch Worker {i}",
                tab_group_id=100 + i,
            )
            self.assertEqual(res["status"], "success")
            session_dirs.append(res["target_session_dir"])

        # Verify each of the 10 sessions has a manifest, but 0 adhoc script duplicates
        for s_dir in session_dirs:
            manifest_path = os.path.join(s_dir, "session_manifest.json")
            self.assertTrue(os.path.isfile(manifest_path))

            # Read manifest
            with open(manifest_path, "r", encoding="utf-8") as mf:
                m_data = json.load(mf)
            self.assertEqual(len(m_data["borrowed_subskills"]), 1)
            self.assertEqual(m_data["borrowed_subskills"][0]["name"], "multi-tool-skill")
            self.assertEqual(m_data["borrowed_subskills"][0]["referenced_adhocs"], ["tool_a.py", "tool_b.py", "tool_c.py"])

            # Verify adhocs directory in session contains ZERO copies of tool_a, tool_b, tool_c
            adhocs_in_session = os.listdir(os.path.join(s_dir, "adhocs"))
            self.assertNotIn("tool_a.py", adhocs_in_session)
            self.assertNotIn("tool_b.py", adhocs_in_session)
            self.assertNotIn("tool_c.py", adhocs_in_session)

            # Yet resolution works seamlessly for each
            for t_name in ["tool_a.py", "tool_b.py", "tool_c.py"]:
                resolved = self.manager.resolve_adhoc(t_name, s_dir)
                self.assertTrue(resolved["found"])
                self.assertEqual(resolved["tier"], "subskill")

    def test_three_tier_hierarchical_resolution(self):
        """
        Acceptance Criteria 3: Hierarchical Resolution.
        Session Local Override -> Subskill-Specific Vault -> Universal Shared Vault.
        """
        # 1. Setup a universal tool
        with open(os.path.join(self.adhocs_dir, "universal_only.py"), "w", encoding="utf-8") as f:
            f.write("# Universal only\nprint('tier universal')\n")

        # 2. Setup a subskill tool (with same name as a universal tool to test override)
        with open(os.path.join(self.adhocs_dir, "shared_name.py"), "w", encoding="utf-8") as f:
            f.write("# Universal shared_name\nprint('from universal')\n")

        sess1 = self.manager.get_or_create_session(tab_group_id=70, tab_group_name="Subskill Source")
        with open(os.path.join(sess1.session_dir, "sub_skill.md"), "w", encoding="utf-8") as f:
            f.write("# Subskill Playbook")
        with open(os.path.join(sess1.adhocs_dir, "shared_name.py"), "w", encoding="utf-8") as f:
            f.write("# Subskill shared_name\nprint('from subskill')\n")
        with open(os.path.join(sess1.adhocs_dir, "subskill_only.py"), "w", encoding="utf-8") as f:
            f.write("# Subskill only\nprint('from subskill')\n")

        self.manager.register_subskill(
            session_path=sess1.session_dir,
            name="tier-test-skill",
            adhoc_tools=["shared_name.py", "subskill_only.py"],
        )

        # 3. Create target session borrowing the subskill
        borrow_res = self.manager.borrow_subskill(
            name="tier-test-skill",
            target_session_id_or_title_or_path="Tier Test Session",
            tab_group_id=71,
        )
        target_dir = borrow_res["target_session_dir"]

        # Case A: Tool only in universal vault -> resolves to universal
        res_univ = self.manager.resolve_adhoc("universal_only.py", target_dir)
        self.assertTrue(res_univ["found"])
        self.assertEqual(res_univ["tier"], "universal")

        # Case B: Tool in both universal and borrowed subskill -> resolves to subskill tier!
        res_sub = self.manager.resolve_adhoc("shared_name.py", target_dir)
        self.assertTrue(res_sub["found"])
        self.assertEqual(res_sub["tier"], "subskill")
        self.assertEqual(res_sub["subskill_name"], "tier-test-skill")

        # Case C: Create a local override in session/adhocs/shared_name.py -> resolves to local override!
        local_override_path = os.path.join(target_dir, "adhocs", "shared_name.py")
        with open(local_override_path, "w", encoding="utf-8") as f:
            f.write("# Local override shared_name\nprint('from local override')\n")

        res_local = self.manager.resolve_adhoc("shared_name.py", target_dir)
        self.assertTrue(res_local["found"])
        self.assertEqual(res_local["tier"], "local")
        self.assertEqual(res_local["path"], local_override_path)

        # Case D: Non-existent tool -> returns not found
        res_none = self.manager.resolve_adhoc("completely_unknown.py", target_dir)
        self.assertFalse(res_none["found"])
        self.assertEqual(res_none["tier"], "none")

    def test_promotion_pipeline_and_syntax_validation(self):
        """
        Acceptance Criteria 4: Promotion Validation.
        Creating a new tool in a session and calling promotion places the tool in the
        permanent vault immediately, rejecting syntax errors.
        """
        sess = self.manager.get_or_create_session(tab_group_id=80, tab_group_name="Promotion Session")

        # 1. Broken syntax file
        broken_tool = os.path.join(sess.adhocs_dir, "broken_syntax.py")
        with open(broken_tool, "w", encoding="utf-8") as f:
            f.write("def bad_syntax(: pass\n")

        fail_res = self.manager.promote_adhoc(
            session_path=sess.session_dir,
            tool_name="broken_syntax.py",
            target="universal",
        )
        self.assertEqual(fail_res["status"], "error")
        self.assertIn("Python syntax error", fail_res["message"])

        # 2. Valid tool promoted to Universal Shared Vault
        valid_univ_tool = os.path.join(sess.adhocs_dir, "new_universal_tool.py")
        with open(valid_univ_tool, "w", encoding="utf-8") as f:
            f.write('"""Universal validator."""\nprint("valid universal tool")\n')

        ok_univ = self.manager.promote_adhoc(
            session_path=sess.session_dir,
            tool_name="new_universal_tool.py",
            target="universal",
        )
        self.assertEqual(ok_univ["status"], "success")
        self.assertTrue(os.path.isfile(os.path.join(self.adhocs_dir, "new_universal_tool.py")))

        # Check it appears in list_adhocs()
        all_adhocs = [t["name"] for t in self.manager.list_adhocs()]
        self.assertIn("new_universal_tool.py", all_adhocs)

        # 3. Valid tool promoted to Subskill Vault
        # First register a target subskill
        with open(os.path.join(sess.session_dir, "sub_skill.md"), "w", encoding="utf-8") as f:
            f.write("# Target Subskill Playbook")
        self.manager.register_subskill(
            session_path=sess.session_dir,
            name="target-subskill",
        )

        valid_sub_tool = os.path.join(sess.adhocs_dir, "subskill_extension.py")
        with open(valid_sub_tool, "w", encoding="utf-8") as f:
            f.write('"""Subskill extension."""\nprint("valid subskill tool")\n')

        ok_sub = self.manager.promote_adhoc(
            session_path=sess.session_dir,
            tool_name="subskill_extension.py",
            target="subskill",
            subskill_name="target-subskill",
        )
        self.assertEqual(ok_sub["status"], "success")
        subskill_vault_tool = os.path.join(self.subskills_dir, "target-subskill", "adhocs", "subskill_extension.py")
        self.assertTrue(os.path.isfile(subskill_vault_tool))

        # Check subskills index was updated to include this tool
        details = self.manager.get_subskill("target-subskill")
        self.assertIn("subskill_extension.py", details["adhoc_tools"])

    def test_run_adhoc_execution(self):
        """Verify executing an adhoc tool via run_adhoc subprocess runner."""
        sess = self.manager.get_or_create_session(tab_group_id=90, tab_group_name="Runner Session")
        local_script = os.path.join(sess.adhocs_dir, "runner_test.py")
        with open(local_script, "w", encoding="utf-8") as f:
            f.write("import sys\nprint('Hello ' + ' '.join(sys.argv[1:]))\n")

        res = self.manager.run_adhoc(
            tool_name="runner_test.py",
            session_dir_or_path=sess.session_dir,
            args=["AgentSocket", "Vault"],
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["returncode"], 0)
        self.assertIn("Hello AgentSocket Vault", res["stdout"])
        self.assertEqual(res["tier"], "local")


if __name__ == "__main__":
    unittest.main()
