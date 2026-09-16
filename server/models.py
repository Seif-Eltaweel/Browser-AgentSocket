"""
AgentSocket - Server Models and Protocol Schemas
aka functioning as both models persistence entities  and API schema for DTOs
Typed Pydantic models and Enums for Python FastAPI gateway, MCP server, and launcher.
"""

from __future__ import annotations # For using types inside the class itself
from enum import Enum 
import os
import time
from typing import Any
import uuid
from pydantic import BaseModel, Field, ConfigDict, model_validator

# for actions 
class ActionType(str, Enum):
    NAVIGATE = "navigate"
    EXECUTE_JS = "execute_js"
    TASK_COMPLETE = "task_complete"
    OBSERVE_PAGE = "observe_page"
    ACT_ELEMENT = "act_element"
    BROWSER_SCREENSHOT = "browser_screenshot"

#websocket messages
class WSMessageType(str, Enum):
    EXECUTE_ACTION = "execute_action"
    COMMAND_RESPONSE = "command_response"
    STATE_CHANGE = "state_change"
    STATE_SYNC = "state_sync"
    UPDATE_PROGRESS = "update_progress"
    PING = "ping"
    OBSERVE_PAGE = "observe_page"
    OBSERVE_RESPONSE = "observe_response"
    ACT_ELEMENT = "act_element"
    ACT_RESPONSE = "act_response"
    AUTH_REQUEST = "auth_request"
    AUTH_RESPONSE = "auth_response"

# who is in control 
class ControlMode(str, Enum):
    AGENT = "agent"
    HUMAN = "human"

# standard values for status in server responces 
class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    HUMAN_LOCKED = "human_locked"
    SECURITY_ABORT = "security_abort"
    RESUMED_CONTEXT = "resumed_context"

# in this class i standardize the error from the server
class ErrorCode(str, Enum):
    TAB_CLOSED = "TAB_CLOSED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    EXTENSION_OFFLINE = "EXTENSION_OFFLINE"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    CDP_ERROR = "CDP_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNAUTHORIZED = "UNAUTHORIZED"
    TASK_ABORTED = "TASK_ABORTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ConsentPermissions(BaseModel):
    enable_subskills: bool = Field(default=True, description="Enable reference and creation of subskills SOPs")
    enable_vision: bool = Field(default=False, description="Enable viewport screenshot captures")


class AuthResponsePayload(BaseModel):
    type: str = Field(default="auth_response", description="Message type")
    status: str = Field(..., description="Approval status: 'approved' or 'denied'")
    token: str = Field(..., description="Verified gateway token")
    tab_group_id: int | None = Field(default=None, description="Active tab group ID")
    tab_group_name: str | None = Field(default=None, description="Active tab group title")
    permissions: ConsentPermissions = Field(default_factory=ConsentPermissions, description="Privacy and capability toggles")


class AgentActionPayload(BaseModel):
    # unique id for each commaned from the AI agent to be excuted 
    id: str = Field(default_factory=lambda: f"cmd_{uuid.uuid4().hex[:8]}", description="Unique correlation identifier for the command")
    # uses the actions from the class "actiontype enum" 
    action_type: ActionType = Field(..., description="Target browser action to execute")
    # to point the target which could be url or data or a code 
    target_data: str = Field(..., description="Target URL, JavaScript code string, or data")
    # to force human to give auth and turn it to true
    requires_privacy_check: bool = Field(default=False, description="Flag indicating sensitive scope check")
    # to get a title for each grouped session 
    session_title: str = Field(..., description="Tab group session title provided by the agent")
    tab_group_id: int | None = Field(default=None, description="Optional target tab group ID")


class ProgressPayload(BaseModel):
    # Identifies which tab group / active session this progress update applies to
    session_title: str = Field(..., description="Tab group session title")
    # The 1-indexed number of the step currently being executed
    step_current: int = Field(..., description="1-indexed current step number")
    # The total planned number of steps planned by the agent to complete the session goal
    step_total: int = Field(..., description="Total number of steps in task")
    step_title: str = Field(..., min_length=1, description="Detailed human-readable step description provided by the agent")


class ReleasePayload(BaseModel):
    notes: str | None = Field(default=None, description="Handoff notes from the human operator")
    tab_group_id: int | None = Field(default=None, description="Optional target tab group ID to release")


# ============================================================================
# Atomic OODA Schemas (Spec 23)
# ============================================================================

class ObserveRequest(BaseModel):
    tab_group_id: int | None = None
    take_screenshot: bool = False


