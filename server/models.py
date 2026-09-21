"""Server Models and Protocol Schemas.

Provides Pydantic data validation, serialization entities, and DTO schemas
for the FastAPI gateway, FastMCP server, and smart launcher subsystems.
"""

from __future__ import annotations

from enum import Enum
import os
import time
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActionType(str, Enum):
    """Supported browser action types for agent command dispatch."""

    NAVIGATE = "navigate"
    EXECUTE_JS = "execute_js"
    TASK_COMPLETE = "task_complete"
    OBSERVE_PAGE = "observe_page"
    ACT_ELEMENT = "act_element"
    BROWSER_SCREENSHOT = "browser_screenshot"


class WSMessageType(str, Enum):
    """WebSocket frame event types exchanged between gateway and extension."""

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
    SET_PLAN = "set_plan"
    SET_MILESTONE = "set_milestone"


class ControlMode(str, Enum):
    """Defines whether the AI agent or the human operator has active execution control."""

    AGENT = "agent"
    HUMAN = "human"


class ResponseStatus(str, Enum):
    """Standardized response status classifications for gateway and MCP interactions."""

    SUCCESS = "success"
    ERROR = "error"
    HUMAN_LOCKED = "human_locked"
    SECURITY_ABORT = "security_abort"
    RESUMED_CONTEXT = "resumed_context"


class ErrorCode(str, Enum):
    """Standardized error classifications for client and extension exceptions."""

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
    """User privacy and capability consent settings established during initial handshake."""

    enable_subskills: bool = Field(default=True, description="Enable reference and creation of subskill SOPs")
    enable_vision: bool = Field(default=False, description="Enable viewport screenshot captures")


class AuthResponsePayload(BaseModel):
    """Response payload returned by the browser extension during connection authentication."""

    type: str = Field(default="auth_response", description="Message frame type identifier")
    status: str = Field(..., description="Approval status: 'approved' or 'denied'")
    token: str = Field(..., description="Verified gateway token")
    tab_group_id: int | None = Field(default=None, description="Active tab group ID")
    tab_group_name: str | None = Field(default=None, description="Active tab group title")
    permissions: ConsentPermissions = Field(
        default_factory=ConsentPermissions, description="Privacy and capability toggles"
    )


class AgentActionPayload(BaseModel):
    """Encapsulates an execution command dispatched from an agent to the browser gateway."""

    id: str = Field(
        default_factory=lambda: f"cmd_{uuid.uuid4().hex[:8]}",
        description="Unique correlation identifier for the command",
    )
    action_type: ActionType = Field(..., description="Target browser action to execute")
    target_data: str = Field(..., description="Target URL, JavaScript code string, or action parameter")
    requires_privacy_check: bool = Field(
        default=False, description="Flag indicating sensitive scope check requiring operator takeover"
    )
    session_title: str = Field(..., description="Tab group session title provided by the agent")
    tab_group_id: int | None = Field(default=None, description="Optional target tab group ID")


class ProgressPayload(BaseModel):
    """Progress update emitted during a multi-step task to update browser HUD indicators."""

    session_title: str = Field(..., description="Tab group session title")
    step_current: int = Field(..., description="1-indexed current step number")
    step_total: int = Field(..., description="Total number of steps planned in task")
    step_title: str = Field(
        ..., min_length=1, description="Detailed human-readable step description provided by the agent"
    )


# ============================================================================
# Strategic Milestones & Plan Presentation Schemas (Spec 32)
# ============================================================================


class MilestoneStatus(str, Enum):
    """Lifecycle state of an individual strategic execution milestone."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanMilestone(BaseModel):
    """Individual milestone entity within an agent's strategic execution plan."""

    index: int = Field(..., description="1-indexed milestone sequence number")
    title: str = Field(..., min_length=1, description="Strategic milestone title")
    description: str | None = Field(default=None, description="Optional milestone details or goal")
    status: MilestoneStatus = Field(default=MilestoneStatus.PENDING, description="Current milestone lifecycle state")


