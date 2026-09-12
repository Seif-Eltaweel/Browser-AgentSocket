"""
Unit tests for server models and protocol schemas.
"""

import unittest
from pydantic import ValidationError

from server.models import (
    ActionType,
    WSMessageType,
    ControlMode,
    ResponseStatus,
    ErrorCode,
    AgentActionPayload,
    ProgressPayload,
    ReleasePayload,
    StandardResponse,
    ServerStatusResponse,
    SessionStatus,
    SessionEventType,
    SessionEventModel,
    SessionSummaryModel,
    MonthlyIndexModel,
    BorrowSubskillPayload,
)


class TestModels(unittest.TestCase):

    def test_enums_values(self):
        self.assertEqual(ActionType.NAVIGATE.value, "navigate")
        self.assertEqual(ActionType.EXECUTE_JS.value, "execute_js")
        self.assertEqual(ActionType.TASK_COMPLETE.value, "task_complete")

        self.assertEqual(WSMessageType.EXECUTE_ACTION.value, "execute_action")
        self.assertEqual(WSMessageType.COMMAND_RESPONSE.value, "command_response")
        self.assertEqual(WSMessageType.STATE_CHANGE.value, "state_change")
        self.assertEqual(WSMessageType.STATE_SYNC.value, "state_sync")
        self.assertEqual(WSMessageType.PING.value, "ping")

        self.assertEqual(ControlMode.AGENT.value, "agent")
        self.assertEqual(ControlMode.HUMAN.value, "human")

        self.assertEqual(ResponseStatus.SUCCESS.value, "success")
        self.assertEqual(ResponseStatus.HUMAN_LOCKED.value, "human_locked")
        self.assertEqual(ResponseStatus.SECURITY_ABORT.value, "security_abort")

    def test_agent_action_payload_valid(self):
        payload = AgentActionPayload(
            id="cmd-123",
            action_type=ActionType.NAVIGATE,
            target_data="https://example.com",
            requires_privacy_check=False,
            session_title="Test Session",
        )
        self.assertEqual(payload.id, "cmd-123")
        self.assertEqual(payload.action_type, ActionType.NAVIGATE)
        self.assertEqual(payload.target_data, "https://example.com")
        self.assertEqual(payload.session_title, "Test Session")

    def test_agent_action_payload_from_str(self):
        payload = AgentActionPayload(
            id="cmd-456",
            action_type="execute_js",
            target_data="document.title",
            session_title="Execute Title Test"
        )
        self.assertEqual(payload.action_type, ActionType.EXECUTE_JS)
        self.assertFalse(payload.requires_privacy_check)
        self.assertEqual(payload.session_title, "Execute Title Test")

    def test_agent_action_payload_missing_session_title(self):
        with self.assertRaises(ValidationError):
            AgentActionPayload(
                id="cmd-no-title",
                action_type="execute_js",
                target_data="document.title"
            )

    def test_agent_action_payload_invalid_action(self):
        with self.assertRaises(ValidationError):
            AgentActionPayload(
                id="cmd-789",
                action_type="invalid_action_type",
                target_data="bad",
                session_title="Invalid Test"
            )

    def test_progress_payload_requires_step_title(self):
        with self.assertRaises(ValidationError):
            ProgressPayload(
                session_title="Test Task",
                step_current=1,
                step_total=5
            )
        valid = ProgressPayload(
            session_title="Test Task",
            step_current=1,
            step_total=5,
            step_title="Step 01: Initializing"
        )
        self.assertEqual(valid.step_title, "Step 01: Initializing")

    def test_borrow_subskill_payload_requires_session_title(self):
        with self.assertRaises(ValidationError):
            BorrowSubskillPayload(name="linkedin-crm-enricher")
        with self.assertRaises(ValidationError):
            BorrowSubskillPayload(name="linkedin-crm-enricher", session_title="")
        valid = BorrowSubskillPayload(
            name="linkedin-crm-enricher",
            session_title="Q3 Outreach Campaign"
        )
        self.assertEqual(valid.name, "linkedin-crm-enricher")
        self.assertEqual(valid.session_title, "Q3 Outreach Campaign")
        self.assertIsNone(valid.tab_group_id)

    def test_release_payload(self):
        payload = ReleasePayload(notes="CAPTCHA resolved by human.")
        self.assertEqual(payload.notes, "CAPTCHA resolved by human.")

        empty_payload = ReleasePayload()
        self.assertIsNone(empty_payload.notes)

    def test_standard_response(self):
        resp = StandardResponse(
            status=ResponseStatus.SUCCESS,
            data={"result": "OK"}
        )
        self.assertEqual(resp.status, ResponseStatus.SUCCESS)
        self.assertIsNotNone(resp.timestamp)
        self.assertEqual(resp.data, {"result": "OK"})

    def test_session_enums(self):
        self.assertEqual(SessionStatus.ACTIVE.value, "active")
        self.assertEqual(SessionStatus.COMPLETED.value, "completed")
        self.assertEqual(SessionStatus.STOPPED.value, "stopped")
        self.assertEqual(SessionStatus.ABORTED.value, "aborted")
        self.assertEqual(SessionStatus.ERROR.value, "error")

        self.assertEqual(SessionEventType.SESSION_START.value, "session_start")
        self.assertEqual(SessionEventType.NAVIGATE.value, "navigate")
        self.assertEqual(SessionEventType.EXECUTE_JS.value, "execute_js")
        self.assertEqual(SessionEventType.CDP_EVAL_RESULT.value, "cdp_eval_result")
        self.assertEqual(SessionEventType.SECURITY_ABORT.value, "security_abort")
        self.assertEqual(SessionEventType.HUMAN_TAKEOVER.value, "human_takeover")
        self.assertEqual(SessionEventType.HUMAN_RELEASE.value, "human_release")
        self.assertEqual(SessionEventType.TASK_COMPLETE.value, "task_complete")
        self.assertEqual(SessionEventType.ERROR.value, "error")
        self.assertEqual(SessionEventType.SESSION_END.value, "session_end")

    def test_session_event_model(self):
        event = SessionEventModel(
            session_id="sess_20260821_084510_9821",
            type=SessionEventType.NAVIGATE,
            title="Navigate to Feed",
            tab_id=101,
            tab_group_id=9821,
            url="https://example.com",
            duration_ms=250.5,
            payload={"reused": True}
        )
        self.assertTrue(event.event_id.startswith("evt_"))
        self.assertEqual(event.session_id, "sess_20260821_084510_9821")
        self.assertEqual(event.type, SessionEventType.NAVIGATE)
        self.assertEqual(event.duration_ms, 250.5)
        self.assertIsNone(event.artifact_link)

    def test_session_summary_model(self):
        summary = SessionSummaryModel(
            session_id="sess_20260821_084510_9821",
            session_title="LinkedIn Lead Gen | 2026-08-21_08:45:10",
            tab_group_id=9821,
            tab_group_name="LinkedIn Lead Gen",
            agent_name="Hermes Agent",
            group_color="green",
            status=SessionStatus.COMPLETED,
            session_path="server/logs/2026-08-21/LinkedIn_Lead_Gen_08-45-10_gid9821",
            event_count=10,
            action_count=8,
            takeover_count=1,
            artifacts_count=2,
            duration_ms=45000.0
        )
        self.assertEqual(summary.status, SessionStatus.COMPLETED)
        self.assertEqual(summary.event_count, 10)
        self.assertEqual(summary.takeover_count, 1)

    def test_monthly_index_model(self):
        summary = SessionSummaryModel(
            session_id="sess_20260821_084510_9821",
            session_title="Test Session",
            tab_group_id=1,
            tab_group_name="Test",
            agent_name="AgentSocket Local",
            group_color="purple",
            session_path="server/logs/2026-08-21/Test_08-45-10_gid1"
        )
        index = MonthlyIndexModel(months={"2026-08": [summary]})
        self.assertIn("2026-08", index.months)
        self.assertEqual(len(index.months["2026-08"]), 1)
        self.assertEqual(index.months["2026-08"][0].session_id, "sess_20260821_084510_9821")


if __name__ == "__main__":
    unittest.main()

