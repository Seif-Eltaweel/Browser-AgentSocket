"""
Agent Bro Hands - Server Models and Protocol Schemas
Typed Pydantic models and Enums for Python FastAPI gateway, MCP server, and launcher.
"""

from enum import Enum
from typing import Any, Optional
import time
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    EXECUTE_JS = "execute_js"
    TASK_COMPLETE = "task_complete"


class WSMessageType(str, Enum):
    EXECUTE_ACTION = "execute_action"
    COMMAND_RESPONSE = "command_response"
    STATE_CHANGE = "state_change"
    STATE_SYNC = "state_sync"
    PING = "ping"


class ControlMode(str, Enum):
    AGENT = "agent"
    HUMAN = "human"


class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    HUMAN_LOCKED = "human_locked"
    SECURITY_ABORT = "security_abort"
    RESUMED_CONTEXT = "resumed_context"


class ErrorCode(str, Enum):
    TAB_CLOSED = "TAB_CLOSED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    EXTENSION_OFFLINE = "EXTENSION_OFFLINE"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    CDP_ERROR = "CDP_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    TASK_ABORTED = "TASK_ABORTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AgentActionPayload(BaseModel):
    id: str = Field(..., description="Unique correlation identifier for the command")
    action_type: ActionType = Field(..., description="Target browser action to execute")
    target_data: str = Field(..., description="Target URL, JavaScript code string, or data")
    requires_privacy_check: bool = Field(default=False, description="Flag indicating sensitive scope check")
    session_title: Optional[str] = Field(default=None, description="Tab group session title")
    group_color: Optional[str] = Field(default=None, description="Tab group accent color")


class ReleasePayload(BaseModel):
    notes: Optional[str] = Field(default=None, description="Handoff notes from the human operator")


class ErrorDetail(BaseModel):
    code: str
    message: str


class StandardResponse(BaseModel):
    status: ResponseStatus
    data: Optional[Any] = None
    error: Optional[ErrorDetail] = None
    message: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: time.time())


class ServerStatusResponse(BaseModel):
    status: str
    extension_connected: bool
    human_in_control: bool
    last_intervention_notes: Optional[str] = None
    idle_seconds_remaining: float = 0.0
