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
    ReleasePayload,
    StandardResponse,
    ServerStatusResponse
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
            group_color="blue"
        )
        self.assertEqual(payload.id, "cmd-123")
        self.assertEqual(payload.action_type, ActionType.NAVIGATE)
        self.assertEqual(payload.target_data, "https://example.com")
        self.assertEqual(payload.session_title, "Test Session")
        self.assertEqual(payload.group_color, "blue")

    def test_agent_action_payload_from_str(self):
        payload = AgentActionPayload(
            id="cmd-456",
            action_type="execute_js",
            target_data="document.title"
        )
        self.assertEqual(payload.action_type, ActionType.EXECUTE_JS)
        self.assertFalse(payload.requires_privacy_check)
        self.assertIsNone(payload.session_title)

    def test_agent_action_payload_invalid_action(self):
        with self.assertRaises(ValidationError):
            AgentActionPayload(
                id="cmd-789",
                action_type="invalid_action_type",
                target_data="bad"
            )

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


if __name__ == "__main__":
    unittest.main()