class PlanPayload(BaseModel):
    """Payload registering or synchronizing a strategic multi-milestone plan."""

    session_title: str = Field(..., min_length=1, description="Target session title")
    milestones: list[PlanMilestone | str] = Field(..., min_length=1, description="List of planned strategic milestones")
    active_milestone_index: int | None = Field(default=1, description="Currently active milestone index")

    @model_validator(mode="before")
    @classmethod
    def _normalize_milestones(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_milestones = data.get("milestones", [])
            normalized = []
            for idx, item in enumerate(raw_milestones, start=1):
                if isinstance(item, str):
                    normalized.append(PlanMilestone(index=idx, title=item, status=MilestoneStatus.PENDING))
                elif isinstance(item, dict):
                    m_idx = item.get("index", idx)
                    m_title = item.get("title", f"Milestone {m_idx}")
                    m_status = item.get("status", MilestoneStatus.PENDING)
                    m_desc = item.get("description")
                    normalized.append(PlanMilestone(index=m_idx, title=m_title, description=m_desc, status=m_status))
                elif isinstance(item, PlanMilestone):
                    normalized.append(item)
            data["milestones"] = normalized
        return data


class UpdateMilestonePayload(BaseModel):
    """Payload updating the status, title, or micro-action ticker of a milestone."""

    session_title: str = Field(..., min_length=1, description="Target session title")
    milestone_index: int | None = Field(default=None, description="Milestone sequence index")
    milestone_title: str | None = Field(default=None, description="Milestone title update")
    action_detail: str | None = Field(default=None, description="Live atomic action ticker subtext")
    status: MilestoneStatus | None = Field(default=None, description="Updated milestone lifecycle status")


class ReleasePayload(BaseModel):
    """Payload releasing human operator intervention lockout with handoff notes."""

    notes: str | None = Field(default=None, description="Handoff notes from the human operator")
    tab_group_id: int | None = Field(default=None, description="Optional target tab group ID to release")


# ============================================================================
# Atomic OODA Schemas (Spec 23)
# ============================================================================


class ObserveRequest(BaseModel):
    """Request schema for DOM observation and ARIA badge generation."""

    tab_group_id: int | None = Field(default=None, description="Target browser tab group ID")
    session_title: str | None = Field(default=None, description="Session title for correlation")
    take_screenshot: bool = Field(default=False, description="Whether to capture a viewport screenshot")
    action_detail: str | None = Field(default=None, description="Optional action ticker text for HUD display")


class ObserveResponse(BaseModel):
    """Response schema containing parsed accessibility tree and numbered badge elements."""

    status: str = Field(..., description="Observation result status: 'success' or 'error'")
    url: str = Field(default="", description="Current URL of observed tab")
    title: str = Field(default="", description="Current document title of observed tab")
    viewport: dict[str, Any] = Field(default_factory=dict, description="Viewport dimensions {width, height}")
    tree_text: str = Field(default="", description="Formatted ARIA accessibility tree with numbered badges")
    elements: list[dict[str, Any]] = Field(default_factory=list, description="Indexed element metadata list")
    screenshot_path: str | None = Field(default=None, description="Relative path to captured screenshot if enabled")


class ActRequest(BaseModel):
    """Request schema for executing an atomic browser action on a badged element or viewport."""

    tab_group_id: int | None = Field(default=None, description="Target browser tab group ID")
    session_title: str | None = Field(default=None, description="Session title for correlation")
    action: str = Field(..., description="Atomic action type: 'click', 'type', 'scroll', or 'key_press'")
    element_id: int | None = Field(default=None, description="Target element badge ID [1]..[N]")
    text: str | None = Field(default=None, description="Text string to type into input element")
    clear_first: bool = Field(default=False, description="Clear input value before typing")
    press_enter: bool = Field(default=False, description="Dispatch Enter key after typing")
    direction: str | None = Field(default=None, description="Scroll direction: 'down', 'up', 'top', 'bottom'")
    amount: int | None = Field(default=None, description="Scroll delta in pixels")
    key: str | None = Field(default=None, description="Key name to dispatch for key_press action")
    wait_settle: bool = Field(default=True, description="Wait for network quiescence and DOM settlement")
    action_detail: str | None = Field(default=None, description="Live micro-action ticker subtext for HUD")


class ActResponse(BaseModel):
    """Response schema following an atomic action and adaptive settlement check."""

    status: str = Field(..., description="Action outcome: 'success', 'error', or 'security_abort'")
    action: str = Field(..., description="Executed action name")
    element_id: int | None = Field(default=None, description="Target element badge ID")
    duration_ms: float = Field(default=0.0, description="Execution and settlement duration in milliseconds")
    mutations_observed: int = Field(default=0, description="Count of DOM mutations observed during settlement")
    settle_reason: str = Field(default="quiescence", description="Settlement termination reason")
    intervention_notes: str | None = Field(
        default=None, description="Preserved operator handoff notes if human intervened"
    )


class SetIntentRequest(BaseModel):
    """Request schema for updating HUD intent ticker and execution phase."""

    tab_group_id: int | None = Field(default=None, description="Target browser tab group ID")
    intent: str = Field(..., description="Current primary objective text")
    subtext: str = Field(default="", description="Detailed secondary status or URL subtext")
    phase: str | None = Field(default=None, description="Optional workflow phase name")


class ScreenshotRequest(BaseModel):
    """Request schema for standalone high-resolution viewport capture."""

    tab_group_id: int | None = Field(default=None, description="Target browser tab group ID")
    filename: str | None = Field(default=None, description="Optional destination filename")


class TaskCompleteRequest(BaseModel):
    """Request schema for concluding an automation session and finalizing documentation."""

    tab_group_id: int | None = Field(default=None, description="Target browser tab group ID")
    result: str | None = Field(default=None, description="Summary result text or deliverables overview")
    status: str = Field(default="completed", description="Final task completion status: 'completed' or 'failed'")


class ErrorDetail(BaseModel):
    """Standardized error detail entity with error code and description."""

    code: str = Field(..., description="Standardized error code classification")
    message: str = Field(..., description="Detailed explanatory error message")


class StandardResponse(BaseModel):
    """Universal standard API response wrapper for gateway endpoints."""

    status: ResponseStatus = Field(..., description="High-level operation status classification")
    data: Any | None = Field(default=None, description="Payload data returned on success")
    error: ErrorDetail | None = Field(default=None, description="Error details returned on failure")
    message: str | None = Field(default=None, description="Informational message or operator notes")
    timestamp: float = Field(default_factory=lambda: time.time(), description="Epoch timestamp of response generation")


class ServerStatusResponse(BaseModel):
    """Health check and connection telemetry response from the gateway."""

    status: str = Field(..., description="Server status: 'running' or 'healthy'")
    extension_connected: bool = Field(..., description="Whether the Chrome extension is connected via WebSocket")
    human_in_control: bool = Field(..., description="Whether a human operator currently has lockout control")
    last_intervention_notes: str | None = Field(default=None, description="Notes from the most recent human release")
    idle_seconds_remaining: float = Field(default=0.0, description="Seconds remaining before auto-idle shutdown")


# ============================================================================
# Session Logging & History Models
# ============================================================================


class SessionStatus(str, Enum):
    """Lifecycle state of a persistent browser automation session."""

    ACTIVE = "active"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ABORTED = "aborted"
    ERROR = "error"


class SessionEventType(str, Enum):
    """Fine-grained event classifications recorded in session telemetry (session.jsonl)."""

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
    PLAN_REGISTERED = "plan_registered"
    MILESTONE_STARTED = "milestone_started"
    MILESTONE_COMPLETED = "milestone_completed"


class SessionEventModel(BaseModel):
    """Represents a single granular event appended to the session.jsonl stream."""

    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}", description="Unique event identifier")
    session_id: str = Field(..., description="Correlation ID of parent session")
    start_time: float = Field(default_factory=lambda: time.time(), description="Epoch timestamp of event dispatch")
    end_time: float | None = Field(default=None, description="Epoch timestamp of event conclusion")
    duration_ms: float | None = Field(default=None, description="Duration in milliseconds")
    type: SessionEventType = Field(..., description="Event type classification")
    title: str = Field(..., description="Concise human-readable event title")
    tab_id: int | None = Field(default=None, description="Browser tab identifier")
    tab_group_id: int | None = Field(default=None, description="Browser tab group identifier")
    url: str | None = Field(default=None, description="Document URL at time of event")
    payload: dict[str, Any] | None = Field(default=None, description="Event-specific parameters and metadata")
    artifact_link: str | None = Field(default=None, description="Relative path to associated artifact if offloaded")


