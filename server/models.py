"""
AgentSocket - Server Models and Protocol Schemas
Typed Pydantic models and Enums for Python FastAPI gateway, MCP server, and launcher.
"""

from enum import Enum
from typing import Any, Optional
import time
import uuid
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


# ============================================================================
# Session Logging & History Models (Spec 11)
# ============================================================================

class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ABORTED = "aborted"
    ERROR = "error"


class SessionEventType(str, Enum):
    SESSION_START = "session_start"
    NAVIGATE = "navigate"
    EXECUTE_JS = "execute_js"
    CDP_EVAL_RESULT = "cdp_eval_result"
    SECURITY_ABORT = "security_abort"
    HUMAN_TAKEOVER = "human_takeover"
    HUMAN_RELEASE = "human_release"
    TASK_COMPLETE = "task_complete"
    SUBSKILL_BORROWED = "subskill_borrowed"
    SUBSKILL_REGISTERED = "subskill_registered"
    ERROR = "error"
    SESSION_END = "session_end"


class SessionEventModel(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    session_id: str
    start_time: float = Field(default_factory=lambda: time.time())
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    type: SessionEventType
    title: str
    tab_id: Optional[int] = None
    tab_group_id: Optional[int] = None
    url: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    artifact_link: Optional[str] = None


class SessionSummaryModel(BaseModel):
    session_id: str
    session_title: str
    tab_group_id: int
    tab_group_name: str
    agent_name: str = "AgentSocket Local"
    group_color: str = "purple"
    status: SessionStatus = SessionStatus.ACTIVE
    start_time: float = Field(default_factory=lambda: time.time())
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    event_count: int = 0
    action_count: int = 0
    takeover_count: int = 0
    session_path: str
    artifacts_count: int = 0
    end_reason: Optional[str] = None


class MonthlyIndexModel(BaseModel):
    updated_at: float = Field(default_factory=lambda: time.time())
    months: dict[str, list[SessionSummaryModel]] = {}


# ============================================================================
# Subskills & Borrowing Engine Models (Spec 13)
# ============================================================================

class SubskillModel(BaseModel):
    name: str = Field(..., description="Unique slug identifier (e.g. linkedin-crm-enricher)")
    display_title: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of what this subskill automates")
    tags: list[str] = Field(default_factory=list, description="Searchable semantic tags")
    latest_session_id: str = Field(..., description="Session ID of the source or latest updated session")
    latest_session_path: str = Field(..., description="Relative path to the latest session directory")
    subskill_file: str = Field(default="sub_skill.md", description="Relative filename of the playbook")
    adhoc_tools: list[str] = Field(default_factory=list, description="List of filenames inside adhocs/ folder")
    times_borrowed: int = Field(default=0, description="Counter of times this subskill has been borrowed")
    success_rate: float = Field(default=1.0, description="Reported task success rate (0.0 to 1.0)")
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


class SubskillsIndexModel(BaseModel):
    version: str = "1.0"
    updated_at: float = Field(default_factory=lambda: time.time())
    subskills: dict[str, SubskillModel] = {}


class BorrowSubskillPayload(BaseModel):
    name: str = Field(..., description="Slug name of the subskill to borrow")
    session_title: Optional[str] = Field(default="AgentSocket Task", description="Title for target session")
    tab_group_id: Optional[int] = Field(default=None, description="Optional target tab group ID")
    input_file_path: Optional[str] = Field(default=None, description="Optional path of input data file to copy into input/")


class RegisterSubskillPayload(BaseModel):
    session_path: str = Field(..., description="Relative or absolute path to session folder")
    name: str = Field(..., description="Unique slug identifier for the subskill")
    display_title: Optional[str] = Field(default=None, description="Human-readable display title")
    description: Optional[str] = Field(default=None, description="Detailed subskill description")
    tags: Optional[list[str]] = Field(default=None, description="List of keyword tags")
    adhoc_tools: Optional[list[str]] = Field(default=None, description="Specific adhoc script filenames")
    subskill_markdown: Optional[str] = Field(default=None, description="Optional raw markdown for sub_skill.md")


