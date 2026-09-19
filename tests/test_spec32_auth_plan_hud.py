"""
Unit and Integration Tests for Feature Spec 32:
Milestone-Driven Auth Plan Presentation & HUD Action Ticker 🎯🛡️
"""

import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from server.models import (
    MilestoneStatus,
    PlanMilestone,
    PlanPayload,
    UpdateMilestonePayload,
    ObserveRequest,
    ActRequest,
    SessionEventType,
    WSMessageType
)
from server.session.manager import SessionManager, render_milestones_markdown
from server.session import session_manager
from server.db import init_db
from server.socket_server import app, state


class TestSpec32Models(unittest.TestCase):
    def test_plan_milestone_defaults(self):
        """PlanMilestone defaults to PENDING status and requires index & title."""
        m = PlanMilestone(index=1, title="Open Target Account")
        self.assertEqual(m.index, 1)
        self.assertEqual(m.title, "Open Target Account")
        self.assertEqual(m.status, MilestoneStatus.PENDING)
        self.assertIsNone(m.description)

    def test_plan_payload_string_normalization(self):
        """PlanPayload normalizes list of plain strings into PlanMilestone instances (1-indexed)."""
        raw = {
            "session_title": "Batch 10 CRM Enrichment",
            "milestones": [
                "Open target account",
                "Access chat history with Omar",
                "Extract last message and verify"
            ]
        }
        payload = PlanPayload(**raw)
        self.assertEqual(len(payload.milestones), 3)
        self.assertEqual(payload.milestones[0].index, 1)
        self.assertEqual(payload.milestones[0].title, "Open target account")
        self.assertEqual(payload.milestones[0].status, MilestoneStatus.PENDING)
        self.assertEqual(payload.milestones[1].index, 2)
        self.assertEqual(payload.milestones[2].index, 3)

    def test_plan_payload_dict_normalization(self):
        """PlanPayload handles mixed lists of dicts and PlanMilestone objects."""
        raw = {
            "session_title": "Batch 10 CRM Enrichment",
            "milestones": [
                {"index": 1, "title": "Navigate to LinkedIn", "status": "completed"},
                {"index": 2, "title": "Locate candidate profile", "status": "in_progress"},
                PlanMilestone(index=3, title="Export 19 fields", status=MilestoneStatus.PENDING)
            ],
            "active_milestone_index": 2
        }
        payload = PlanPayload(**raw)
        self.assertEqual(len(payload.milestones), 3)
        self.assertEqual(payload.milestones[0].status, MilestoneStatus.COMPLETED)
        self.assertEqual(payload.milestones[1].status, MilestoneStatus.IN_PROGRESS)
        self.assertEqual(payload.milestones[2].status, MilestoneStatus.PENDING)
        self.assertEqual(payload.active_milestone_index, 2)

    def test_observe_act_request_action_detail(self):
        """ObserveRequest and ActRequest accept optional action_detail parameter."""
        obs = ObserveRequest(action_detail="Scanning DOM for target Omar...")
        self.assertEqual(obs.action_detail, "Scanning DOM for target Omar...")

        act = ActRequest(action="click", element_id=42, action_detail="(Open account no1)")
        self.assertEqual(act.action_detail, "(Open account no1)")

    def test_event_and_ws_types(self):
        """Verify Spec 32 event types and WebSocket message types exist."""
        self.assertEqual(SessionEventType.PLAN_REGISTERED.value, "plan_registered")
        self.assertEqual(SessionEventType.MILESTONE_STARTED.value, "milestone_started")
        self.assertEqual(SessionEventType.MILESTONE_COMPLETED.value, "milestone_completed")
        self.assertEqual(WSMessageType.SET_PLAN.value, "set_plan")
        self.assertEqual(WSMessageType.SET_MILESTONE.value, "set_milestone")