class ObserveResponse(BaseModel):
    status: str
    url: str = ""
    title: str = ""
    viewport: dict[str, Any] = Field(default_factory=dict)
    tree_text: str = ""
    elements: list[dict[str, Any]] = Field(default_factory=list)
    screenshot_path: str | None = None


class ActRequest(BaseModel):
    tab_group_id: int | None = None
    action: str  # "click", "type", "scroll", "key_press"
    element_id: int | None = None
    text: str | None = None
    clear_first: bool = False
    press_enter: bool = False
    direction: str | None = None
    amount: int | None = None
    key: str | None = None
    wait_settle: bool = True


class ActResponse(BaseModel):
    status: str
    action: str
    element_id: int | None = None
    duration_ms: float = 0.0
    mutations_observed: int = 0
    settle_reason: str = "quiescence"
    intervention_notes: str | None = None  # Preserves human context without dropping command!


class SetIntentRequest(BaseModel):
    tab_group_id: int | None = None
    intent: str
    subtext: str = ""
    phase: str | None = None


class ScreenshotRequest(BaseModel):
    tab_group_id: int | None = None
    filename: str | None = None


class TaskCompleteRequest(BaseModel):
    tab_group_id: int | None = None
    result: str | None = None
    status: str = "completed"



class ErrorDetail(BaseModel):
    code: str
    message: str


class StandardResponse(BaseModel):
    status: ResponseStatus
    data: Any | None = None
    error: ErrorDetail | None = None
    message: str | None = None
    timestamp: float = Field(default_factory=lambda: time.time())


class ServerStatusResponse(BaseModel):
    status: str
    extension_connected: bool
    human_in_control: bool
    last_intervention_notes: str | None = None
    idle_seconds_remaining: float = 0.0


# ============================================================================
# Session Logging & History Models 
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
    OBSERVE = "observe"
    CLICK = "click"
    TYPE = "type"
    ACT_ELEMENT = "act_element"
    BROWSER_SCREENSHOT = "browser_screenshot"


