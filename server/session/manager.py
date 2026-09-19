"""
AgentSocket - Core Session Manager & Lifecycle Subsystem
Handles active session maps, step latency benchmarking, threshold offloading,
subskills catalog & borrowing, and automatic adhoc suite seeding.
"""

from __future__ import annotations
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from server.logger import logger
from server.models import (
    MonthlyIndexModel,
    SessionEventModel,
    SessionEventType,
    SessionStatus,
    SessionSummaryModel,
    SubskillModel,
    SubskillsIndexModel,
    SessionManifestModel,
    BorrowedSubskillReference,
    PromoteAdhocPayload,
    RunAdhocPayload,
    MilestoneStatus,
    PlanMilestone,
    PlanPayload,
    UpdateMilestonePayload,
)
from server.session.documenter import SessionDocumenter
from server.session.formatter import (
    format_session_thread,
    print_history_table,
    print_session_logs,
    print_subskill_details,
    print_subskills_table,
)
from server.session.storage import (
    DEFAULT_BASE_LOG_DIR,
    DEFAULT_SUBSKILLS_DIR,
    DEFAULT_ADHOCS_DIR,
    SessionStorage,
    get_relative_session_path,
    sanitize_filename,
)
from server.subskills.manager import SubskillsManager

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES_ADHOCS_DIR = os.path.join(REPO_ROOT, "server", "templates", "adhocs")
CENTRAL_ADHOCS_DIR = os.path.join(REPO_ROOT, "server", "adhocs")

OFFLOAD_STRING_THRESHOLD = 10000  # 10 KB string length
OFFLOAD_ARRAY_THRESHOLD = 50       # > 50 items in list


def seed_universal_adhocs(session_adhoc_dir: str) -> list[str]:
    """Copies all universal adhoc tools from server/templates/adhocs into the session adhocs/ directory."""
    seeded: list[str] = []
    os.makedirs(session_adhoc_dir, exist_ok=True)
    if not os.path.exists(TEMPLATES_ADHOCS_DIR):
        return seeded

    for filename in os.listdir(TEMPLATES_ADHOCS_DIR):
        if filename.endswith(".py"):
            src = os.path.join(TEMPLATES_ADHOCS_DIR, filename)
            dst = os.path.join(session_adhoc_dir, filename)
            if not os.path.exists(dst) and os.path.isfile(src):
                try:
                    shutil.copy2(src, dst)
                    seeded.append(filename)
                except Exception as e:
                    logger.warning(f"Failed to seed adhoc tool {filename}: {e}")

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|token|secret|cvv|cvc|api_key|apikey|auth_token|access_token|private_key|credentials)",
    re.IGNORECASE,
)


