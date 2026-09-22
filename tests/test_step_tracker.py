"""
Tests for StepTracker atomic progress tracking and Markdown generation (Spec 17).
"""

import json
import os
import shutil
import tempfile
import unittest
from server.session.manager import StepTracker, AtomicStep


class TestStepTracker(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.steps_path = os.path.join(self.test_dir, "input", "steps.md")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_initialization_from_strings(self):
        steps = [
            "CONN-0126 Connect with Sarah Jenkins",
            "CONN-0127 Connect with Michael Chang",
            "CONN-0128 Connect with Elena Rostova"
        ]
        tracker = StepTracker(
            session_title="LinkedIn Outbound Session",
            steps=steps,
            steps_file_path=self.steps_path,
            auto_dispatch=False
        )

        self.assertEqual(tracker.total_steps, 3)
        self.assertEqual(tracker.completed_count, 0)
        self.assertEqual(tracker.progress_percent, 0)
        self.assertEqual(tracker.atomic_steps[0].unit_id, "CONN-0126")

        # Verify steps.md created
        self.assertTrue(os.path.exists(self.steps_path))
        with open(self.steps_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("# 🎯 Atomic Step Execution: LinkedIn Outbound Session", content)
        self.assertIn("0/3 Steps Completed (0%)", content)
        self.assertIn("- [ ] **Step 01:** `CONN-0126`", content)

    def test_step_lifecycle_transitions(self):
        steps = ["Step 1", "Step 2", "Step 3", "Step 4"]
        tracker = StepTracker(
            session_title="Lifecycle Test",
            steps=steps,
            steps_file_path=self.steps_path,
            auto_dispatch=False
        )

        # 1. Start Step 1
        tracker.start_step(1, "Navigating to profile")
        self.assertEqual(tracker.atomic_steps[0].status, "in_progress")
        self.assertEqual(tracker.atomic_steps[0].details, "Navigating to profile")
        self.assertEqual(tracker.active_step_index, 1)

        with open(self.steps_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("- [/] **Step 01:** Step 1 — IN PROGRESS (Navigating to profile)", content)

        # 2. Complete Step 1
        tracker.complete_step(1, "Invite sent successfully")
        self.assertEqual(tracker.atomic_steps[0].status, "completed")
        self.assertEqual(tracker.completed_count, 1)
        self.assertEqual(tracker.progress_percent, 25)

        with open(self.steps_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("1/4 Steps Completed (25%)", content)
        self.assertIn("- [x] **Step 01:** Step 1 — COMPLETED (Invite sent successfully)", content)

        # 3. Fail Step 2
        tracker.fail_step(2, "Button not found")
        self.assertEqual(tracker.atomic_steps[1].status, "failed")
        self.assertEqual(tracker.completed_count, 1)

        with open(self.steps_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("- [x] **Step 02:** Step 2 — FAILED (ERROR: Button not found)", content)

    def test_finish_all(self):
        steps = ["Step 1", "Step 2", "Step 3"]
        tracker = StepTracker(
            session_title="Finish All Test",
            steps=steps,
            steps_file_path=self.steps_path,
            auto_dispatch=False
        )

        tracker.finish_all(execute_task_complete=False)
        self.assertEqual(tracker.completed_count, 3)
        self.assertEqual(tracker.progress_percent, 100)

        with open(self.steps_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("3/3 Steps Completed (100%)", content)
        self.assertIn("✅ All Steps Completed (100%)", content)
        self.assertIn("██████████", content)  # Full ASCII progress bar

    def test_json_serialization_and_dual_sync(self):
        steps = [
            {"id": "SCRAPE-1", "title": "Scrape notifications"},
            {"id": "SCRAPE-2", "title": "Scrape feed posts"}
        ]
        json_path = os.path.join(self.test_dir, "input", "plan.json")
        tracker = StepTracker(
            session_title="Dual Sync Test",
            steps=steps,
            plan_json_path=json_path,
            auto_dispatch=False
        )

        self.assertTrue(os.path.exists(json_path))
        self.assertTrue(os.path.exists(tracker.steps_file_path))

        # Check JSON structure
        tracker.start_step(1, "Parsing DOM")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["session_title"], "Dual Sync Test")
        self.assertEqual(data["total_steps"], 2)
        self.assertEqual(data["active_step_index"], 1)
        self.assertEqual(data["steps"][0]["status"], "in_progress")
        self.assertEqual(data["steps"][0]["details"], "Parsing DOM")

        tracker.complete_step(1, "5 items extracted")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["completed_count"], 1)
        self.assertEqual(data["progress_percent"], 50)
        self.assertEqual(data["steps"][0]["status"], "completed")

        # Markdown should also be in sync
        with open(tracker.steps_file_path, "r", encoding="utf-8") as mf:
            md_content = mf.read()
        self.assertIn("1/2 Steps Completed (50%)", md_content)
        self.assertIn("- [x] **Step 01:** `SCRAPE-1` Scrape notifications — COMPLETED (5 items extracted)", md_content)

    def test_from_json_and_from_plan(self):
        json_path = os.path.join(self.test_dir, "input", "plan.json")
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        sample_data = {
            "session_title": "Loaded Plan Test",
            "steps": [
                {"index": 1, "title": "Step One", "status": "completed"},
                {"index": 2, "title": "Step Two", "status": "pending"}
            ]
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        # Test from_json
        tracker = StepTracker.from_json(json_path, auto_dispatch=False)
        self.assertEqual(tracker.session_title, "Loaded Plan Test")
        self.assertEqual(tracker.total_steps, 2)
        self.assertEqual(tracker.completed_count, 1)

        # Test from_plan
        tracker_plan = StepTracker.from_plan(self.test_dir, auto_dispatch=False)
        self.assertIsNotNone(tracker_plan)
        self.assertEqual(tracker_plan.session_title, "Loaded Plan Test")
        self.assertEqual(tracker_plan.total_steps, 2)


if __name__ == "__main__":
    unittest.main()
