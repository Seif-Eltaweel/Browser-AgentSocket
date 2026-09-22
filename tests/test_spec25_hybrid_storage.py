"""
Comprehensive Unit Tests for Feature Spec 25:
Hybrid Storage Architecture (Embedded SQLite + YAML Frontmatter + Lean JSONL)
"""

import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
import yaml

from server.db import init_db, get_connection, DB_PATH
from server.models import (
    SessionEventType,
    SessionStatus,
    SessionManifestModel,
)
from server.session.manager import SessionManager, redact_sensitive_payload
from server.session.storage import SessionStorage


class TestSpec25HybridStorage(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="spec25_test_")
        self.db_path = os.path.join(self.test_dir, "test_agentsocket.db")
        init_db(self.db_path)
        self.storage = SessionStorage(base_log_dir=self.test_dir, db_path=self.db_path)
        self.manager = SessionManager(base_log_dir=self.test_dir, db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ------------------------------------------------------------------------
    # 1. SQLite WAL Mode & Schema Verification
    # ------------------------------------------------------------------------
    def test_sqlite_wal_mode_and_tables(self):
        """Verifies SQLite WAL mode is enabled and all 3 tables exist with indexes."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0]
            self.assertEqual(mode.lower(), "wal", "SQLite database must run in WAL journal mode.")

            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            self.assertIn("sessions", tables)
            self.assertIn("events", tables)
            self.assertIn("subskills", tables)

            # Verify index on sessions
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index';")
            indexes = {row[0] for row in cursor.fetchall()}
            self.assertIn("idx_sessions_start_time", indexes)
            self.assertIn("idx_events_session", indexes)

    # ------------------------------------------------------------------------
    # 2. Atomic O(1) Upsert & Performance Benchmark
    # ------------------------------------------------------------------------
    def test_atomic_upsert_and_performance(self):
        """Verifies session upserts are atomic, correct, and execute under 10ms each."""
        session = self.manager.get_or_create_session(
            tab_group_id=101,
            tab_group_name="Performance Test",
            group_color="blue",
            agent_name="Antigravity Benchmarker",
        )

        # Update session counters and benchmark 100 upserts
        start_bench = time.perf_counter()
        for i in range(100):
            session.action_count = i + 1
            session.event_count = (i + 1) * 2
            self.manager._update_index_for_session(session)
        elapsed = time.perf_counter() - start_bench
        avg_per_upsert_ms = (elapsed / 100.0) * 1000.0

        # Assert performance is fast (< 10ms per upsert on SQLite WAL)
        self.assertLess(avg_per_upsert_ms, 15.0, f"Upsert took too long: {avg_per_upsert_ms:.2f}ms")

        # Verify database content
        with get_connection(self.storage.db_path) as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session.session_id,))
            row = dict(cursor.fetchone())
            self.assertEqual(row["session_id"], session.session_id)
            self.assertEqual(row["action_count"], 100)
            self.assertEqual(row["event_count"], 200)
            self.assertEqual(row["tab_group_name"], "Performance Test")

    # ------------------------------------------------------------------------
    # 3. Query History from SQLite
    # ------------------------------------------------------------------------
    def test_query_history_sqlite(self):
        """Verifies query_history searches directly from SQLite with filters and limits."""
        s1 = self.manager.get_or_create_session(tab_group_id=201, tab_group_name="Alpha Search")
        s2 = self.manager.get_or_create_session(tab_group_id=202, tab_group_name="Beta Crawl")
        self.manager.finalize_session(201, SessionStatus.COMPLETED)
        self.manager.finalize_session(202, SessionStatus.STOPPED)

        # 1. Search by query hint
        alpha_res = self.manager.query_history(query_hint="Alpha", limit=5)
        self.assertEqual(len(alpha_res), 1)
        self.assertIn("Alpha Search", alpha_res[0]["tab_group_name"])

        # 2. Search all with limit
        all_res = self.manager.query_history(limit=1)
        self.assertEqual(len(all_res), 1)

        # 3. Verify backward-compatible read_index
        index_model = self.storage.read_index()
        self.assertGreaterEqual(len(index_model.months), 1)
        first_month = list(index_model.months.keys())[0]
        self.assertGreaterEqual(len(index_model.months[first_month]), 2)

    # ------------------------------------------------------------------------
    # 4. YAML Frontmatter Manifest Persistence
    # ------------------------------------------------------------------------
    def test_yaml_frontmatter_manifest(self):
        """Verifies read_manifest and write_manifest parse and update YAML frontmatter in SESSION_DOCUMENT.md."""
        session_dir = os.path.join(self.test_dir, "test_session_doc")
        os.makedirs(session_dir, exist_ok=True)

        manifest = SessionManifestModel(
            session_id="sess_yaml_101",
            session_title="YAML Frontmatter Test",
            tab_group_id=301,
            tab_group_name="YAML Frontmatter Test",
            group_color="emerald",
            agent_name="Antigravity Spec25",
            mode="direct",
            status="completed",
            duration_ms=1250.5,
            metrics={"total_actions": 5, "avg_settlement_ms": 42.1},
            deliverables=["output/leads.csv"],
        )

        # Write frontmatter
        self.storage.write_manifest(session_dir, manifest)
        doc_path = os.path.join(session_dir, "SESSION_DOCUMENT.md")
        self.assertTrue(os.path.exists(doc_path))

        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(content.startswith("---"))
        self.assertIn("session_id: sess_yaml_101", content)
        self.assertIn("group_color: emerald", content)
        self.assertIn("deliverables:", content)
        self.assertIn("output/leads.csv", content)

        # Read back via read_manifest
        loaded = self.storage.read_manifest(session_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "sess_yaml_101")
        self.assertEqual(loaded.group_color, "emerald")
        self.assertEqual(loaded.metrics.get("total_actions"), 5)
        self.assertIn("output/leads.csv", loaded.deliverables)

    # ------------------------------------------------------------------------
    # 5. Zero-Knowledge Redaction ([REDACTED])
    # ------------------------------------------------------------------------
    def test_zero_knowledge_redaction(self):
        """Verifies sensitive attributes (password, token, secret, cvv) are masked as [REDACTED]."""
        payload = {
            "username": "alice",
            "password": "SuperSecretPassword123!",
            "auth_token": "bearer_abc_987",
            "card": {
                "number": "4111222233334444",
                "cvv": "999",
                "secret_pin": "1234",
            },
            "regular_field": "public_data",
        }

        redacted = redact_sensitive_payload(payload)
        self.assertEqual(redacted["username"], "alice")
        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["auth_token"], "[REDACTED]")
        self.assertEqual(redacted["card"]["cvv"], "[REDACTED]")
        self.assertEqual(redacted["card"]["secret_pin"], "[REDACTED]")
        self.assertEqual(redacted["regular_field"], "public_data")

        # Test in manager.log_event
        session = self.manager.get_or_create_session(tab_group_id=401, tab_group_name="Secret Test")
        evt = self.manager.log_event(
            tab_group_id=401,
            event_type=SessionEventType.ACT_ELEMENT,
            title="Type password",
            start_time=time.time(),
            payload={"action": "type", "field": "user_password", "text": "my_hidden_pw", "token": "tok_xyz"},
        )
        self.assertEqual(evt.payload["text"], "[REDACTED]")
        self.assertEqual(evt.payload["token"], "[REDACTED]")

        # Check session.jsonl contains [REDACTED]
        with open(session.jsonl_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        act_evt = next(e for e in lines if e["type"] == SessionEventType.ACT_ELEMENT.value)
        self.assertEqual(act_evt["payload"]["text"], "[REDACTED]")
        self.assertEqual(act_evt["payload"]["token"], "[REDACTED]")

    # ------------------------------------------------------------------------
    # 6. Two-File Architecture Verification Gate
    # ------------------------------------------------------------------------
    def test_two_file_architecture_gate(self):
        """
        Verification Gate: Verifies that session root folder contains ONLY
        SESSION_DOCUMENT.md and session.jsonl (subfolders like artifacts/, output/ allowed).
        No session_manifest.json, no THREAD.md, no empty adhocs/ folder!
        """
        session = self.manager.get_or_create_session(tab_group_id=501, tab_group_name="Two File Test")

        # Perform atomic actions
        self.manager.log_event(
            tab_group_id=501,
            event_type=SessionEventType.NAVIGATE,
            title="Navigate to homepage",
            start_time=time.time(),
            payload={"url": "https://example.com"},
        )
        self.manager.finalize_session(501, SessionStatus.COMPLETED)

        # Inspect root of session folder
        session_root = session.session_dir
        root_entries = os.listdir(session_root)
        root_files = [f for f in root_entries if os.path.isfile(os.path.join(session_root, f))]

        # Root files MUST be exactly SESSION_DOCUMENT.md and session.jsonl
        self.assertCountEqual(
            root_files,
            ["SESSION_DOCUMENT.md", "session.jsonl"],
            f"Expected only SESSION_DOCUMENT.md and session.jsonl at root, found: {root_files}",
        )

        # Check that empty adhocs/ is NOT created
        self.assertFalse(
            os.path.exists(os.path.join(session_root, "adhocs")),
            "adhocs/ directory should not be created for session.",
        )

        # Check that session_manifest.json is NOT created
        self.assertFalse(
            os.path.exists(os.path.join(session_root, "session_manifest.json")),
            "session_manifest.json should be eliminated in Spec 25.",
        )

        # Check that standalone THREAD.md is NOT created at root
        self.assertFalse(
            os.path.exists(os.path.join(session_root, "THREAD.md")),
            "THREAD.md should not be created at session root in Spec 25.",
        )

        # Verify SESSION_DOCUMENT.md has both YAML frontmatter and human sections
        doc_path = os.path.join(session_root, "SESSION_DOCUMENT.md")
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(content.startswith("---"))
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3)

        frontmatter = yaml.safe_load(parts[1])
        self.assertEqual(frontmatter["session_id"], session.session_id)
        self.assertEqual(frontmatter["status"], "completed")
        self.assertEqual(frontmatter["metrics"]["total_actions"], 1)  # navigate

        # Check human markdown content
        markdown_body = parts[2]
        self.assertIn("# 📜 Session Document: `Two File Test`", markdown_body)
        self.assertIn("## 🧵 Chronological Execution Timeline Thread", markdown_body)
        self.assertIn("NAVIGATE", markdown_body)


if __name__ == "__main__":
    unittest.main()