def redact_sensitive_payload(val: Any) -> Any:
    """Recursively redacts sensitive keys and values with [REDACTED] (Spec 25 Zero-Knowledge)."""
    if isinstance(val, dict):
        redacted: dict[str, Any] = {}
        for k, v in val.items():
            k_str = str(k)
            if SENSITIVE_KEY_PATTERN.search(k_str):
                redacted[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                redacted[k] = redact_sensitive_payload(v)
            else:
                redacted[k] = v

        selector_or_field = (
            str(val.get("selector", ""))
            + " "
            + str(val.get("input_type", ""))
            + " "
            + str(val.get("name", ""))
            + " "
            + str(val.get("field", ""))
            + " "
            + str(val.get("label", ""))
            + " "
            + str(val.get("id", ""))
        )
        if SENSITIVE_KEY_PATTERN.search(selector_or_field):
            if "text" in redacted:
                redacted["text"] = "[REDACTED]"
            if "value" in redacted:
                redacted["value"] = "[REDACTED]"
        return redacted
    elif isinstance(val, list):
        return [redact_sensitive_payload(item) for item in val]
    return val


@dataclass
class ActiveSession:
    session_id: str
    session_title: str
    tab_group_id: int
    tab_group_name: str
    group_color: str
    agent_name: str
    status: SessionStatus
    start_time: float
    session_dir: str
    session_path: str
    artifacts_dir: str
    jsonl_path: str
    input_dir: str = ""
    output_dir: str = ""
    adhocs_dir: str = ""
    last_action_time: float = field(default_factory=lambda: time.time())
    end_time: float | None = None
    duration_ms: float | None = None
    event_count: int = 0
    action_count: int = 0
    takeover_count: int = 0
    artifacts_count: int = 0
    end_reason: str | None = None
    human_takeover_start_time: float | None = None
    milestones: list[PlanMilestone] = field(default_factory=list)
    active_milestone_index: int | None = None
    current_action: str | None = None


def render_milestones_markdown(
    session_title: str,
    milestones: list[PlanMilestone],
    active_index: int | None = None,
    current_action: str | None = None,
) -> str:
    """Renders clean, executive strategic milestones checklist (Spec 32)."""
    total = len(milestones)
    completed = sum(1 for m in milestones if m.status in (MilestoneStatus.COMPLETED, "completed"))
    percent = int((completed / total) * 100) if total > 0 else 0

    filled_blocks = int(round((percent / 100) * 10))
    empty_blocks = 10 - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks

    active_str = "None (Idle)"
    if active_index and 1 <= active_index <= total:
        active_m = milestones[active_index - 1]
        active_str = f"Milestone {active_m.index}: {active_m.title}"
    elif completed == total and total > 0:
        active_str = "✅ All Strategic Milestones Completed (100%)"

    action_str = current_action or "None (Idle)"

    lines = [
        f"# 🎯 Strategic Plan: {session_title}",
        "",
        "## 📊 Milestone Progress",
        f"*Progress: [{bar}] {completed}/{total} Milestones Completed ({percent}%)*",
        f"*Active Milestone:* `{active_str}`",
        f"*Live Micro-Action:* `{action_str}`",
        "",
        "---",
        "",
        "## 🏁 Strategic Milestones Checklist",
    ]

    for m in milestones:
        status_val = m.status.value if hasattr(m.status, "value") else str(m.status)
        if status_val == "completed":
            check_char = "x"
            suffix = f" — COMPLETED ({m.description})" if m.description else " — COMPLETED"
        elif status_val == "in_progress":
            check_char = "/"
            suffix = f" — IN PROGRESS ({m.description})" if m.description else " — IN PROGRESS"
        elif status_val == "failed":
            check_char = "x"
            suffix = f" — FAILED ({m.description})" if m.description else " — FAILED"
        else:
            check_char = " "
            suffix = f" — {m.description}" if m.description else ""

        lines.append(f"- [{check_char}] **Milestone {m.index}:** {m.title}{suffix}")

    lines.append("")
    return "\n".join(lines)


@dataclass
class AtomicStep:
    index: int
    title: str
    unit_id: str | None = None
    status: str = "pending"  # "pending", "in_progress", "completed", "failed"
    details: str | None = None


class StepTracker:
    """
    Dedicated Standalone Atomic Step & Live Progress Tracker (Spec 17).
    Maintains machine-readable input/plan.json and human-readable input/implementation_plan.md
    with real-time ASCII progress bar and granular checklist, while dispatching live progress frames
    to the AgentSocket gateway.
    """

    def __init__(
        self,
        session_title: str,
        steps: list[str] | list[dict[str, Any]] | list[AtomicStep],
        steps_file_path: str | Path | None = None,
        plan_json_path: str | Path | None = None,
        server_url: str | None = None,
        auto_dispatch: bool = True,
    ) -> None:
        self.session_title = session_title
        self.server_url = server_url
        self.auto_dispatch = auto_dispatch
        self.atomic_steps: list[AtomicStep] = []
        self.active_step_index: int | None = None

        # Resolve paths
        self.steps_file_path: str | None = str(steps_file_path) if steps_file_path else None
        self.plan_json_path: str | None = str(plan_json_path) if plan_json_path else None

        if self.steps_file_path and not self.plan_json_path:
            dir_name = os.path.dirname(os.path.abspath(self.steps_file_path))
            if self.steps_file_path.endswith(".json"):
                self.plan_json_path = self.steps_file_path
                self.steps_file_path = os.path.join(dir_name, "implementation_plan.md")
            else:
                self.plan_json_path = os.path.join(dir_name, "plan.json")
        elif self.plan_json_path and not self.steps_file_path:
            dir_name = os.path.dirname(os.path.abspath(self.plan_json_path))
            self.steps_file_path = os.path.join(dir_name, "implementation_plan.md")

        for idx, item in enumerate(steps, start=1):
            if isinstance(item, AtomicStep):
                self.atomic_steps.append(item)
            elif isinstance(item, dict):
                self.atomic_steps.append(
                    AtomicStep(
                        index=item.get("index", idx),
                        title=item.get("title", f"Step {idx:02d}"),
                        unit_id=item.get("unit_id") or item.get("id"),
                        status=item.get("status", "pending"),
                        details=item.get("details"),
                    )
                )
            else:
                title_str = str(item)
                match = re.search(r"\b([A-Z]{2,6}-\d{3,6})\b", title_str)
                unit_id = match.group(1) if match else None
                self.atomic_steps.append(
                    AtomicStep(
                        index=idx,
                        title=title_str,
                        unit_id=unit_id,
                        status="pending",
                    )
                )

        if self.steps_file_path or self.plan_json_path:
            self.save()
        if self.auto_dispatch:
            self.dispatch_progress(step_current=0, step_title="Session Initialized")

    @classmethod
    def from_json(
        cls,
        json_path: str | Path,
        plan_md_path: str | Path | None = None,
        server_url: str | None = None,
        auto_dispatch: bool = False,
    ) -> "StepTracker":
        """Loads a StepTracker instance directly from a plan.json file."""
        with open(str(json_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        session_title = data.get("session_title", "Agent Task")
        steps = data.get("steps", [])
        tracker = cls(
            session_title=session_title,
            steps=steps,
            steps_file_path=plan_md_path,
            plan_json_path=json_path,
            server_url=server_url,
            auto_dispatch=auto_dispatch,
        )
        tracker.active_step_index = data.get("active_step_index")
        return tracker

    @classmethod
    def from_plan(
        cls,
        session_dir_or_input: str | Path,
        session_title: str | None = None,
        server_url: str | None = None,
        auto_dispatch: bool = False,
    ) -> "StepTracker | None":
        """Attempts to load a StepTracker from a session directory or input folder."""
        base_path = Path(session_dir_or_input)
        candidates = [
            base_path / "input" / "plan.json",
            base_path / "input" / "steps.json",
            base_path / "plan.json",
            base_path / "steps.json",
        ]
        for c in candidates:
            if c.exists():
                return cls.from_json(c, server_url=server_url, auto_dispatch=auto_dispatch)
        return None

    @property
    def total_steps(self) -> int:
        return len(self.atomic_steps)

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.atomic_steps if s.status == "completed")

    @property
    def progress_percent(self) -> int:
        if self.total_steps == 0:
            return 100
        return int((self.completed_count / self.total_steps) * 100)

    def to_dict(self) -> dict[str, Any]:
        """Serializes current steps state to a JSON-compatible dictionary."""
        return {
            "session_title": self.session_title,
            "total_steps": self.total_steps,
            "completed_count": self.completed_count,
            "progress_percent": self.progress_percent,
            "active_step_index": self.active_step_index,
            "steps": [
                {
                    "index": s.index,
                    "title": s.title,
                    "unit_id": s.unit_id,
                    "status": s.status,
                    "details": s.details,
                }
                for s in self.atomic_steps
            ],
        }

    def start_step(self, step_index: int, description: str | None = None) -> None:
        """Marks a step as in progress and updates steps.md + plan.json + gateway HUD."""
        if 1 <= step_index <= len(self.atomic_steps):
            self.active_step_index = step_index
            step = self.atomic_steps[step_index - 1]
            step.status = "in_progress"
            if description:
                step.details = description

            self.save()

            if self.auto_dispatch:
                self.dispatch_progress(
                    step_current=step_index,
                    step_title=f"Step {step_index:02d}: {step.unit_id or ''} {step.title}".strip(),
                )

    def complete_step(self, step_index: int, details: str | None = None) -> None:
        """Marks a step as completed and updates steps.md + plan.json + gateway HUD."""
        if 1 <= step_index <= len(self.atomic_steps):
            step = self.atomic_steps[step_index - 1]
            step.status = "completed"
            if details:
                step.details = details
            if self.active_step_index == step_index:
                self.active_step_index = None

            self.save()

            if self.auto_dispatch:
                self.dispatch_progress(
                    step_current=step_index,
                    step_title=f"Completed Step {step_index:02d}: {step.unit_id or step.title}",
                )

    def fail_step(self, step_index: int, error_details: str | None = None) -> None:
        """Marks a step as failed / error and updates steps.md + plan.json + gateway HUD."""
        if 1 <= step_index <= len(self.atomic_steps):
            step = self.atomic_steps[step_index - 1]
            step.status = "failed"
            if error_details:
                step.details = f"ERROR: {error_details}"
            if self.active_step_index == step_index:
                self.active_step_index = None

            self.save()

            if self.auto_dispatch:
                self.dispatch_progress(
                    step_current=step_index,
                    step_title=f"Failed Step {step_index:02d}: {step.unit_id or step.title}",
                )

    def finish_all(self, execute_task_complete: bool = True) -> None:
        """Marks all remaining steps as completed and dispatches 100% and task_complete."""
        for step in self.atomic_steps:
            if step.status != "failed":
                step.status = "completed"
        self.active_step_index = None

        self.save()

        if self.auto_dispatch:
            self.dispatch_progress(
                step_current=self.total_steps,
                step_title="All steps completed",
            )
            if execute_task_complete:
                try:
                    from server.socket_launcher import execute_action
                    execute_action("task_complete", target_data=self.session_title, session_title=self.session_title)
                except Exception as e:
                    logger.debug(f"Could not dispatch task_complete action: {e}")

    def render_markdown(self) -> str:
        """Renders the standard steps.md markdown string."""
        total = self.total_steps
        completed = self.completed_count
        percent = self.progress_percent

        filled_blocks = int(round((percent / 100) * 10))
        empty_blocks = 10 - filled_blocks
        bar = "█" * filled_blocks + "░" * empty_blocks

        active_str = "None (Idle)"
        if self.active_step_index and 1 <= self.active_step_index <= total:
            active_step = self.atomic_steps[self.active_step_index - 1]
            unit_part = f"`{active_step.unit_id}` " if active_step.unit_id else ""
            active_str = f"Step {active_step.index:02d}: {unit_part}{active_step.title}"
        elif completed == total and total > 0:
            active_str = "✅ All Steps Completed (100%)"

        lines = [
            f"# 🎯 Atomic Step Execution: {self.session_title}",
            "",
            "## 📊 Live Progress",
            f"*Progress: [{bar}] {completed}/{total} Steps Completed ({percent}%)*",
            f"*Current Active Step:* `{active_str}`",
            "",
            "---",
            "",
            "## 📋 Step Checklist (1 Unit = 1 Atomic Step)",
        ]

        for s in self.atomic_steps:
            if s.status == "completed":
                check_char = "x"
                suffix = f" — COMPLETED ({s.details})" if s.details else " — COMPLETED"
            elif s.status == "in_progress":
                check_char = "/"
                suffix = f" — IN PROGRESS ({s.details})" if s.details else " — IN PROGRESS"
            elif s.status == "failed":
                check_char = "x"
                suffix = f" — FAILED ({s.details})" if s.details else " — FAILED"
            else:
                check_char = " "
                suffix = f" — {s.details}" if s.details else ""

            unit_part = f"`{s.unit_id}` " if s.unit_id else ""
            lines.append(f"- [{check_char}] **Step {s.index:02d}:** {unit_part}{s.title}{suffix}")

        lines.append("")
        return "\n".join(lines)

    def save(self) -> None:
        """Saves current steps to both Markdown and JSON on disk."""
        if self.steps_file_path:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.steps_file_path)), exist_ok=True)
                with open(self.steps_file_path, "w", encoding="utf-8") as f:
                    f.write(self.render_markdown())
            except Exception as e:
                logger.warning(f"Could not save steps markdown: {e}")

        if self.plan_json_path:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.plan_json_path)), exist_ok=True)
                with open(self.plan_json_path, "w", encoding="utf-8") as f:
                    json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Could not save steps json: {e}")

    def dispatch_progress(self, step_current: int | None = None, step_title: str | None = None) -> dict[str, Any]:
        """Dispatches live progress to gateway server."""
        current = step_current if step_current is not None else self.completed_count
        title = step_title or f"Step {current:02d}: In Progress"
        try:
            import requests
            from server.socket_launcher import resolve_server_url, get_auth_headers
            url = self.server_url or resolve_server_url()
            payload = {
                "session_title": self.session_title,
                "step_current": current,
                "step_total": self.total_steps,
                "step_title": title,
            }
            resp = requests.post(f"{url}/progress", json=payload, headers=get_auth_headers(), timeout=2.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {"status": "local", "progress_percent": self.progress_percent}


class SessionManager:
    """Manages active session lifecycle, central vault, subskill borrowing, and logging operations."""

    def __init__(
        self,
        base_log_dir: str = DEFAULT_BASE_LOG_DIR,
        subskills_dir: str | None = None,
        adhocs_dir: str | None = None,
        db_path: str | None = None,
    ):
        self.storage = SessionStorage(
            base_log_dir=base_log_dir,
            subskills_dir=subskills_dir,
            adhocs_dir=adhocs_dir,
            db_path=db_path,
        )
        self.base_log_dir = self.storage.base_log_dir
        self.history_index_dir = self.storage.history_index_dir
        self.index_file = self.storage.index_file
        self.subskills_dir = self.storage.subskills_dir
        self.adhocs_dir = self.storage.adhocs_dir
        self.subskills_index_file = self.storage.subskills_index_file
        self.active_sessions: dict[int, ActiveSession] = {}
        self.title_to_group_id: dict[str, int] = {}
        self.subskills = SubskillsManager(
            subskills_dir=self.subskills_dir,
            db_path=self.storage.db_path,
            index_file=self.subskills_index_file,
        )

    def _ensure_directories(self) -> None:
        self.storage.ensure_directories()

    def _get_relative_session_path(self, session_dir: str) -> str:
        return get_relative_session_path(session_dir)

    def get_session_paths(self, session_dir_or_path: str) -> dict[str, str]:
        return self.storage.get_session_paths(session_dir_or_path, self.active_sessions)

    def _read_index(self) -> MonthlyIndexModel:
        return self.storage.read_index()

    def _write_index(self, index_model: MonthlyIndexModel) -> None:
        self.storage.write_index(index_model)

    def _read_subskills_index(self) -> SubskillsIndexModel:
        return self.subskills._read_subskills_index()

    def _write_subskills_index(self, index_model: SubskillsIndexModel) -> None:
        self.subskills._write_subskills_index(index_model)

    def _update_index_for_session(self, session: ActiveSession) -> None:
        self.storage.update_index_for_session(session)

    # ========================================================================
    # Session Creation & Retrieval
    # ========================================================================
    def get_or_create_session(
        self,
        tab_group_id: int,
        tab_group_name: str = "AgentSocket Task",
        group_color: str = "purple",
        agent_name: str = "AgentSocket Local",
        reuse_existing_today: bool = True,
    ) -> ActiveSession:
        """Retrieves existing active session by tab_group_id or initializes a new date-partitioned session with isolated folders and seeded adhocs."""
        clean_name = tab_group_name.replace("✅", "").strip()
        sanitized_title = sanitize_filename(clean_name)

        # 1. Direct group_id match in active_sessions
        if tab_group_id in self.active_sessions:
            session = self.active_sessions[tab_group_id]
            session.last_action_time = time.time()
            return session

        # 2. Check if a session with this title is currently in active_sessions under another tab_group_id
        for existing in list(self.active_sessions.values()):
            if sanitize_filename(existing.tab_group_name.replace("✅", "").strip()) == sanitized_title:
                old_gid = existing.tab_group_id
                if old_gid != tab_group_id:
                    self.active_sessions.pop(old_gid, None)
                    existing.tab_group_id = tab_group_id
                self.active_sessions[tab_group_id] = existing
                self.title_to_group_id[tab_group_name] = tab_group_id
                self.title_to_group_id[clean_name] = tab_group_id
                existing.status = SessionStatus.ACTIVE
                existing.last_action_time = time.time()
                return existing

        now = time.time()
        dt = datetime.fromtimestamp(now)
        date_str = dt.strftime("%Y-%m-%d")
        time_str_dir = dt.strftime("%H-%M-%S")
        time_str_id = dt.strftime("%H%M%S")
        date_str_id = dt.strftime("%Y%m%d")

        session_dir = None
        # 3. If reuse_existing_today is True, check if today's log dir already has a folder for this task
        if reuse_existing_today:
            today_dir = os.path.join(self.base_log_dir, date_str)
            if os.path.exists(today_dir):
                candidate_folders = [
                    d for d in os.listdir(today_dir)
                    if os.path.isdir(os.path.join(today_dir, d)) and d.startswith(sanitized_title)
                ]
                if candidate_folders:
                    # Pick the latest existing folder for this session
                    latest_folder = sorted(candidate_folders)[-1]
                    session_dir = os.path.join(today_dir, latest_folder)

        if not session_dir:
            session_id = f"sess_{date_str_id}_{time_str_id}_{tab_group_id}"
            session_title = f"{tab_group_name} | {dt.strftime('%Y-%m-%d_%H:%M:%S')}"
            folder_name = f"{sanitized_title}_{time_str_dir}_gid{tab_group_id}"
            session_dir = os.path.join(self.base_log_dir, date_str, folder_name)
        else:
            folder_name = os.path.basename(session_dir)
            session_id = f"sess_{date_str_id}_{time_str_id}_{tab_group_id}"
            session_title = f"{tab_group_name} | {dt.strftime('%Y-%m-%d_%H:%M:%S')}"

        artifacts_dir = os.path.join(session_dir, "artifacts")
        adhocs_dir = os.path.join(session_dir, "adhocs")
        input_dir = os.path.join(session_dir, "input")
        output_dir = os.path.join(session_dir, "output")
        jsonl_path = os.path.join(session_dir, "session.jsonl")

        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(artifacts_dir, exist_ok=True)
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        # Initialize session manifest in YAML frontmatter of SESSION_DOCUMENT.md (Spec 25)
        manifest = self.storage.read_manifest(session_dir)
        if not manifest:
            manifest = SessionManifestModel(
                session_id=session_id,
                session_title=session_title,
                tab_group_id=tab_group_id,
                tab_group_name=tab_group_name,
                group_color=group_color,
                agent_name=agent_name,
                mode="direct",
                status=SessionStatus.ACTIVE.value,
                created_at=datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            self.storage.write_manifest(session_dir, manifest)

        session_path = self._get_relative_session_path(session_dir)

        session = ActiveSession(
            session_id=session_id,
            session_title=session_title,
            tab_group_id=tab_group_id,
            tab_group_name=tab_group_name,
            group_color=group_color,
            agent_name=agent_name,
            status=SessionStatus.ACTIVE,
            start_time=now,
            session_dir=session_dir,
            session_path=session_path,
            artifacts_dir=artifacts_dir,
            jsonl_path=jsonl_path,
            input_dir=input_dir,
            output_dir=output_dir,
            adhocs_dir=adhocs_dir,
            last_action_time=now,
        )

        self.active_sessions[tab_group_id] = session
        self.title_to_group_id[tab_group_name] = tab_group_id
        self.title_to_group_id[clean_name] = tab_group_id

        # Log SESSION_START event
        self.log_event(
            tab_group_id=tab_group_id,
            event_type=SessionEventType.SESSION_START,
            title=f"Session Started: {tab_group_name}",
            start_time=now,
            end_time=now,
            tab_group_id_val=tab_group_id,
            payload={
                "session_id": session_id,
                "session_title": session_title,
                "group_color": group_color,
                "agent_name": agent_name,
            },
        )

        self._update_index_for_session(session)
        self.generate_session_document(session_dir)
        return session

    def get_active_session_by_group_id(self, tab_group_id: int) -> ActiveSession | None:
        return self.active_sessions.get(tab_group_id)

    def get_active_session_by_title(self, session_title: str) -> ActiveSession | None:
        if session_title in self.title_to_group_id:
            gid = self.title_to_group_id[session_title]
            return self.active_sessions.get(gid)
        for session in self.active_sessions.values():
            if session.tab_group_name == session_title or session_title in session.session_title:
                return session
        return None

    # ========================================================================
    # Strategic Milestones & Plan Persistence (Spec 32)
    # ========================================================================
    def _save_milestones_artifacts(self, session: ActiveSession) -> None:
        """Persists input/plan.json and input/implementation_plan.md for strategic milestones (Spec 32)."""
        input_dir = session.input_dir or os.path.join(session.session_dir, "input")
        os.makedirs(input_dir, exist_ok=True)

        total = len(session.milestones)
        completed = sum(1 for m in session.milestones if m.status in (MilestoneStatus.COMPLETED, "completed"))
        percent = int((completed / total) * 100) if total > 0 else 0

        plan_json_path = os.path.join(input_dir, "plan.json")
        plan_dict = {
            "session_title": session.session_title,
            "total_milestones": total,
            "completed_milestones": completed,
            "progress_percent": percent,
            "active_milestone_index": session.active_milestone_index,
            "current_action": session.current_action,
            "milestones": [
                {
                    "index": m.index,
                    "title": m.title,
                    "description": m.description,
                    "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                }
                for m in session.milestones
            ],
        }
        try:
            with open(plan_json_path, "w", encoding="utf-8") as f:
                json.dump(plan_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save plan.json: {e}")

        plan_md_path = os.path.join(input_dir, "implementation_plan.md")
        try:
            with open(plan_md_path, "w", encoding="utf-8") as f:
                f.write(render_milestones_markdown(
                    session_title=session.session_title,
                    milestones=session.milestones,
                    active_index=session.active_milestone_index,
                    current_action=session.current_action,
                ))
        except Exception as e:
            logger.warning(f"Could not save implementation_plan.md: {e}")

    def set_session_plan(
        self,
        session_title: str,
        milestones: list[PlanMilestone | dict[str, Any] | str],
        active_index: int = 1,
        tab_group_id: int | None = None,
    ) -> dict[str, Any]:
        """Registers or updates strategic milestones for an active session (Spec 32)."""
        session = None
        if tab_group_id is not None:
            session = self.get_active_session_by_group_id(tab_group_id)
        if not session and session_title:
            session = self.get_active_session_by_title(session_title)
        if not session:
            gid = tab_group_id if tab_group_id is not None else 0
            session = self.get_or_create_session(tab_group_id=gid, tab_group_name=session_title)

        parsed_milestones: list[PlanMilestone] = []
        for idx, item in enumerate(milestones, start=1):
            if isinstance(item, PlanMilestone):
                parsed_milestones.append(item)
            elif isinstance(item, dict):
                m_idx = item.get("index", idx)
                m_title = item.get("title", f"Milestone {m_idx}")
                m_desc = item.get("description")
                m_status = item.get("status", MilestoneStatus.PENDING)
                if isinstance(m_status, str):
                    try:
                        m_status = MilestoneStatus(m_status)
                    except ValueError:
                        m_status = MilestoneStatus.PENDING
                parsed_milestones.append(PlanMilestone(index=m_idx, title=m_title, description=m_desc, status=m_status))
            elif isinstance(item, str):
                parsed_milestones.append(PlanMilestone(index=idx, title=item, status=MilestoneStatus.PENDING))

        if 1 <= active_index <= len(parsed_milestones):
            parsed_milestones[active_index - 1].status = MilestoneStatus.IN_PROGRESS

        session.milestones = parsed_milestones
        session.active_milestone_index = active_index

        self._save_milestones_artifacts(session)

        now = time.time()
        self.log_event(
            tab_group_id=session.tab_group_id,
            event_type=SessionEventType.PLAN_REGISTERED,
            title=f"Plan Registered: {len(parsed_milestones)} Strategic Milestones",
            start_time=now,
            end_time=now,
            tab_group_id_val=session.tab_group_id,
            payload={
                "session_title": session_title,
                "total_milestones": len(parsed_milestones),
                "active_index": active_index,
                "milestones": [
                    {
                        "index": m.index,
                        "title": m.title,
                        "description": m.description,
                        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                    }
                    for m in parsed_milestones
                ],
            },
        )

        total = len(parsed_milestones)
        completed = sum(1 for m in parsed_milestones if m.status in (MilestoneStatus.COMPLETED, "completed"))
        percent = int((completed / total) * 100) if total > 0 else 0
        active_title = parsed_milestones[active_index - 1].title if 1 <= active_index <= total else ""

        return {
            "status": "success",
            "session_title": session_title,
            "total_milestones": total,
            "active_index": active_index,
            "active_title": active_title,
            "progress_percent": percent,
            "milestones": [
                {
                    "index": m.index,
                    "title": m.title,
                    "description": m.description,
                    "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                }
                for m in parsed_milestones
            ],
        }

    def update_session_milestone(
        self,
        session_title: str,
        milestone_index: int | None = None,
        milestone_title: str | None = None,
        action_detail: str | None = None,
        status: MilestoneStatus | str | None = None,
        tab_group_id: int | None = None,
    ) -> dict[str, Any]:
        """Updates active milestone state or atomic action detail for a session (Spec 32)."""
        session = None
        if tab_group_id is not None:
            session = self.get_active_session_by_group_id(tab_group_id)
        if not session and session_title:
            session = self.get_active_session_by_title(session_title)
        if not session:
            gid = tab_group_id if tab_group_id is not None else 0
            session = self.get_or_create_session(tab_group_id=gid, tab_group_name=session_title)

        now = time.time()
        idx = milestone_index if milestone_index is not None else session.active_milestone_index
        if idx is not None and 1 <= idx <= len(session.milestones):
            target_m = session.milestones[idx - 1]
            if milestone_title:
                target_m.title = milestone_title
            if status:
                status_val = status if isinstance(status, MilestoneStatus) else MilestoneStatus(str(status))
                prev_status = target_m.status
                target_m.status = status_val

                if status_val == MilestoneStatus.IN_PROGRESS and prev_status != MilestoneStatus.IN_PROGRESS:
                    self.log_event(
                        tab_group_id=session.tab_group_id,
                        event_type=SessionEventType.MILESTONE_STARTED,
                        title=f"Milestone Started: [{target_m.index}/{len(session.milestones)}] {target_m.title}",
                        start_time=now,
                        end_time=now,
                        tab_group_id_val=session.tab_group_id,
                        payload={"milestone_index": target_m.index, "title": target_m.title},
                    )
                elif status_val == MilestoneStatus.COMPLETED and prev_status != MilestoneStatus.COMPLETED:
                    self.log_event(
                        tab_group_id=session.tab_group_id,
                        event_type=SessionEventType.MILESTONE_COMPLETED,
                        title=f"Milestone Completed: [{target_m.index}/{len(session.milestones)}] {target_m.title}",
                        start_time=now,
                        end_time=now,
                        tab_group_id_val=session.tab_group_id,
                        payload={"milestone_index": target_m.index, "title": target_m.title},
                    )
            session.active_milestone_index = idx

        if action_detail is not None:
            session.current_action = action_detail

        self._save_milestones_artifacts(session)

        total = len(session.milestones)
        completed = sum(1 for m in session.milestones if m.status in (MilestoneStatus.COMPLETED, "completed"))
        percent = int((completed / total) * 100) if total > 0 else 0

        active_title = ""
        cur_idx = session.active_milestone_index or (milestone_index or 1)
        if 1 <= cur_idx <= total:
            active_title = session.milestones[cur_idx - 1].title

        return {
            "status": "success",
            "session_title": session.session_title,
            "milestone_index": cur_idx,
            "milestone_title": active_title,
            "current_action": session.current_action,
            "progress_percent": percent,
            "total_milestones": total,
            "completed_milestones": completed,
        }

    # ========================================================================
    # Event Logging & Threshold Offloading
    # ========================================================================
    def log_event(
        self,
        tab_group_id: int,
        event_type: SessionEventType,
        title: str,
        start_time: float,
        end_time: float | None = None,
        tab_id: int | None = None,
        tab_group_id_val: int | None = None,
        url: str | None = None,
        payload: dict[str, Any] | None = None,
        screenshot_bytes: bytes | None = None,
    ) -> SessionEventModel | None:
        """Logs an event line into session.jsonl with step latency and offload handling."""
        session = self.get_active_session_by_group_id(tab_group_id)
        if not session:
            return None

        now = time.time()
        if end_time is None:
            end_time = now

        duration_ms = max(0.0, round((end_time - start_time) * 1000.0, 2))
        event_id = f"evt_{uuid.uuid4().hex[:8]}"

        artifact_link = None
        processed_payload = redact_sensitive_payload(payload.copy()) if payload else {}

        # 1. Check for Screenshot to Save
        if screenshot_bytes:
            screenshot_filename = f"error_screenshot_{event_id}.png"
            screenshot_path = os.path.join(session.artifacts_dir, screenshot_filename)
            try:
                with open(screenshot_path, "wb") as sf:
                    sf.write(screenshot_bytes)
                artifact_link = f"artifacts/{screenshot_filename}"
                session.artifacts_count += 1
            except Exception as e:
                logger.error(f"Error saving screenshot artifact: {e}")

        # 2. Check Explicit Threshold (10 KB or >50 array items) for Offloading
        if processed_payload:
            should_offload = False
            offload_reason = ""
            payload_str = json.dumps(processed_payload)

            if len(payload_str) > OFFLOAD_STRING_THRESHOLD:
                should_offload = True
                offload_reason = f"Payload size {len(payload_str)} exceeds 10KB threshold"

            result_val = processed_payload.get("result") or processed_payload.get("output")
            if isinstance(result_val, list) and len(result_val) > OFFLOAD_ARRAY_THRESHOLD:
                should_offload = True
                offload_reason = f"Array length {len(result_val)} exceeds 50-item threshold"

            if should_offload:
                action_name = event_type.value if hasattr(event_type, "value") else str(event_type)
                artifact_filename = f"{action_name}_{event_id}.json"
                artifact_path = os.path.join(session.artifacts_dir, artifact_filename)
                try:
                    with open(artifact_path, "w", encoding="utf-8") as af:
                        json.dump(processed_payload, af, indent=2)
                    artifact_link = f"artifacts/{artifact_filename}"
                    session.artifacts_count += 1

                    # Create lightweight preview for session.jsonl
                    preview_text = ""
                    if isinstance(result_val, list):
                        preview_text = f"[Array of {len(result_val)} items offloaded]"
                    elif isinstance(result_val, str):
                        preview_text = result_val[:480] + "..." if len(result_val) > 480 else result_val
                    else:
                        preview_text = payload_str[:480] + "..." if len(payload_str) > 480 else payload_str

                    processed_payload = {
                        "result_preview": preview_text,
                        "is_offloaded": True,
                        "payload_size_bytes": len(payload_str.encode("utf-8")),
                        "offload_reason": offload_reason,
                    }
                    if "script" in payload:
                        script_val = str(payload["script"])
                        processed_payload["script_preview"] = (
                            script_val[:300] + "..." if len(script_val) > 300 else script_val
                        )
                except Exception as e:
                    logger.error(f"Error offloading artifact payload: {e}")

        event = SessionEventModel(
            event_id=event_id,
            session_id=session.session_id,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            type=event_type,
            title=title,
            tab_id=tab_id,
            tab_group_id=tab_group_id_val or tab_group_id,
            url=url,
            payload=processed_payload if processed_payload else None,
            artifact_link=artifact_link,
        )

        # Atomic append to session.jsonl (Spec 25/28 Lean JSONL)
        try:
            with open(session.jsonl_path, "a", encoding="utf-8") as f:
                event_dict = event.model_dump(mode="json", exclude_none=True)
                if event_type != SessionEventType.SESSION_START:
                    event_dict.pop("session_id", None)
                f.write(json.dumps(event_dict) + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error writing to session.jsonl: {e}")

        # Index event in SQLite events table (Spec 25)
        self.storage.log_event_index(
            event_id=event_id,
            session_id=session.session_id,
            event_type=event_type.value if hasattr(event_type, "value") else str(event_type),
            timestamp=start_time,
            duration_ms=duration_ms,
            payload=processed_payload,
        )

        # Update session counters
        session.event_count += 1
        session.last_action_time = now

        if event_type in (SessionEventType.NAVIGATE, SessionEventType.EXECUTE_JS, SessionEventType.TASK_COMPLETE):
            session.action_count += 1
        elif event_type in (SessionEventType.HUMAN_TAKEOVER, SessionEventType.HUMAN_RELEASE):
            if event_type == SessionEventType.HUMAN_TAKEOVER:
                session.human_takeover_start_time = start_time
            session.takeover_count += 1

        self._update_index_for_session(session)
        return event

    # ========================================================================
    # Finalization, Inactivity, and Disconnect Handlers
    # ========================================================================
    def finalize_session(
        self,
        tab_group_id: int | str,
        status: SessionStatus = SessionStatus.COMPLETED,
        end_reason: str | None = None,
    ) -> ActiveSession | None:
        """Finalizes an active session, computes total duration, appends session_end event, and updates index."""
        session = None
        if isinstance(tab_group_id, int):
            session = self.active_sessions.get(tab_group_id)
        else:
            for s in self.active_sessions.values():
                if s.session_id == tab_group_id or s.tab_group_name == tab_group_id:
                    session = s
                    break

        if not session:
            return None

        actual_tab_group_id = session.tab_group_id
        now = time.time()
        session.status = status
        session.end_time = now
        session.duration_ms = max(0.0, round((now - session.start_time) * 1000.0, 2))
        session.end_reason = end_reason or ("task_complete" if status == SessionStatus.COMPLETED else "stopped")

        if status == SessionStatus.COMPLETED:
            clean_tab = session.tab_group_name.replace("✅", "").strip()
            session.tab_group_name = f"✅ {clean_tab}"
            if " | " in session.session_title:
                clean_title_part, rest = session.session_title.split(" | ", 1)
                clean_title_part = clean_title_part.replace("✅", "").strip()
                session.session_title = f"✅ {clean_title_part} | {rest}"
            else:
                clean_title = session.session_title.replace("✅", "").strip()
                session.session_title = f"✅ {clean_title}"

        # Write session_end event
        self.log_event(
            tab_group_id=actual_tab_group_id,
            event_type=SessionEventType.SESSION_END,
            title=f"Session Finalized ({status.value}): {session.end_reason}",
            start_time=now,
            end_time=now,
            tab_group_id_val=actual_tab_group_id,
            payload={
                "status": status.value,
                "end_reason": session.end_reason,
                "total_duration_ms": session.duration_ms,
                "event_count": session.event_count + 1,
            },
        )

        self._update_index_for_session(session)
        self.active_sessions.pop(actual_tab_group_id, None)
        if isinstance(tab_group_id, str):
            self.active_sessions.pop(tab_group_id, None)
        self.title_to_group_id.pop(session.tab_group_name, None)
        self.generate_session_document(session.session_dir)
        return session

    def check_inactivity(self, inactivity_threshold_seconds: float = 600.0) -> list[int]:
        """Checks for sessions exceeding the inactivity threshold (default 10min) and auto-closes them."""
        now = time.time()
        timed_out_gids: list[int] = []

        for gid, session in list(self.active_sessions.items()):
            if (now - session.last_action_time) >= inactivity_threshold_seconds:
                logger.info(
                    f"Session {session.session_id} (group {gid}) timed out after {inactivity_threshold_seconds}s of inactivity."
                )
                self.finalize_session(
                    tab_group_id=gid,
                    status=SessionStatus.STOPPED,
                    end_reason="inactivity_timeout",
                )
                timed_out_gids.append(gid)

        return timed_out_gids

    def handle_disconnect(self) -> list[int]:
        """Handles abrupt WebSocket/CDP disconnects by aborting all active sessions."""
        aborted_gids: list[int] = []
        for gid, session in list(self.active_sessions.items()):
            logger.warning(f"Abrupt browser disconnect detected. Aborting active session {session.session_id}.")
            self.finalize_session(
                tab_group_id=gid,
                status=SessionStatus.ABORTED,
                end_reason="browser_disconnected",
            )
            aborted_gids.append(gid)
        return aborted_gids

    # ========================================================================
    # Query & Document Methods
    # ========================================================================
    def query_history(
        self,
        query_hint: str = "",
        month: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self.storage.query_history(query_hint=query_hint, month=month, limit=limit)

    def format_session_thread(
        self,
        details_or_events: dict[str, Any] | list[dict[str, Any]],
        session_title: str | None = None,
        total_duration_ms: float | None = None,
    ) -> str:
        return format_session_thread(
            details_or_events=details_or_events,
            session_title=session_title,
            total_duration_ms=total_duration_ms,
        )

    def get_session_details(self, session_path: str) -> dict[str, Any]:
        return self.storage.get_session_details(session_path=session_path, formatter_fn=format_session_thread)

    def get_session_artifact(self, session_path: str, artifact_name: str) -> dict[str, Any] | str:
        return self.storage.get_session_artifact(session_path=session_path, artifact_name=artifact_name)

    def generate_session_document(self, session_dir_or_path: str) -> str:
        paths = self.get_session_paths(session_dir_or_path)
        return SessionDocumenter.generate_session_document(paths=paths, format_session_thread_fn=format_session_thread)

    def generate_thread_document(self, session_dir_or_path: str) -> str:
        paths = self.get_session_paths(session_dir_or_path)
        return SessionDocumenter.generate_thread_document(paths=paths, format_session_thread_fn=format_session_thread)

    def export_all_to_markdown(
        self,
        month: str | None = None,
        output_path: str | None = None,
    ) -> str:
        index_model = self._read_index()
        return SessionDocumenter.export_all_to_markdown(
            index_model=index_model,
            get_session_details_fn=self.get_session_details,
            month=month,
            output_path=output_path,
        )

    # ========================================================================
    # Subskills & Borrowing Engine Registry (Spec 13)
    # ========================================================================
    def list_subskills(
        self,
        query: str = "",
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Lists registered subskills using SubskillsManager (SQLite indexed search with JSON fallback)."""
        return self.subskills.list_subskills(query=query, tags=tags)

    def get_subskill(self, name: str) -> dict[str, Any] | None:
        """Retrieves a subskill by slug name, including metadata, playbook markdown, and adhoc tools."""
        return self.subskills.get_subskill(name=name)

    def register_subskill(
        self,
        session_path: str,
        name: str,
        display_title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        adhoc_tools: list[str] | None = None,
        subskill_markdown: str | None = None,
    ) -> dict[str, Any]:
        """Registers or updates a session as a permanent reusable subskill in the central vault and SQLite catalog."""
        paths = self.get_session_paths(session_path)
        session_dir = paths["session_dir"]
        rel_session_path = paths["session_path"]

        res = self.subskills.register_subskill(
            session_path=session_path,
            name=name,
            display_title=display_title,
            description=description,
            tags=tags,
            adhoc_tools=adhoc_tools,
            subskill_markdown=subskill_markdown,
        )

        subskill_data = res.get("subskill", {})
        sub_name = subskill_data.get("name") or name

        for gid, sess in self.active_sessions.items():
            if sess.session_path == rel_session_path or sess.session_dir == session_dir:
                self.log_event(
                    tab_group_id=gid,
                    event_type=SessionEventType.SUBSKILL_REGISTERED,
                    title=f"Registered Subskill: {sub_name}",
                    start_time=time.time(),
                    payload={
                        "subskill_name": sub_name,
                        "display_title": subskill_data.get("display_title"),
                        "tags": subskill_data.get("tags"),
                        "vault_path": res.get("vault_path"),
                        "playbook_path": res.get("playbook_path"),
                        "adhoc_tools": subskill_data.get("adhoc_tools", []),
                    },
                )
                break

        self.generate_session_document(session_dir)
        return res

    def borrow_subskill(
        self,
        name: str,
        target_session_id_or_title_or_path: str | None = None,
        tab_group_id: int | None = None,
        input_file_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Borrows a subskill into a target session (Spec 18):
        1. Catalog lookup in central vault.
        2. Manifest registration in target session's session_manifest.json.
        3. Copies ONLY sub_skill.md into target session workspace (lean staging, zero script duplicates).
        4. Copies input data file into input/ if provided.
        5. Increments times_borrowed and emits subskill_borrowed event.
        """
        subskill_dict = self.subskills.get_subskill(name)
        if not subskill_dict:
            return {
                "status": "error",
                "message": f"Subskill '{name}' was not found in central registry.",
            }
        subskill = SubskillModel.model_validate(subskill_dict)
        index_model = self._read_subskills_index()

        # Determine source vault directory
        vault_dir = None
        candidate_subskill_dir = os.path.join(self.subskills_dir, name)
        if os.path.isdir(candidate_subskill_dir):
            vault_dir = candidate_subskill_dir
        elif subskill.vault_path:
            clean_vault = subskill.vault_path.replace("/", os.sep).replace("\\", os.sep)
            vault_dir = clean_vault if os.path.isabs(clean_vault) else os.path.join(REPO_ROOT, clean_vault)
        elif subskill.latest_session_path:
            sess_dir = subskill.latest_session_path.replace("/", os.sep).replace("\\", os.sep)
            vault_dir = sess_dir if os.path.isabs(sess_dir) else os.path.join(REPO_ROOT, sess_dir)
        else:
            vault_dir = candidate_subskill_dir

        target_session: ActiveSession | None = None
        target_dir: str = ""

        if tab_group_id and tab_group_id in self.active_sessions:
            target_session = self.active_sessions[tab_group_id]
            target_dir = target_session.session_dir
        elif target_session_id_or_title_or_path:
            target_session = self.get_active_session_by_title(target_session_id_or_title_or_path)
            if target_session:
                target_dir = target_session.session_dir
            elif "/" in target_session_id_or_title_or_path or "\\" in target_session_id_or_title_or_path:
                clean_target = target_session_id_or_title_or_path.replace("/", os.sep).replace("\\", os.sep)
                target_dir = clean_target if os.path.isabs(clean_target) else os.path.join(REPO_ROOT, clean_target)
                os.makedirs(target_dir, exist_ok=True)
            else:
                gid = (int(time.time() * 1000) % 90000) + 1000
                target_session = self.get_or_create_session(
                    tab_group_id=gid,
                    tab_group_name=target_session_id_or_title_or_path,
                )
                target_dir = target_session.session_dir
        else:
            gid = (int(time.time() * 1000) % 90000) + 1000
            target_session = self.get_or_create_session(
                tab_group_id=gid,
                tab_group_name=f"Task: {subskill.display_title}",
            )
            target_dir = target_session.session_dir

        target_paths = self.get_session_paths(target_dir)
        os.makedirs(target_paths["input_dir"], exist_ok=True)
        os.makedirs(target_paths["output_dir"], exist_ok=True)
        os.makedirs(target_paths["artifacts_dir"], exist_ok=True)

        borrowed_files: list[str] = []

        # 1. Copy sub_skill.md ONLY into session root
        src_subskill = os.path.join(vault_dir, subskill.subskill_file)
        dst_subskill = os.path.join(target_dir, "sub_skill.md")
        if os.path.exists(src_subskill):
            try:
                shutil.copy2(src_subskill, dst_subskill)
                borrowed_files.append("sub_skill.md")
            except Exception as e:
                logger.warning(f"Warning copying sub_skill.md: {e}")

        # 2. Update session_manifest.json (Spec 18 Lean Staging - references tools, does not duplicate files)
        manifest = self.storage.read_manifest(target_dir)
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        if not manifest:
            manifest = SessionManifestModel(
                session_id=target_session.session_id if target_session else os.path.basename(target_dir),
                session_title=target_session.session_title if target_session else os.path.basename(target_dir),
                tab_group_id=target_session.tab_group_id if target_session else tab_group_id,
                created_at=now_iso,
            )

        vault_rel_path = subskill.vault_path or get_relative_session_path(vault_dir)
        existing_ref = next((b for b in manifest.borrowed_subskills if b.name == subskill.name), None)
        if existing_ref:
            existing_ref.borrowed_at = now_iso
            existing_ref.vault_path = vault_rel_path
            existing_ref.referenced_adhocs = list(subskill.adhoc_tools)
        else:
            manifest.borrowed_subskills.append(
                BorrowedSubskillReference(
                    name=subskill.name,
                    borrowed_at=now_iso,
                    vault_path=vault_rel_path,
                    referenced_adhocs=list(subskill.adhoc_tools),
                )
            )
        self.storage.write_manifest(target_dir, manifest)

        # 3. Handle optional input_file_path copy into input/
        input_file_borrowed = None
        if input_file_path:
            clean_inp = input_file_path.replace("/", os.sep).replace("\\", os.sep)
            full_inp = clean_inp if os.path.isabs(clean_inp) else os.path.join(REPO_ROOT, clean_inp)
            if os.path.exists(full_inp) and os.path.isfile(full_inp):
                dest_inp = os.path.join(target_paths["input_dir"], os.path.basename(full_inp))
                try:
                    shutil.copy2(full_inp, dest_inp)
                    borrowed_files.append(f"input/{os.path.basename(full_inp)}")
                    input_file_borrowed = os.path.basename(full_inp)
                except Exception as e:
                    logger.warning(f"Warning copying input file {full_inp}: {e}")

        # 4. Increment times_borrowed & times_referenced in SQLite and index
        self.subskills.increment_reference_sqlite(name)
        subskill.times_borrowed += 1
        subskill.times_referenced += 1
        subskill.updated_at = now_iso
        index_model.subskills[name] = subskill
        self._write_subskills_index(index_model)

        # 5. Log subskill_borrowed event
        if target_session:
            self.log_event(
                tab_group_id=target_session.tab_group_id,
                event_type=SessionEventType.SUBSKILL_BORROWED,
                title=f"Borrowed Subskill: {subskill.name}",
                start_time=time.time(),
                payload={
                    "subskill_name": subskill.name,
                    "vault_path": vault_rel_path,
                    "referenced_adhocs": subskill.adhoc_tools,
                    "borrowed_files": borrowed_files,
                    "input_file": input_file_borrowed,
                },
            )

        # 6. Generate / refresh SESSION_DOCUMENT.md
        self.generate_session_document(target_dir)

        return {
            "status": "success",
            "message": f"Successfully borrowed subskill '{subskill.name}' into session manifest.",
            "subskill_name": subskill.name,
            "display_title": subskill.display_title,
            "vault_path": vault_rel_path,
            "target_session_path": target_paths["session_path"],
            "target_session_dir": target_paths["session_dir"],
            "manifest_path": target_paths["manifest_path"],
            "borrowed_files": borrowed_files,
            "referenced_adhocs": subskill.adhoc_tools,
            "input_dir": target_paths["input_dir"],
            "output_dir": target_paths["output_dir"],
            "adhocs_dir": target_paths["adhocs_dir"],
        }

    # ========================================================================
    # Hierarchical Adhoc Tool Resolution & Execution Pipeline (Spec 18)
    # ========================================================================
    def resolve_adhoc(
        self,
        tool_name: str,
        session_dir_or_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Deterministic 3-tier hierarchical tool resolution pipeline (Spec 18):
        Tier 1: Session Local Override (session/adhocs/<tool_name>)
        Tier 2: Subskill-Specific Vault (server/subskills/<name>/adhocs/<tool_name> for borrowed subskills)
        Tier 3: Universal Shared Vault (server/adhocs/<tool_name> or templates/adhocs/)
        """
        # Tier 1: Local Session Override
        if session_dir_or_path:
            paths = self.get_session_paths(session_dir_or_path)
            session_dir = paths["session_dir"]
            local_path = os.path.join(session_dir, "adhocs", tool_name)
            if os.path.isfile(local_path):
                return {
                    "found": True,
                    "tier": "local",
                    "path": local_path,
                    "tool_name": tool_name,
                    "session_path": paths["session_path"],
                }

            # Tier 2: Subskill-Specific Vault via session_manifest.json
            manifest = self.storage.read_manifest(session_dir)
            if manifest:
                for borrowed in reversed(manifest.borrowed_subskills):
                    v_path = borrowed.vault_path
                    clean_v = v_path.replace("/", os.sep).replace("\\", os.sep)
                    subskill_dir = clean_v if os.path.isabs(clean_v) else os.path.join(REPO_ROOT, clean_v)
                    sub_tool_path = os.path.join(subskill_dir, "adhocs", tool_name)
                    if os.path.isfile(sub_tool_path):
                        return {
                            "found": True,
                            "tier": "subskill",
                            "subskill_name": borrowed.name,
                            "path": sub_tool_path,
                            "tool_name": tool_name,
                            "vault_path": v_path,
                        }

        # Tier 3: Universal Shared Vault (server/adhocs/)
        universal_path = os.path.join(self.adhocs_dir, tool_name)
        if os.path.isfile(universal_path):
            return {
                "found": True,
                "tier": "universal",
                "path": universal_path,
                "tool_name": tool_name,
            }

        # Fallback to TEMPLATES_ADHOCS_DIR if present
        template_path = os.path.join(TEMPLATES_ADHOCS_DIR, tool_name)
        if os.path.isfile(template_path):
            return {
                "found": True,
                "tier": "universal",
                "path": template_path,
                "tool_name": tool_name,
            }

        return {
            "found": False,
            "tier": "none",
            "path": None,
            "tool_name": tool_name,
            "error": f"Tool '{tool_name}' not found across local session, borrowed subskills, and universal vault.",
        }

    def run_adhoc(
        self,
        tool_name: str,
        session_dir_or_path: str | None = None,
        args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Executes an adhoc script resolved via the 3-tier hierarchical resolution pipeline."""
        resolution = self.resolve_adhoc(tool_name, session_dir_or_path)
        if not resolution["found"]:
            return {
                "status": "error",
                "message": resolution.get("error", f"Tool '{tool_name}' not found."),
                "resolution": resolution,
            }

        script_path = resolution["path"]
        cmd = [sys.executable, script_path, *(args or [])]
        env = os.environ.copy()
        if session_dir_or_path:
            paths = self.get_session_paths(session_dir_or_path)
            env["AGENTSOCKET_SESSION_DIR"] = paths["session_dir"]
            env["AGENTSOCKET_SESSION_PATH"] = paths["session_path"]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60.0,
                env=env,
            )
            return {
                "status": "success" if proc.returncode == 0 else "error",
                "tool_name": tool_name,
                "tier": resolution["tier"],
                "path": script_path,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": f"Execution of adhoc tool '{tool_name}' timed out after 60 seconds.",
                "tool_name": tool_name,
                "tier": resolution["tier"],
                "path": script_path,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to execute adhoc tool '{tool_name}': {e}",
                "tool_name": tool_name,
                "tier": resolution["tier"],
                "path": script_path,
            }

    def promote_adhoc(
        self,
        session_path: str,
        tool_name: str,
        target: str = "universal",
        subskill_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Promotes an adhoc tool created or modified inside a session's adhocs/ directory
        to either the universal vault (server/adhocs/) or a subskill vault (server/subskills/<name>/adhocs/).
        Validates Python syntax prior to promotion.
        """
        paths = self.get_session_paths(session_path)
        session_dir = paths["session_dir"]
        src_path = os.path.join(session_dir, "adhocs", tool_name)

        if not os.path.isfile(src_path):
            return {
                "status": "error",
                "message": f"Adhoc script '{tool_name}' does not exist in session '{session_dir}/adhocs/'.",
            }

        # 1. Syntax Validation
        try:
            with open(src_path, "r", encoding="utf-8") as sf:
                code_content = sf.read()
            ast.parse(code_content, filename=tool_name)
        except SyntaxError as se:
            return {
                "status": "error",
                "message": f"Python syntax error in '{tool_name}': {se.msg} (line {se.lineno})",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Validation failed for '{tool_name}': {e}",
            }

        # 2. Determine target destination
        if target == "universal":
            dst_dir = self.adhocs_dir
            dst_path = os.path.join(dst_dir, tool_name)
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(src_path, dst_path)

            # Update session manifest
            manifest = self.storage.read_manifest(session_dir)
            if manifest:
                if tool_name not in manifest.universal_adhocs_referenced:
                    manifest.universal_adhocs_referenced.append(tool_name)
                self.storage.write_manifest(session_dir, manifest)

            return {
                "status": "success",
                "message": f"Promoted '{tool_name}' to universal shared vault.",
                "tool_name": tool_name,
                "target": "universal",
                "vault_path": get_relative_session_path(dst_path),
            }

        elif target == "subskill":
            if not subskill_name:
                return {
                    "status": "error",
                    "message": "Parameter 'subskill_name' is required when target is 'subskill'.",
                }
            index_model = self._read_subskills_index()
            subskill = index_model.subskills.get(subskill_name)
            if not subskill:
                return {
                    "status": "error",
                    "message": f"Subskill '{subskill_name}' does not exist in central catalog.",
                }

            vault_sub_dir = os.path.join(self.subskills_dir, subskill_name, "adhocs")
            os.makedirs(vault_sub_dir, exist_ok=True)
            dst_path = os.path.join(vault_sub_dir, tool_name)
            shutil.copy2(src_path, dst_path)

            # Update subskills index
            if tool_name not in subskill.adhoc_tools:
                subskill.adhoc_tools.append(tool_name)
                subskill.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
                self._write_subskills_index(index_model)

            return {
                "status": "success",
                "message": f"Promoted '{tool_name}' to subskill vault '{subskill_name}'.",
                "tool_name": tool_name,
                "target": "subskill",
                "subskill_name": subskill_name,
                "vault_path": get_relative_session_path(dst_path),
            }

        else:
            return {
                "status": "error",
                "message": f"Invalid target '{target}'. Must be 'universal' or 'subskill'.",
            }

    def list_adhocs(self) -> list[dict[str, Any]]:
        """Lists all universal shared adhoc tools currently in the permanent vault."""
        tools: list[dict[str, Any]] = []
        if os.path.exists(self.adhocs_dir):
            for f_name in sorted(os.listdir(self.adhocs_dir)):
                if f_name.endswith(".py") and f_name != "__init__.py":
                    f_path = os.path.join(self.adhocs_dir, f_name)
                    doc = ""
                    try:
                        with open(f_path, "r", encoding="utf-8") as pf:
                            content = pf.read(1024)
                            m = re.search(r'"""(.*?)"""', content, re.DOTALL) or re.search(r"'''(.*?)'''", content, re.DOTALL)
                            if m:
                                doc = m.group(1).strip().splitlines()[0]
                    except Exception:
                        pass
                    tools.append({
                        "name": f_name,
                        "size": os.path.getsize(f_path),
                        "doc": doc,
                        "path": get_relative_session_path(f_path),
                    })
        return tools


# Singleton global manager instance
session_manager = SessionManager()