class TestSpec32SessionManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_spec32.db")
        init_db(self.db_path)
        self.session_manager = SessionManager(base_log_dir=self.temp_dir, db_path=self.db_path)
        self.session = self.session_manager.get_or_create_session(
            tab_group_id=101,
            tab_group_name="Batch 10 CRM Enrichment"
        )

    def test_render_milestones_markdown(self):
        """Milestones render as clean strategic markdown without micro-step badge clutter."""
        milestones = [
            PlanMilestone(index=1, title="Open target account", status=MilestoneStatus.COMPLETED),
            PlanMilestone(index=2, title="Access chat history with Omar", status=MilestoneStatus.IN_PROGRESS),
            PlanMilestone(index=3, title="Extract and verify CRM fields", status=MilestoneStatus.PENDING)
        ]
        md = render_milestones_markdown("Batch 10 CRM Enrichment", milestones, active_index=2)
        self.assertIn("Strategic Plan: Batch 10 CRM Enrichment", md)
        self.assertIn("Milestone 1:** Open target account", md)
        self.assertIn("Milestone 2:** Access chat history with Omar", md)
        self.assertIn("Milestone 3:** Extract and verify CRM fields", md)
        self.assertNotIn("Step 01: Click", md)

    def test_set_session_plan_and_artifacts(self):
        """Setting a plan persists input/plan.json and input/implementation_plan.md."""
        milestones = [
            PlanMilestone(index=1, title="Open Target Account"),
            PlanMilestone(index=2, title="Locate Omar Chat"),
            PlanMilestone(index=3, title="Extract Message")
        ]
        res = self.session_manager.set_session_plan(
            session_title="Batch 10 CRM Enrichment",
            milestones=milestones,
            active_index=1
        )
        self.assertEqual(res["total_milestones"], 3)
        self.assertEqual(res["active_index"], 1)

        # Verify artifacts
        plan_json_path = os.path.join(self.session.input_dir, "plan.json")
        impl_plan_md_path = os.path.join(self.session.input_dir, "implementation_plan.md")

        self.assertTrue(os.path.exists(plan_json_path))
        self.assertTrue(os.path.exists(impl_plan_md_path))

        with open(plan_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(len(data["milestones"]), 3)
            self.assertEqual(data["active_milestone_index"], 1)

        with open(impl_plan_md_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Strategic Plan: Batch 10 CRM Enrichment", content)
            self.assertIn("Milestone 1", content)

    def test_update_session_milestone_progress(self):
        """Updating milestone updates lifecycle state and computes accurate milestone completion percent."""
        milestones = [
            PlanMilestone(index=1, title="Open Target Account"),
            PlanMilestone(index=2, title="Locate Omar Chat"),
            PlanMilestone(index=3, title="Extract Message")
        ]
        self.session_manager.set_session_plan(
            session_title="Batch 10 CRM Enrichment",
            milestones=milestones,
            active_index=1
        )

        # Complete Milestone 1
        self.session_manager.update_session_milestone(
            session_title="Batch 10 CRM Enrichment",
            milestone_index=1,
            status=MilestoneStatus.COMPLETED
        )

        # Start Milestone 2 with live action detail
        update_res = self.session_manager.update_session_milestone(
            session_title="Batch 10 CRM Enrichment",
            milestone_index=2,
            action_detail="(Open account no1)",
            status=MilestoneStatus.IN_PROGRESS
        )
        self.assertEqual(update_res["milestone_index"], 2)
        self.assertEqual(update_res["current_action"], "(Open account no1)")
        # 1 completed out of 3 = 33%
        self.assertEqual(update_res["progress_percent"], 33)

        # Complete Milestone 2
        update_res2 = self.session_manager.update_session_milestone(
            session_title="Batch 10 CRM Enrichment",
            milestone_index=2,
            status=MilestoneStatus.COMPLETED
        )
        # 2 completed out of 3 = 66%
        self.assertEqual(update_res2["progress_percent"], 66)


class TestSpec32Endpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.headers.update({"X-AgentSocket-Token": state.server_token})
        self.session = session_manager.get_or_create_session(
            tab_group_id=303,
            tab_group_name="Batch 10 CRM Enrichment"
        )
        # Setup mock extension websocket
        self.mock_ws = MagicMock()
        self.mock_ws.send_text = AsyncMock()
        state.extension_ws = self.mock_ws

    def tearDown(self):
        state.extension_ws = None

    def test_post_plan_endpoint(self):
        """POST /plan sets plan and dispatches set_plan WS frame."""
        resp = self.client.post("/plan", json={
            "session_title": "Batch 10 CRM Enrichment",
            "milestones": [
                "Open target account",
                "Access chat history with Omar",
                "Extract and verify CRM fields"
            ],
            "active_milestone_index": 1
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_milestones"], 3)
        self.assertEqual(data["active_index"], 1)

        # Check broadcast
        self.assertTrue(self.mock_ws.send_text.called)
        sent_frame = json.loads(self.mock_ws.send_text.call_args[0][0])
        self.assertEqual(sent_frame["type"], "set_plan")
        self.assertEqual(len(sent_frame["milestones"]), 3)
        self.assertEqual(sent_frame["active_index"], 1)

    def test_post_plan_milestone_endpoint(self):
        """POST /plan/milestone updates active milestone and action detail."""
        # First register plan
        self.client.post("/plan", json={
            "session_title": "Batch 10 CRM Enrichment",
            "milestones": ["Task A", "Task B"],
            "active_milestone_index": 1
        })

        resp = self.client.post("/plan/milestone", json={
            "session_title": "Batch 10 CRM Enrichment",
            "milestone_index": 2,
            "action_detail": "(Open account no1)",
            "status": "in_progress"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["milestone_index"], 2)
        self.assertEqual(data["current_action"], "(Open account no1)")

        self.assertTrue(self.mock_ws.send_text.called)
        sent_frame = json.loads(self.mock_ws.send_text.call_args[0][0])
        self.assertEqual(sent_frame["type"], "set_milestone")
        self.assertEqual(sent_frame["milestone_index"], 2)
        self.assertEqual(sent_frame["current_action"], "(Open account no1)")


if __name__ == "__main__":
    unittest.main()