class SessionSummaryModel(BaseModel):
    """Aggregated session summary entity stored in SQLite and monthly JSON indexes."""

    session_id: str = Field(..., description="Unique session identifier")
    session_title: str = Field(..., description="Descriptive session title")
    tab_group_id: int = Field(..., description="Chrome tab group ID")
    tab_group_name: str = Field(..., description="Chrome tab group label")
    agent_name: str = Field(..., description="Agent name dynamically supplied by extension port settings")
    group_color: str = Field(..., description="Tab group accent color dynamically supplied by extension port settings")
    status: SessionStatus = Field(default=SessionStatus.ACTIVE, description="Current session lifecycle status")
    start_time: float = Field(default_factory=lambda: time.time(), description="Session start epoch timestamp")
    end_time: float | None = Field(default=None, description="Session conclusion epoch timestamp")
    duration_ms: float | None = Field(default=None, description="Total execution duration in milliseconds")
    event_count: int = Field(default=0, description="Total number of logged events")
    action_count: int = Field(default=0, description="Total number of executed browser actions")
    takeover_count: int = Field(default=0, description="Total number of human takeover interventions")
    session_path: str = Field(..., description="Relative filesystem path to session workspace")
    artifacts_count: int = Field(default=0, description="Count of saved offloaded artifacts")
    end_reason: str | None = Field(default=None, description="Explanation for session termination")


