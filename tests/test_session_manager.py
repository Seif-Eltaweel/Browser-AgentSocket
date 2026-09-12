"""
Unit tests for Server-Side SessionManager (Spec 11).
Tests hierarchical logging, latency benchmarking, artifact offloading,
atomic index updates, zero-credential takeover, and introspection tools.
"""

import json
import os
import shutil
import tempfile
import time
import unittest

from server.models import (
    SessionStatus,
    SessionEventType,
    SessionEventModel,
    SessionSummaryModel,
    MonthlyIndexModel,
)
from server.session_manager import SessionManager, format_session_thread


class TestSessionManager(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agent_socket_test_logs_")
        self.mgr = SessionManager(base_log_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_or_create_session(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=9821,
            tab_group_name="LinkedIn Lead Gen",
            group_color="purple",
            agent_name="Antigravity Local"
        )
        self.assertEqual(session.tab_group_id, 9821)
        self.assertEqual(session.tab_group_name, "LinkedIn Lead Gen")
        self.assertEqual(session.status, SessionStatus.ACTIVE)
        self.assertTrue(os.path.exists(session.session_dir))
        self.assertTrue(os.path.exists(session.artifacts_dir))
        self.assertTrue(os.path.exists(session.jsonl_path))

        # Check session.jsonl contains session_start
        with open(session.jsonl_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["type"], SessionEventType.SESSION_START.value)

        # Check index.json updated
        index_data = self.mgr._read_index()
        self.assertTrue(len(index_data.months) > 0)
        first_month = list(index_data.months.keys())[0]
        self.assertEqual(len(index_data.months[first_month]), 1)
        self.assertEqual(index_data.months[first_month][0].session_id, session.session_id)

    def test_log_event_latency_calculation(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=123,
            tab_group_name="Test Workflow"
        )
        t_start = time.time()
        time.sleep(0.05)
        t_end = time.time()

        event = self.mgr.log_event(
            tab_group_id=123,
            event_type=SessionEventType.NAVIGATE,
            title="Navigate to Dashboard",
            start_time=t_start,
            end_time=t_end,
            tab_id=10,
            url="https://example.com/dashboard",
            payload={"reused": False}
        )
        self.assertIsNotNone(event)
        self.assertGreaterEqual(event.duration_ms, 40.0)
        self.assertEqual(session.action_count, 1)
        self.assertEqual(session.event_count, 2)  # session_start + navigate

    def test_artifact_offload_threshold_large_string(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=456,
            tab_group_name="Scraper Task"
        )
        large_html = "<html>" + "<div>content</div>" * 1000 + "</html>"  # > 15 KB
        self.assertGreater(len(large_html), 10000)

        t_start = time.time()
        event = self.mgr.log_event(
            tab_group_id=456,
            event_type=SessionEventType.EXECUTE_JS,
            title="Extract DOM",
            start_time=t_start,
            end_time=t_start + 0.1,
            payload={"script": "document.body.innerHTML", "result": large_html}
        )

        self.assertIsNotNone(event.artifact_link)
        self.assertTrue(event.artifact_link.startswith("artifacts/execute_js_"))
        self.assertTrue(event.payload.get("is_offloaded"))
        self.assertEqual(session.artifacts_count, 1)

        # Verify offloaded file exists and has full content
        art_path = os.path.join(session.session_dir, event.artifact_link)
        self.assertTrue(os.path.exists(art_path))
        with open(art_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        self.assertEqual(saved_data["result"], large_html)

    def test_artifact_offload_threshold_large_array(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=789,
            tab_group_name="Batch Scrape"
        )
        items = [{"id": i, "name": f"Lead {i}"} for i in range(75)]  # 75 items > 50

        t_start = time.time()
        event = self.mgr.log_event(
            tab_group_id=789,
            event_type=SessionEventType.EXECUTE_JS,
            title="Extract Contact Cards",
            start_time=t_start,
            end_time=t_start + 0.05,
            payload={"result": items}
        )

        self.assertIsNotNone(event.artifact_link)
        self.assertTrue(event.payload.get("is_offloaded"))
        self.assertIn("Array of 75 items", event.payload.get("result_preview", ""))

    def test_screenshot_artifact_saving(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=999,
            tab_group_name="Visual Exception Task"
        )
        fake_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

        t_start = time.time()
        event = self.mgr.log_event(
            tab_group_id=999,
            event_type=SessionEventType.SECURITY_ABORT,
            title="Security Abort",
            start_time=t_start,
            end_time=t_start + 0.01,
            payload={"reason": "Password field detected"},
            screenshot_bytes=fake_png_bytes
        )

        self.assertIsNotNone(event.artifact_link)
        self.assertTrue(event.artifact_link.startswith("artifacts/error_screenshot_"))
        screenshot_path = os.path.join(session.session_dir, event.artifact_link)
        self.assertTrue(os.path.exists(screenshot_path))
        with open(screenshot_path, "rb") as f:
            self.assertEqual(f.read(), fake_png_bytes)

    def test_zero_credential_human_takeover_logging(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=111,
            tab_group_name="Auth Challenge"
        )
        t_takeover = time.time()
        # Log takeover start
        self.mgr.log_event(
            tab_group_id=111,
            event_type=SessionEventType.HUMAN_TAKEOVER,
            title="Operator Manual Takeover",
            start_time=t_takeover,
            end_time=t_takeover,
            payload={"reason": "CAPTCHA challenge"}
        )

        time.sleep(0.02)
        t_release = time.time()
        dur_ms = (t_release - t_takeover) * 1000.0

        # Log release
        self.mgr.log_event(
            tab_group_id=111,
            event_type=SessionEventType.HUMAN_RELEASE,
            title="Operator Release",
            start_time=t_takeover,
            end_time=t_release,
            payload={"notes": "Solved slide puzzle", "takeover_duration_ms": dur_ms}
        )

        self.assertEqual(session.takeover_count, 2)

        # Inspect jsonl - ensure zero credentials exist
        details = self.mgr.get_session_details(session.session_path)
        events = details.get("events", [])
        for e in events:
            p = e.get("payload") or {}
            self.assertNotIn("password", p)
            self.assertNotIn("credentials", p)

    def test_finalize_session(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=222,
            tab_group_name="Complete Flow"
        )
        finalized = self.mgr.finalize_session(
            tab_group_id=222,
            status=SessionStatus.COMPLETED,
            end_reason="task_complete"
        )
        self.assertIsNotNone(finalized)
        self.assertEqual(finalized.status, SessionStatus.COMPLETED)
        self.assertTrue(finalized.tab_group_name.startswith("✅"))
        self.assertTrue(finalized.session_title.startswith("✅"))
        self.assertIsNotNone(finalized.end_time)
        self.assertIsNotNone(finalized.duration_ms)

        # Session should be removed from active sessions
        self.assertIsNone(self.mgr.get_active_session_by_group_id(222))

        # Check index.json updated to completed
        summaries = self.mgr.query_history(query_hint="Complete Flow")
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["status"], SessionStatus.COMPLETED.value)
        self.assertTrue(summaries[0]["tab_group_name"].startswith("✅"))

    def test_inactivity_watchdog(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=333,
            tab_group_name="Idle Flow"
        )
        # Artificially age session
        session.last_action_time = time.time() - 360.0

        timed_out = self.mgr.check_inactivity(inactivity_threshold_seconds=300.0)
        self.assertIn(333, timed_out)
        self.assertIsNone(self.mgr.get_active_session_by_group_id(333))

        summaries = self.mgr.query_history(query_hint="Idle Flow")
        self.assertEqual(summaries[0]["status"], SessionStatus.STOPPED.value)
        self.assertEqual(summaries[0]["end_reason"], "inactivity_timeout")

    def test_disconnect_handler(self):
        self.mgr.get_or_create_session(tab_group_id=444, tab_group_name="Session 1")
        self.mgr.get_or_create_session(tab_group_id=555, tab_group_name="Session 2")
        self.assertEqual(len(self.mgr.active_sessions), 2)

        aborted = self.mgr.handle_disconnect()
        self.assertEqual(len(aborted), 2)
        self.assertEqual(len(self.mgr.active_sessions), 0)

        summaries = self.mgr.query_history(limit=10)
        for s in summaries:
            self.assertEqual(s["status"], SessionStatus.ABORTED.value)
            self.assertEqual(s["end_reason"], "browser_disconnected")

    def test_query_history_and_details_and_artifact(self):
        session = self.mgr.get_or_create_session(tab_group_id=777, tab_group_name="Target Search")
        large_json = {"contacts": [{"name": f"User {i}"} for i in range(60)]}

        self.mgr.log_event(
            tab_group_id=777,
            event_type=SessionEventType.EXECUTE_JS,
            title="Extract Leads",
            start_time=time.time(),
            payload={"result": large_json["contacts"]}
        )
        self.mgr.finalize_session(777, SessionStatus.COMPLETED)

        # 1. Query history
        hist = self.mgr.query_history(query_hint="Target Search", limit=5)
        self.assertEqual(len(hist), 1)
        sess_path = hist[0]["session_path"]

        # 2. Get details
        details = self.mgr.get_session_details(sess_path)
        self.assertEqual(details["status"], "success")
        self.assertGreaterEqual(details["event_count"], 3)  # start, execute_js, end

        # 3. Get artifact
        js_event = next(e for e in details["events"] if e["type"] == SessionEventType.EXECUTE_JS.value)
        art_link = js_event["artifact_link"]
        self.assertIsNotNone(art_link)

        art_data = self.mgr.get_session_artifact(sess_path, art_link)
        self.assertIsInstance(art_data, dict)
        self.assertIn("result", art_data)
        self.assertEqual(len(art_data["result"]), 60)

    def test_export_all_to_markdown(self):
        session = self.mgr.get_or_create_session(tab_group_id=888, tab_group_name="Export Report Test")
        self.mgr.log_event(
            tab_group_id=888,
            event_type=SessionEventType.NAVIGATE,
            title="Navigate Home",
            start_time=time.time(),
            payload={"target_url": "https://example.com"}
        )
        self.mgr.finalize_session(888, SessionStatus.COMPLETED)

        out_md_path = os.path.join(self.test_dir, "REPORT.md")
        md_text = self.mgr.export_all_to_markdown(output_path=out_md_path)

        self.assertTrue(os.path.exists(out_md_path))
        self.assertIn("AgentSocket Session History & Execution Timeline Master Report", md_text)
        self.assertIn("Export Report Test", md_text)
        self.assertIn("Navigate Home", md_text)

    def test_format_session_thread_full_flow(self):
        # Base timestamp: 2026-08-21 08:45:10
        t0 = 1787309110.0  # mock 08:45:10

        events = [
            {
                "type": "session_start",
                "start_time": t0,
                "end_time": t0,
                "duration_ms": 0.0,
                "title": "Session Started: LinkedIn Scraper",
                "payload": {"group_name": "LinkedIn Scraper", "session_title": "LinkedIn Scraper | 2026-08-21_08:45:10"}
            },
            {
                "type": "navigate",
                "start_time": t0,
                "end_time": t0 + 0.210,
                "duration_ms": 210.0,
                "url": "https://linkedin.com/feed",
                "title": "Navigate to https://linkedin.com/feed",
                "payload": {"target_url": "https://linkedin.com/feed"}
            },
            {
                "type": "execute_js",
                "start_time": t0 + 2.0,
                "end_time": t0 + 2.045,
                "duration_ms": 45.0,
                "title": "Query selector for feed items",
                "payload": {"script": "document.querySelectorAll('.feed-item')", "result": "found 10"}
            },
            {
                "type": "security_abort",
                "start_time": t0 + 5.0,
                "end_time": t0 + 5.0,
                "duration_ms": 0.0,
                "title": "Security Abort Triggered",
                "payload": {"reason": "Password field detected"},
                "artifact_link": "artifacts/error_screenshot_evt_01.png"
            },
            {
                "type": "human_takeover",
                "start_time": t0 + 5.0,
                "end_time": t0 + 30.0,
                "duration_ms": 25000.0,
                "title": "Human Operator Takeover",
                "payload": {"notes": "Solved 2FA challenge"}
            },
            {
                "type": "human_release",
                "start_time": t0 + 30.0,
                "end_time": t0 + 30.0,
                "duration_ms": 0.0,
                "title": "Human Operator Release Handoff",
                "payload": {"notes": "Resumed automation context"}
            },
            {
                "type": "execute_js",
                "start_time": t0 + 32.0,
                "end_time": t0 + 32.180,
                "duration_ms": 180.0,
                "title": "Scraped 25 profile links",
                "payload": {"result": ["link1", "link2"]}
            },
            {
                "type": "session_end",
                "start_time": t0 + 35.0,
                "end_time": t0 + 35.0,
                "duration_ms": 0.0,
                "title": "Session Finalized (completed): task_complete",
                "payload": {"status": "completed"}
            }
        ]

        thread_str = format_session_thread(events, session_title="LinkedIn Scraper | 2026-08-21_08:45:10", total_duration_ms=35000.0)

        # Assert Header & Divider
        self.assertIn("🧵 Thread: LinkedIn Scraper | 2026-08-21_08:45:10 (Total Run: 35.0s)", thread_str)
        self.assertIn("━" * 65, thread_str)

        # Assert Lines structure
        lines = thread_str.split("\n")
        self.assertEqual(len(lines), 10)  # 1 header + 1 divider + 8 events

        # Event 1: SESSION_START
        self.assertTrue(lines[2].startswith("├── "))
        self.assertIn("(T+00.0s) 🚀 SESSION_START", lines[2])
        self.assertIn("│    --   │ Group: \"LinkedIn Scraper\"", lines[2])

        # Event 2: NAVIGATE
        self.assertTrue(lines[3].startswith("├── "))
        self.assertIn("🌐 NAVIGATE", lines[3])
        self.assertIn("│  210ms  │ https://linkedin.com/feed", lines[3])

        # Event 3: EXECUTE_JS
        self.assertTrue(lines[4].startswith("├── "))
        self.assertIn("(T+02.0s) ⚡ EXECUTE_JS", lines[4])
        self.assertIn("│   45ms  │ Query selector for feed items", lines[4])

        # Event 4: SECURITY_ABORT
        self.assertTrue(lines[5].startswith("├── "))
        self.assertIn("(T+05.0s) 🔒 SECURITY_ABORT", lines[5])
        self.assertIn("│    0ms  │ Password field detected (Snapshot saved)", lines[5])

        # Event 5: HUMAN_TAKEOVER
        self.assertTrue(lines[6].startswith("├── "))
        self.assertIn("(T+05.0s) ✋ HUMAN_TAKEOVER", lines[6])
        self.assertIn("│  25.0s  │ Operator: \"Solved 2FA challenge\"", lines[6])

        # Event 6: HUMAN_RELEASE
        self.assertTrue(lines[7].startswith("├── "))
        self.assertIn("(T+30.0s) ▶ HUMAN_RELEASE", lines[7])
        self.assertIn("│    0ms  │ Resumed automation context", lines[7])

        # Event 7: EXECUTE_JS
        self.assertTrue(lines[8].startswith("├── "))
        self.assertIn("(T+32.0s) ⚡ EXECUTE_JS", lines[8])
        self.assertIn("│  180ms  │ Scraped 25 profile links", lines[8])

        # Event 8: SESSION_END (last event has └── )
        self.assertTrue(lines[9].startswith("└── "))
        self.assertIn("(T+35.0s) ✅ SESSION_END", lines[9])
        self.assertIn("│    --   │ Status: COMPLETED", lines[9])

    def test_get_session_details_includes_formatted_thread(self):
        session = self.mgr.get_or_create_session(tab_group_id=601, tab_group_name="Thread Test")
        self.mgr.log_event(
            tab_group_id=601,
            event_type=SessionEventType.NAVIGATE,
            title="Navigate to Search",
            start_time=time.time(),
            payload={"target_url": "https://example.com/search"}
        )
        self.mgr.finalize_session(601, SessionStatus.COMPLETED)

        details = self.mgr.get_session_details(session.session_path)
        self.assertIn("formatted_thread", details)
        self.assertIn("🧵 Thread:", details["formatted_thread"])
        self.assertIn("🌐 NAVIGATE", details["formatted_thread"])
        self.assertIn("https://example.com/search", details["formatted_thread"])
        self.assertIn("✅ SESSION_END", details["formatted_thread"])

    def test_generate_thread_document(self):
        session = self.mgr.get_or_create_session(
            tab_group_id=777,
            tab_group_name="Batch 5 CRM Enrichment",
            group_color="purple"
        )
        self.mgr.log_event(
            tab_group_id=777,
            event_type=SessionEventType.NAVIGATE,
            title="Navigate to Profile",
            start_time=time.time(),
            payload={"target_url": "https://example.com/in/john"}
        )
        self.mgr.log_event(
            tab_group_id=777,
            event_type=SessionEventType.EXECUTE_JS,
            title="Extract Bio",
            start_time=time.time(),
            payload={"result": "Software Engineer"}
        )
        self.mgr.finalize_session(777, SessionStatus.COMPLETED)

        thread_path = os.path.join(session.session_dir, "THREAD.md")
        doc_path = os.path.join(session.session_dir, "SESSION_DOCUMENT.md")

        self.assertTrue(os.path.exists(thread_path), "THREAD.md should be generated in session directory")
        self.assertTrue(os.path.exists(doc_path), "SESSION_DOCUMENT.md should be generated in session directory")

        with open(thread_path, "r", encoding="utf-8") as f:
            thread_content = f.read()

        self.assertIn("# 🧵 Session Execution Thread: Batch 5 CRM Enrichment", thread_content)
        self.assertIn("* **Session ID:**", thread_content)
        self.assertIn("* **Total Actions:** 2", thread_content)
        self.assertIn("* **Tab Group ID:** `777` (purple)", thread_content)
        self.assertIn("## ⏱️ Chronological Execution Log", thread_content)
        self.assertIn("🌐 NAVIGATE", thread_content)
        self.assertIn("⚡ EXECUTE_JS", thread_content)

        with open(doc_path, "r", encoding="utf-8") as f:
            doc_content = f.read()
        self.assertIn("[`THREAD.md`](THREAD.md)", doc_content)

    def test_inactivity_watchdog_600s_default(self):
        session = self.mgr.get_or_create_session(tab_group_id=888, tab_group_name="Idle Session")
        session.last_action_time = time.time() - 350.0  # 350s ago (less than 600s)

        # 350s should NOT trigger timeout when threshold is default 600.0s
        timed_out = self.mgr.check_inactivity()
        self.assertEqual(len(timed_out), 0)
        self.assertEqual(session.status, SessionStatus.ACTIVE)

        # Now age it past 600s
        session.last_action_time = time.time() - 605.0
        timed_out = self.mgr.check_inactivity()
        self.assertEqual(timed_out, [888])
        self.assertEqual(session.status, SessionStatus.STOPPED)
        self.assertEqual(session.end_reason, "inactivity_timeout")

    def test_session_deduplication_and_title_reuse(self):
        # 1. Create first session
        sess1 = self.mgr.get_or_create_session(tab_group_id=101, tab_group_name="LinkedIn Scraper")
        sess1_dir = sess1.session_dir

        # 2. Re-request with same title but new Chrome tab_group_id (e.g. 102)
        sess2 = self.mgr.get_or_create_session(tab_group_id=102, tab_group_name="LinkedIn Scraper")

        # Must reuse the same session directory and object without creating duplicate folders
        self.assertEqual(sess1_dir, sess2.session_dir)
        self.assertEqual(sess2.tab_group_id, 102)
        self.assertIn(102, self.mgr.active_sessions)

        # 3. Request with "✅ LinkedIn Scraper" (after completion rename)
        sess3 = self.mgr.get_or_create_session(tab_group_id=103, tab_group_name="✅ LinkedIn Scraper")
        self.assertEqual(sess1_dir, sess3.session_dir)


if __name__ == "__main__":
    unittest.main()
