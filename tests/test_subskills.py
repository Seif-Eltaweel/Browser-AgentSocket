"""
Unit and Integration Tests for Session-Isolated Subskills & Borrowing Engine (Spec 13)
"""

import os
import shutil
import tempfile
import unittest
from fastapi.testclient import TestClient

from server.models import (
    SubskillModel,
    SubskillsIndexModel,
    BorrowSubskillPayload,
    RegisterSubskillPayload,
    SessionEventType,
)
from server.session_manager import SessionManager
from server.socket_server import app, state


class TestSubskillsEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.logs_dir = os.path.join(self.temp_dir, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.manager = SessionManager(base_log_dir=self.logs_dir)
        self.client = TestClient(app)
        self.client.headers.update({"X-AgentSocket-Token": state.server_token})
        state.global_permissions["enable_subskills"] = True

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_session_folder_structure(self):
        """Verify active session automatically creates input/, output/, adhocs/, artifacts/ folders."""
        session = self.manager.get_or_create_session(
            tab_group_id=123,
            tab_group_name="Test Subskills Group",
            agent_name="TestAgent"
        )
        self.assertTrue(os.path.isdir(session.input_dir))
        self.assertTrue(os.path.isdir(session.output_dir))
        self.assertTrue(os.path.isdir(session.adhocs_dir))
        self.assertTrue(os.path.isdir(session.artifacts_dir))

        paths = self.manager.get_session_paths(session.session_id)
        self.assertEqual(paths["input_dir"], session.input_dir)
        self.assertEqual(paths["output_dir"], session.output_dir)
        self.assertEqual(paths["adhocs_dir"], session.adhocs_dir)
        self.assertEqual(paths["artifacts_dir"], session.artifacts_dir)

    def test_register_and_list_subskills(self):
        """Verify subskill registration, indexing, search, and tag filtering."""
        # Create a mock source session
        session = self.manager.get_or_create_session(
            tab_group_id=200,
            tab_group_name="Source CRM Run",
            agent_name="TestAgent"
        )
        # Create sub_skill.md and an adhoc script in source
        playbook_content = """---
name: test-crm-enricher
display_title: "Test CRM Profile Enricher"
description: "Tested playbook for CRM enrichment."
tags: ["crm", "enrichment", "test"]
---
# CRM Playbook
Test instructions.
"""
        with open(os.path.join(session.session_dir, "sub_skill.md"), "w", encoding="utf-8") as f:
            f.write(playbook_content)

        with open(os.path.join(session.adhocs_dir, "extract_tool.py"), "w", encoding="utf-8") as f:
            f.write("# Extract helper tool\nprint('extracted')\n")

        # Register subskill
        reg_res = self.manager.register_subskill(
            session_path=session.session_dir,
            name="test-crm-enricher",
            display_title="Test CRM Profile Enricher",
            description="Tested playbook for CRM enrichment.",
            tags=["crm", "enrichment", "test"],
            adhoc_tools=["extract_tool.py"]
        )
        self.assertEqual(reg_res["status"], "success")

        # List subskills
        all_skills = self.manager.list_subskills()
        self.assertEqual(len(all_skills), 1)
        self.assertEqual(all_skills[0]["name"], "test-crm-enricher")

        # Query filter
        match = self.manager.list_subskills(query="CRM")
        self.assertEqual(len(match), 1)
        no_match = self.manager.list_subskills(query="nonexistent")
        self.assertEqual(len(no_match), 0)

        # Tag filter
        tag_match = self.manager.list_subskills(tags=["enrichment"])
        self.assertEqual(len(tag_match), 1)
        tag_no_match = self.manager.list_subskills(tags=["finance"])
        self.assertEqual(len(tag_no_match), 0)

    def test_get_subskill_details(self):
        """Verify retrieving full subskill details and playbook content."""
        session = self.manager.get_or_create_session(tab_group_id=300, tab_group_name="Playbook Run")
        with open(os.path.join(session.session_dir, "sub_skill.md"), "w", encoding="utf-8") as f:
            f.write("# Custom Subskill Playbook Content\n\nSelectors: `.custom-btn`")

        self.manager.register_subskill(
            session_path=session.session_dir,
            name="custom-scraper",
            display_title="Custom Scraper",
            description="Extracts data from custom pages.",
            tags=["scraper"]
        )

        details = self.manager.get_subskill("custom-scraper")
        self.assertIsNotNone(details)
        self.assertEqual(details["name"], "custom-scraper")
        self.assertIn("Custom Subskill Playbook Content", details["playbook_markdown"])

    def test_borrow_subskill_workflow(self):
        """Verify complete borrowing lifecycle: playbook copy, adhocs copy, input copy, event logging."""
        # 1. Setup source session
        src_session = self.manager.get_or_create_session(tab_group_id=400, tab_group_name="Source Session")
        with open(os.path.join(src_session.session_dir, "sub_skill.md"), "w", encoding="utf-8") as f:
            f.write("# Source Playbook Content")
        with open(os.path.join(src_session.adhocs_dir, "probe_dom.py"), "w", encoding="utf-8") as f:
            f.write("# DOM Probe script\n")

        self.manager.register_subskill(
            session_path=src_session.session_dir,
            name="borrow-target-skill",
            display_title="Borrow Target Skill",
            tags=["borrow"]
        )

        # 2. Prepare sample input file to pass during borrow
        sample_input = os.path.join(self.temp_dir, "sample_input.csv")
        with open(sample_input, "w", encoding="utf-8") as f:
            f.write("id,url\n1,https://example.com/user1\n")

        # 3. Borrow subskill into a new session
        borrow_res = self.manager.borrow_subskill(
            name="borrow-target-skill",
            target_session_id_or_title_or_path="Batch 2 Run",
            tab_group_id=500,
            input_file_path=sample_input
        )
        self.assertEqual(borrow_res["status"], "success")
        target_dir = borrow_res["target_session_dir"]

        # Check copied files: sub_skill.md and session_manifest.json exist, tools remain referenced (Spec 18)
        self.assertTrue(os.path.exists(os.path.join(target_dir, "sub_skill.md")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "session_manifest.json")))
        # Lean staging: tools are referenced, not physically duplicated into target adhocs/
        self.assertFalse(os.path.exists(os.path.join(target_dir, "adhocs", "probe_dom.py")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "input", "sample_input.csv")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "SESSION_DOCUMENT.md")))

        # Check hierarchical resolution resolves probe_dom.py via subskill tier
        resolved = self.manager.resolve_adhoc("probe_dom.py", target_dir)
        self.assertTrue(resolved["found"])
        self.assertEqual(resolved["tier"], "subskill")

        # Check borrow counter incremented in index
        details = self.manager.get_subskill("borrow-target-skill")
        self.assertEqual(details["times_borrowed"], 1)

        # Check subskill_borrowed event logged in target session.jsonl
        sess_details = self.manager.get_session_details(target_dir)
        events = sess_details["events"]
        borrow_events = [e for e in events if e.get("type") == SessionEventType.SUBSKILL_BORROWED.value]
        self.assertEqual(len(borrow_events), 1)
        self.assertEqual(borrow_events[0]["payload"]["subskill_name"], "borrow-target-skill")

    def test_session_document_and_alias(self):
        """Verify SESSION_DOCUMENT.md generation and section completeness."""
        session = self.manager.get_or_create_session(tab_group_id=600, tab_group_name="Document Test Run")

        with open(os.path.join(session.input_dir, "data_in.csv"), "w", encoding="utf-8") as f:
            f.write("col1,col2\nval1,val2\n")

        with open(os.path.join(session.output_dir, "results.csv"), "w", encoding="utf-8") as f:
            f.write("col1,col2,enriched\nval1,val2,yes\n")

        with open(os.path.join(session.adhocs_dir, "helper.py"), "w", encoding="utf-8") as f:
            f.write('"""Helper script docstring."""\n')

        # Finalize session to trigger document generation
        self.manager.finalize_session(session.session_id, end_reason="task_complete")

        doc_path = os.path.join(session.session_dir, "SESSION_DOCUMENT.md")
        self.assertTrue(os.path.exists(doc_path))

        with open(doc_path, "r", encoding="utf-8") as f:
            doc_content = f.read()


        self.assertIn("Session Document: `Document Test Run`", doc_content)
        self.assertIn("data_in.csv", doc_content)
        self.assertIn("results.csv", doc_content)
        self.assertIn("helper.py", doc_content)
        self.assertIn("Helper script docstring.", doc_content)
        self.assertIn("Chronological Execution Timeline Thread", doc_content)

    def test_fastapi_endpoints(self):
        """Verify REST API gateway endpoints for subskills and session documents."""
        # 1. GET /subskills
        resp = self.client.get("/subskills")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

        # 2. GET /subskills/{name} on official reference subskill
        resp = self.client.get("/subskills/linkedin-crm-enricher")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["name"], "linkedin-crm-enricher")

        # 3. GET /session/document
        ref_path = "server/logs/2026-08-21/LinkedIn_CRM_Enricher_08-45_gid101"
        resp = self.client.get("/session/document", params={"path": ref_path})
        self.assertEqual(resp.status_code, 200)
        doc_json = resp.json()
        self.assertEqual(doc_json["status"], "success")
        self.assertIn("Session Document", doc_json["document_markdown"])


if __name__ == "__main__":
    unittest.main()