class MonthlyIndexModel(BaseModel):
    """Catalog of session summaries grouped by month (YYYY-MM)."""

    updated_at: float = Field(default_factory=lambda: time.time(), description="Epoch timestamp of index update")
    months: dict[str, list[SessionSummaryModel]] = Field(
        default_factory=dict, description="Dictionary mapping month strings to session summary lists"
    )


# ============================================================================
# Subskills & Central Vault Models (Spec 18)
# ============================================================================


class SubskillModel(BaseModel):
    """Canonical model for a tested, reusable browser automation subskill SOP."""

    name: str = Field(..., description="Unique slug identifier (e.g. linkedin-crm-enricher)")
    display_title: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of what this subskill automates")
    tags: list[str] = Field(default_factory=list, description="Searchable semantic tags")
    vault_path: str = Field(default="", description="Relative path to subskill in permanent central vault")
    subskill_file: str = Field(default="sub_skill.md", description="Relative filename of the playbook")
    playbook_path: str = Field(default="", description="Relative path to sub_skill.md playbook (Spec 26)")
    adhoc_tools: list[str] = Field(default_factory=list, description="List of filenames inside adhocs/ folder")
    times_borrowed: int = Field(default=0, description="Counter of times this subskill has been borrowed")
    times_referenced: int = Field(
        default=0, description="Counter of times this subskill has been referenced/borrowed (Spec 26)"
    )
    success_rate: float = Field(default=1.0, description="Reported task success rate (0.0 to 1.0)")
    origin_session_id: str | None = Field(
        default=None, description="Session ID of the source or latest updated session"
    )
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
    """Master catalog index of all registered subskills in the system."""

    version: str = Field(default="2.1.0", description="Index schema version")
    updated_at: Any = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    subskills: dict[str, SubskillModel] = Field(default_factory=dict, description="Mapping of slug to subskill model")


class BorrowedSubskillReference(BaseModel):
    """Manifest record of a subskill cloned into an active session workspace."""

    name: str = Field(..., description="Subskill slug identifier")
    borrowed_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    vault_path: str = Field(..., description="Relative path to subskill in central vault")
    referenced_adhocs: list[str] = Field(default_factory=list, description="Referenced adhoc tool filenames")


class SessionManifestModel(BaseModel):
    """Comprehensive session metadata manifest persisted in session workspace."""

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
    borrowed_subskills: list[BorrowedSubskillReference] = Field(
        default_factory=list, description="Borrowed subskills references"
    )
    universal_adhocs_referenced: list[str] = Field(default_factory=list, description="Universal adhocs used")
    local_overrides: list[str] = Field(default_factory=list, description="Local adhoc overrides in session/adhocs/")
    created_adhocs: list[str] = Field(default_factory=list, description="Newly created adhocs in session/adhocs/")


class BorrowSubskillPayload(BaseModel):
    """Payload for borrowing a subskill into an active session workspace."""

    name: str = Field(..., description="Slug name of the subskill to borrow")
    session_title: str = Field(..., min_length=1, description="Title for target session provided by the agent")
    tab_group_id: int | None = Field(default=None, description="Optional target tab group ID")
    input_file_path: str | None = Field(default=None, description="Optional path of input data file to copy into input/")


class RegisterSubskillPayload(BaseModel):
    """Payload for registering a completed session as a reusable subskill in the central catalog."""

    session_path: str = Field(..., description="Relative or absolute path to session folder")
    name: str = Field(..., description="Unique slug identifier for the subskill")
    display_title: str | None = Field(default=None, description="Human-readable display title")
    description: str | None = Field(default=None, description="Detailed subskill description")
    tags: list[str] | None = Field(default=None, description="List of keyword tags")
    adhoc_tools: list[str] | None = Field(default=None, description="Specific adhoc script filenames")
    subskill_markdown: str | None = Field(default=None, description="Optional raw markdown for sub_skill.md")


class PromoteAdhocPayload(BaseModel):
    """Payload for promoting a session adhoc tool into the central or subskill vault."""

    session_path: str = Field(..., description="Path to session folder containing the adhoc tool")
    tool_name: str = Field(..., description="Filename of adhoc tool to promote (e.g. verify_company_size.py)")
    target: str = Field(default="universal", description="Promotion target vault: 'universal' or 'subskill'")
    subskill_name: str | None = Field(default=None, description="Target subskill name if target is 'subskill'")


class RunAdhocPayload(BaseModel):
    """Legacy adhoc execution request payload (Spec 18; retired in Spec 38)."""

    tool_name: str = Field(..., description="Filename of the adhoc tool (e.g. probe_dom.py)")
    session_path: str | None = Field(
        default=None, description="Optional session path for resolving local overrides and subskill adhocs"
    )
    args: list[str] = Field(default_factory=list, description="Command line arguments to pass to the script")