class SessionEventModel(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    session_id: str
    start_time: float = Field(default_factory=lambda: time.time())
    end_time: float | None = None
    duration_ms: float | None = None
    type: SessionEventType
    title: str
    tab_id: int | None = None
    tab_group_id: int | None = None
    url: str | None = None
    payload: dict[str, Any] | None = None
    artifact_link: str | None = None


class SessionSummaryModel(BaseModel):
    session_id: str
    session_title: str
    tab_group_id: int
    tab_group_name: str
    agent_name: str = Field(..., description="Agent name dynamically supplied by extension port settings")
    group_color: str = Field(..., description="Tab group accent color dynamically supplied by extension port settings")
    status: SessionStatus = SessionStatus.ACTIVE
    start_time: float = Field(default_factory=lambda: time.time())
    end_time: float | None = None
    duration_ms: float | None = None
    event_count: int = 0
    action_count: int = 0
    takeover_count: int = 0
    session_path: str
    artifacts_count: int = 0
    end_reason: str | None = None


class MonthlyIndexModel(BaseModel):
    updated_at: float = Field(default_factory=lambda: time.time())
    months: dict[str, list[SessionSummaryModel]] = Field(default_factory=dict)


# ============================================================================
# Subskills & Borrowing Engine Models 
# ============================================================================
# Subskills & Central Vault Models (Spec 18)
# ============================================================================

class SubskillModel(BaseModel):
    name: str = Field(..., description="Unique slug identifier (e.g. linkedin-crm-enricher)")
    display_title: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of what this subskill automates")
    tags: list[str] = Field(default_factory=list, description="Searchable semantic tags")
    vault_path: str = Field(default="", description="Relative path to subskill in permanent central vault")
    subskill_file: str = Field(default="sub_skill.md", description="Relative filename of the playbook")
    playbook_path: str = Field(default="", description="Relative path to sub_skill.md playbook (Spec 26)")
    adhoc_tools: list[str] = Field(default_factory=list, description="List of filenames inside adhocs/ folder")
    times_borrowed: int = Field(default=0, description="Counter of times this subskill has been borrowed")
    times_referenced: int = Field(default=0, description="Counter of times this subskill has been referenced/borrowed (Spec 26)")
    success_rate: float = Field(default=1.0, description="Reported task success rate (0.0 to 1.0)")
    origin_session_id: str | None = Field(default=None, description="Session ID of the source or latest updated session")
    latest_session_id: str | None = Field(default=None, description="Legacy session ID of source session")
    latest_session_path: str | None = Field(default=None, description="Legacy relative path to source session")
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @model_validator(mode="before")
    @classmethod
    def _sync_subskill_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "times_referenced" in data and "times_borrowed" not in data:
                data["times_borrowed"] = data["times_referenced"]
            elif "times_borrowed" in data and "times_referenced" not in data:
                data["times_referenced"] = data["times_borrowed"]
            elif "times_referenced" in data and "times_borrowed" in data:
                max_ref = max(data.get("times_referenced") or 0, data.get("times_borrowed") or 0)
                data["times_referenced"] = max_ref
                data["times_borrowed"] = max_ref

            name = data.get("name") or data.get("slug", "")
            if not data.get("name") and name:
                data["name"] = name

            playbook_path = data.get("playbook_path", "")
            vault_path = data.get("vault_path", "")
            subskill_file = data.get("subskill_file", "sub_skill.md")

            if not playbook_path and vault_path:
                data["playbook_path"] = f"{vault_path}/{subskill_file}".replace("\\", "/")
            elif not vault_path and playbook_path:
                data["vault_path"] = os.path.dirname(playbook_path).replace("\\", "/")
            elif not playbook_path and not vault_path and name:
                data["vault_path"] = f"server/subskills/{name}"
                data["playbook_path"] = f"server/subskills/{name}/{subskill_file}"
        return data


class SubskillsIndexModel(BaseModel):
    version: str = "2.1.0"
    updated_at: Any = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    subskills: dict[str, SubskillModel] = Field(default_factory=dict)


class BorrowedSubskillReference(BaseModel):
    name: str = Field(..., description="Subskill name")
    borrowed_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    vault_path: str = Field(..., description="Relative path to subskill in central vault")
    referenced_adhocs: list[str] = Field(default_factory=list, description="Referenced adhoc tool filenames")


class SessionManifestModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str = Field(..., description="Unique session identifier")
    session_title: str = Field(..., description="Session title")
    tab_group_id: int | None = Field(default=None, description="Browser tab group ID")
    tab_group_name: str | None = Field(default=None, description="Tab group name")
    group_color: str | None = Field(default="purple", description="Tab group color")
    agent_name: str | None = Field(default="AgentSocket Local", description="Agent name")
    mode: str | None = Field(default="direct", description="Session execution mode")
    status: str | None = Field(default="active", description="Session status")
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    duration_ms: float | None = Field(default=0.0, description="Execution duration in milliseconds")
    permissions: dict[str, Any] | None = Field(default=None, description="Session permissions")
    metrics: dict[str, Any] | None = Field(default=None, description="Session metrics")
    deliverables: list[str] = Field(default_factory=list, description="Output deliverables list")
    borrowed_subskills: list[BorrowedSubskillReference] = Field(default_factory=list, description="Borrowed subskills references")
    universal_adhocs_referenced: list[str] = Field(default_factory=list, description="Universal adhocs used")
    local_overrides: list[str] = Field(default_factory=list, description="Local adhoc overrides in session/adhocs/")
    created_adhocs: list[str] = Field(default_factory=list, description="Newly created adhocs in session/adhocs/")


class BorrowSubskillPayload(BaseModel):
    name: str = Field(..., description="Slug name of the subskill to borrow")
    session_title: str = Field(..., min_length=1, description="Title for target session provided by the agent")
    tab_group_id: int | None = Field(default=None, description="Optional target tab group ID")
    input_file_path: str | None = Field(default=None, description="Optional path of input data file to copy into input/")


class RegisterSubskillPayload(BaseModel):
    session_path: str = Field(..., description="Relative or absolute path to session folder")
    name: str = Field(..., description="Unique slug identifier for the subskill")
    display_title: str | None = Field(default=None, description="Human-readable display title")
    description: str | None = Field(default=None, description="Detailed subskill description")
    tags: list[str] | None = Field(default=None, description="List of keyword tags")
    adhoc_tools: list[str] | None = Field(default=None, description="Specific adhoc script filenames")
    subskill_markdown: str | None = Field(default=None, description="Optional raw markdown for sub_skill.md")


class PromoteAdhocPayload(BaseModel):
    session_path: str = Field(..., description="Path to session folder containing the adhoc tool")
    tool_name: str = Field(..., description="Filename of adhoc tool to promote (e.g. verify_company_size.py)")
    target: str = Field(default="universal", description="Promotion target vault: 'universal' or 'subskill'")
    subskill_name: str | None = Field(default=None, description="Target subskill name if target is 'subskill'")


class RunAdhocPayload(BaseModel):
    tool_name: str = Field(..., description="Filename of the adhoc tool (e.g. probe_dom.py)")
    session_path: str | None = Field(default=None, description="Optional session path for resolving local overrides and subskill adhocs")
    args: list[str] = Field(default_factory=list, description="Command line arguments to pass to the script")

