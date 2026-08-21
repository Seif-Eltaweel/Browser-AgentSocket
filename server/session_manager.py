"""
AgentSocket - Server-Side Session Manager & JSONL Logging Engine (Spec 11)
Handles session lifecycle, latency benchmarking, artifact offloading,
atomic index updates, and zero-credential takeover records.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from server.models import (
    SessionStatus,
    SessionEventType,
    SessionEventModel,
    SessionSummaryModel,
    MonthlyIndexModel,
    SubskillModel,
    SubskillsIndexModel,
)

DEFAULT_BASE_LOG_DIR = os.path.join(REPO_ROOT, "server", "logs")
OFFLOAD_STRING_THRESHOLD = 10000  # 10 KB string length
OFFLOAD_ARRAY_THRESHOLD = 50       # > 50 items in list


def sanitize_filename(name: str) -> str:
    """Sanitizes strings for safe cross-platform folder and file naming."""
    clean = re.sub(r"[^\w\-]+", "_", name).strip("_")
    return clean if clean else "session"


def format_session_thread(
    details_or_events: dict | list[dict],
    session_title: Optional[str] = None,
    total_duration_ms: Optional[float] = None,
) -> str:
    """
    Formats a session's events into a tree-structured ASCII timeline thread.

    Format Example:
    🧵 Thread: LinkedIn Scraper | 2026-08-21_08:45:10 (Total Run: 35.0s)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ├── [08:45:10] (T+00.0s) 🚀 SESSION_START   │    --   │ Group: "LinkedIn Scraper"
    ├── [08:45:10] (T+00.0s) 🌐 NAVIGATE        │  210ms  │ https://linkedin.com/feed
    ├── [08:45:12] (T+02.0s) ⚡ EXECUTE_JS      │   45ms  │ Query selector for feed items
    ├── [08:45:15] (T+05.0s) 🔒 SECURITY_ABORT  │    0ms  │ Password field detected (Snapshot saved)
    ├── [08:45:15] (T+05.0s) ✋ HUMAN_TAKEOVER  │  25.0s  │ Operator: "Solved 2FA challenge"
    ├── [08:45:40] (T+30.0s) ▶ HUMAN_RELEASE   │    0ms  │ Resumed automation context
    ├── [08:45:42] (T+32.0s) ⚡ EXECUTE_JS      │  180ms  │ Scraped 25 profile links
    └── [08:45:45] (T+35.0s) ✅ SESSION_END     │    --   │ Status: COMPLETED
    """
    if isinstance(details_or_events, dict):
        events = details_or_events.get("events", [])
        if session_title is None:
            session_title = details_or_events.get("session_title")
        if total_duration_ms is None:
            total_duration_ms = details_or_events.get("duration_ms")
    elif isinstance(details_or_events, list):
        events = details_or_events
    else:
        events = []

    if not events:
        title_str = session_title or "Browser Session"
        return f"🧵 Thread: {title_str} (Total Run: 0.0s)\n" + ("━" * 65) + "\n*No recorded events.*"

    first_evt = events[0]
    first_start = first_evt.get("start_time", time.time())

    if not session_title:
        first_payload = first_evt.get("payload") or {}
        session_title = (
            first_payload.get("session_title")
            or first_evt.get("session_title")
        )
        if not session_title:
            grp = (
                first_payload.get("tab_group_name")
                or first_payload.get("group_name")
                or first_evt.get("title", "").replace("Session Started: ", "").strip()
                or "Browser Session"
            )
            dt_start = datetime.fromtimestamp(first_start)
            session_title = f"{grp} | {dt_start.strftime('%Y-%m-%d_%H:%M:%S')}"

    if total_duration_ms is None:
        last_evt = events[-1]
        last_end = last_evt.get("end_time") or last_evt.get("start_time") or first_start
        total_run_sec = max(0.0, last_end - first_start)
    else:
        total_run_sec = max(0.0, total_duration_ms / 1000.0)

    total_run_str = f"{total_run_sec:.1f}s"
    header = f"🧵 Thread: {session_title} (Total Run: {total_run_str})"
    divider = "━" * 65

    lines = [header, divider]
    num_events = len(events)

    for idx, evt in enumerate(events):
        is_last = (idx == num_events - 1)
        connector = "└── " if is_last else "├── "

        evt_start = evt.get("start_time", first_start)
        evt_end = evt.get("end_time", evt_start)
        dur_ms = evt.get("duration_ms")
        if dur_ms is None and evt_end is not None and evt_start is not None:
            dur_ms = max(0.0, (evt_end - evt_start) * 1000.0)

        dt = datetime.fromtimestamp(evt_start)
        time_str = dt.strftime("%H:%M:%S")

        rel_offset_sec = max(0.0, evt_start - first_start)
        rel_str = f"T+{rel_offset_sec:04.1f}s"

        etype_raw = evt.get("type", "")
        etype = etype_raw.value if hasattr(etype_raw, "value") else str(etype_raw).lower()

        payload = evt.get("payload") or {}
        art = evt.get("artifact_link") or ""
        title = evt.get("title") or ""

        # Map event type to Icon + Formatted Name padded to 18 characters
        if etype == "session_start":
            icon_type = "🚀 SESSION_START"
        elif etype == "navigate":
            icon_type = "🌐 NAVIGATE"
        elif etype == "execute_js":
            icon_type = "⚡ EXECUTE_JS"
        elif etype == "cdp_eval_result":
            icon_type = "⚡ CDP_EVAL_RESULT"
        elif etype == "security_abort":
            icon_type = "🔒 SECURITY_ABORT"
        elif etype == "human_takeover":
            icon_type = "✋ HUMAN_TAKEOVER"
        elif etype == "human_release":
            icon_type = "▶ HUMAN_RELEASE"
        elif etype == "task_complete":
            icon_type = "🎯 TASK_COMPLETE"
        elif etype == "subskill_borrowed":
            icon_type = "📦 SUBSKILL_BORROW"
        elif etype == "subskill_registered":
            icon_type = "🗂️ SUBSKILL_REG"
        elif etype == "error":
            icon_type = "❌ ERROR"
        elif etype == "session_end":
            status_val = str(payload.get("status", "completed")).lower()
            if status_val in ("completed", "success"):
                icon_type = "✅ SESSION_END"
            elif status_val == "aborted":
                icon_type = "🛑 SESSION_END"
            elif status_val == "stopped":
                icon_type = "⏹ SESSION_END"
            else:
                icon_type = "✅ SESSION_END"
        else:
            icon_type = f"🔹 {etype.upper()}"

        icon_type_padded = f"{icon_type:<18}"

        # Format Duration Column
        if etype in ("session_start", "session_end"):
            dur_col = "    --   "
        elif dur_ms is None or dur_ms < 0:
            dur_col = "    --   "
        elif dur_ms < 1000.0:
            ms_val = int(round(dur_ms))
            dur_col = f"  {f'{ms_val}ms':>5}  "
        else:
            s_val = f"{dur_ms / 1000.0:.1f}s"
            dur_col = f"  {s_val:>5}  "

        # Format Details / Summary Column
        details = ""
        if etype == "session_start":
            grp = (
                payload.get("tab_group_name")
                or payload.get("group_name")
                or (session_title.split(" | ")[0] if " | " in session_title else session_title)
            )
            details = f'Group: "{grp}"'
        elif etype == "navigate":
            details = evt.get("url") or payload.get("target_url") or title.replace("Navigate to ", "").strip()
        elif etype in ("execute_js", "cdp_eval_result"):
            if title and not title.startswith("Execute JavaScript (") and not title.startswith("Execute JS"):
                details = title
            elif payload.get("result_preview") and not str(payload["result_preview"]).startswith("{"):
                details = str(payload["result_preview"])
            elif title.startswith("Execute JavaScript ("):
                script_str = title[len("Execute JavaScript ("):-1] if title.endswith(")") else title
                details = script_str
            else:
                details = title or "Execute JavaScript"
        elif etype == "security_abort":
            reason = payload.get("reason", "Sensitive scope detected")
            if reason.startswith("sensitive keywords detected:"):
                keywords = reason.split("sensitive keywords detected:")[1].strip()
                reason = f"{keywords.capitalize()} field detected"
            elif "password" in reason.lower():
                reason = "Password field detected"

            if art or "Snapshot saved" in title:
                details = f"{reason} (Snapshot saved)"
            else:
                details = reason
        elif etype == "human_takeover":
            notes = payload.get("notes")
            reason = payload.get("reason")
            if notes:
                details = f'Operator: "{notes}"'
            elif reason:
                details = f'Operator takeover ({reason})'
            elif title and not title.startswith("Human"):
                details = title
            else:
                details = 'Operator takeover initiated'
        elif etype == "human_release":
            notes = payload.get("notes")
            if notes:
                if notes in ("Released by human operator.", "Released to agent context."):
                    details = "Resumed automation context"
                else:
                    details = f"{notes}"
            else:
                details = "Resumed automation context"
        elif etype == "subskill_borrowed":
            sk_name = payload.get("subskill_name") or title.replace("Borrowed Subskill: ", "").strip()
            src = payload.get("source_session") or ""
            details = f"Borrowed subskill: {sk_name}" + (f" (from {src})" if src else "")
        elif etype == "subskill_registered":
            sk_name = payload.get("subskill_name") or title.replace("Registered Subskill: ", "").strip()
            details = f"Registered subskill: {sk_name}"
        elif etype == "session_end":
            status_str = str(payload.get("status", "COMPLETED")).upper()
            details = f"Status: {status_str}"
        elif etype == "task_complete":
            details = "Status: COMPLETED"
        elif etype == "error":
            msg = payload.get("message") or evt.get("title") or "Unknown error"
            details = f"Error: {msg}"
        else:
            details = title

        line = f"{connector}[{time_str}] ({rel_str}) {icon_type_padded}│{dur_col}│ {details}"
        lines.append(line)

    return "\n".join(lines)


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
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    event_count: int = 0
    action_count: int = 0
    takeover_count: int = 0
    artifacts_count: int = 0
    end_reason: Optional[str] = None
    human_takeover_start_time: Optional[float] = None


class SessionManager:
    def __init__(self, base_log_dir: str = DEFAULT_BASE_LOG_DIR):
        self.base_log_dir = os.path.abspath(base_log_dir)
        self.history_index_dir = os.path.join(self.base_log_dir, "sessions", "history_logs")
        self.index_file = os.path.join(self.history_index_dir, "index.json")
        self.subskills_index_file = os.path.join(self.base_log_dir, "subskills_index.json")
        self.active_sessions: dict[int, ActiveSession] = {}
        # Also map title -> tab_group_id for early lookups
        self.title_to_group_id: dict[str, int] = {}
        self._ensure_directories()

    def _ensure_directories(self):
        os.makedirs(self.history_index_dir, exist_ok=True)
        os.makedirs(self.base_log_dir, exist_ok=True)
        if not os.path.exists(self.index_file):
            self._write_index(MonthlyIndexModel())
        if not os.path.exists(self.subskills_index_file):
            self._write_subskills_index(SubskillsIndexModel())

    def _get_relative_session_path(self, session_dir: str) -> str:
        """Returns relative path formatted with forward slashes starting from server/logs/."""
        try:
            rel = os.path.relpath(session_dir, REPO_ROOT)
            return rel.replace("\\", "/")
        except ValueError:
            return session_dir.replace("\\", "/")

    def get_session_paths(self, session_dir_or_path: str) -> dict:
        """Returns normalized absolute and relative paths for all session subdirectories."""
        full_dir = None
        # 1. Match against active session IDs or titles
        for s in self.active_sessions.values():
            if s.session_id == session_dir_or_path or s.tab_group_name == session_dir_or_path:
                full_dir = s.session_dir
                break

        if not full_dir:
            clean_path = str(session_dir_or_path).replace("/", os.sep).replace("\\", os.sep)
            if os.path.isabs(clean_path):
                full_dir = clean_path
            elif os.path.isdir(os.path.join(self.base_log_dir, clean_path)):
                full_dir = os.path.join(self.base_log_dir, clean_path)
            elif os.path.isdir(os.path.join(REPO_ROOT, clean_path)):
                full_dir = os.path.join(REPO_ROOT, clean_path)
            else:
                # Search base_log_dir for matching folder
                found = None
                if os.path.exists(self.base_log_dir):
                    for root, dirs, _ in os.walk(self.base_log_dir):
                        for d in dirs:
                            if d == clean_path or clean_path in d:
                                found = os.path.join(root, d)
                                break
                        if found:
                            break
                full_dir = found or (os.path.join(self.base_log_dir, clean_path) if not os.path.exists(os.path.join(REPO_ROOT, clean_path)) else os.path.join(REPO_ROOT, clean_path))

        if full_dir and not os.path.isdir(full_dir) and os.path.isfile(full_dir):
            full_dir = os.path.dirname(full_dir)

        return {
            "session_dir": full_dir,
            "session_path": self._get_relative_session_path(full_dir),
            "input_dir": os.path.join(full_dir, "input"),
            "output_dir": os.path.join(full_dir, "output"),
            "adhocs_dir": os.path.join(full_dir, "adhocs"),
            "artifacts_dir": os.path.join(full_dir, "artifacts"),
            "jsonl_path": os.path.join(full_dir, "session.jsonl"),
            "sub_skill_path": os.path.join(full_dir, "sub_skill.md"),
            "session_doc_path": os.path.join(full_dir, "SESSION_DOCUMENT.md"),
        }


    # ========================================================================
    # Index Reading & Atomic Writing
    # ========================================================================
    def _read_index(self) -> MonthlyIndexModel:

        if not os.path.exists(self.index_file):
            return MonthlyIndexModel()
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MonthlyIndexModel.model_validate(data)
        except Exception as e:
            print(f"[SessionManager] Warning: Failed to read index.json: {e}")
            return MonthlyIndexModel()

    def _write_index(self, index_model: MonthlyIndexModel):
        index_model.updated_at = time.time()
        os.makedirs(os.path.dirname(self.index_file), exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.index_file),
            prefix="idx_",
            suffix=".tmp",
            text=True
        )
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(index_model.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.index_file)
        except Exception as e:
            print(f"[SessionManager] Error writing atomic index.json: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _read_subskills_index(self) -> SubskillsIndexModel:
        if not os.path.exists(self.subskills_index_file):
            return SubskillsIndexModel()
        try:
            with open(self.subskills_index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SubskillsIndexModel.model_validate(data)
        except Exception as e:
            print(f"[SessionManager] Warning: Failed to read subskills_index.json: {e}")
            return SubskillsIndexModel()

    def _write_subskills_index(self, index_model: SubskillsIndexModel):
        index_model.updated_at = time.time()
        os.makedirs(os.path.dirname(self.subskills_index_file), exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.subskills_index_file),
            prefix="subsk_",
            suffix=".tmp",
            text=True
        )
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(index_model.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.subskills_index_file)
        except Exception as e:
            print(f"[SessionManager] Error writing atomic subskills_index.json: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _update_index_for_session(self, session: ActiveSession):
        """Upserts a session's summary in the monthly master index."""
        index_model = self._read_index()
        dt = datetime.fromtimestamp(session.start_time)
        month_key = dt.strftime("%Y-%m")

        summary = SessionSummaryModel(
            session_id=session.session_id,
            session_title=session.session_title,
            tab_group_id=session.tab_group_id,
            tab_group_name=session.tab_group_name,
            agent_name=session.agent_name,
            group_color=session.group_color,
            status=session.status,
            start_time=session.start_time,
            end_time=session.end_time,
            duration_ms=session.duration_ms,
            event_count=session.event_count,
            action_count=session.action_count,
            takeover_count=session.takeover_count,
            session_path=session.session_path,
            artifacts_count=session.artifacts_count,
            end_reason=session.end_reason,
        )

        if month_key not in index_model.months:
            index_model.months[month_key] = []

        existing_list = index_model.months[month_key]
        idx = next((i for i, s in enumerate(existing_list) if s.session_id == session.session_id), None)
        if idx is not None:
            existing_list[idx] = summary
        else:
            existing_list.append(summary)

        self._write_index(index_model)

    # ========================================================================
    # Session Creation & Retrieval
    # ========================================================================
    def get_or_create_session(
        self,
        tab_group_id: int,
        tab_group_name: str = "AgentSocket Task",
        group_color: str = "purple",
        agent_name: str = "AgentSocket Local",
    ) -> ActiveSession:
        """Retrieves existing active session by tab_group_id or initializes a new date-partitioned session with isolated folders."""
        if tab_group_id in self.active_sessions:
            session = self.active_sessions[tab_group_id]
            session.last_action_time = time.time()
            return session

        now = time.time()
        dt = datetime.fromtimestamp(now)
        date_str = dt.strftime("%Y-%m-%d")
        time_str_dir = dt.strftime("%H-%M-%S")
        time_str_id = dt.strftime("%H%M%S")
        date_str_id = dt.strftime("%Y%m%d")

        sanitized_title = sanitize_filename(tab_group_name)
        session_id = f"sess_{date_str_id}_{time_str_id}_{tab_group_id}"
        session_title = f"{tab_group_name} | {dt.strftime('%Y-%m-%d_%H:%M:%S')}"
        folder_name = f"{sanitized_title}_{time_str_dir}_gid{tab_group_id}"

        session_dir = os.path.join(self.base_log_dir, date_str, folder_name)
        artifacts_dir = os.path.join(session_dir, "artifacts")
        adhocs_dir = os.path.join(session_dir, "adhocs")
        input_dir = os.path.join(session_dir, "input")
        output_dir = os.path.join(session_dir, "output")
        jsonl_path = os.path.join(session_dir, "session.jsonl")

        os.makedirs(artifacts_dir, exist_ok=True)
        os.makedirs(adhocs_dir, exist_ok=True)
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

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
            }
        )

        self._update_index_for_session(session)
        self.generate_session_document(session_dir)
        return session

    def get_active_session_by_group_id(self, tab_group_id: int) -> Optional[ActiveSession]:
        return self.active_sessions.get(tab_group_id)

    def get_active_session_by_title(self, session_title: str) -> Optional[ActiveSession]:
        if session_title in self.title_to_group_id:
            gid = self.title_to_group_id[session_title]
            return self.active_sessions.get(gid)
        for session in self.active_sessions.values():
            if session.tab_group_name == session_title or session_title in session.session_title:
                return session
        return None

    # ========================================================================
    # Event Logging & Threshold Offloading
    # ========================================================================
    def log_event(
        self,
        tab_group_id: int,
        event_type: SessionEventType,
        title: str,
        start_time: float,
        end_time: Optional[float] = None,
        tab_id: Optional[int] = None,
        tab_group_id_val: Optional[int] = None,
        url: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        screenshot_bytes: Optional[bytes] = None,
    ) -> Optional[SessionEventModel]:
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
        processed_payload = payload.copy() if payload else {}

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
                print(f"[SessionManager] Error saving screenshot artifact: {e}")

        # 2. Check Explicit Threshold (10 KB or >50 array items) for Offloading
        if processed_payload:
            should_offload = False
            offload_reason = ""
            payload_str = json.dumps(processed_payload)

            if len(payload_str) > OFFLOAD_STRING_THRESHOLD:
                should_offload = True
                offload_reason = f"Payload size {len(payload_str)} exceeds 10KB threshold"

            # Check array counts in result or data
            result_val = processed_payload.get("result") or processed_payload.get("output")
            if isinstance(result_val, list) and len(result_val) > OFFLOAD_ARRAY_THRESHOLD:
                should_offload = True
                offload_reason = f"Array length {len(result_val)} exceeds 50-item threshold"

            if should_offload:
                action_name = event_type.value
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
                        "offload_reason": offload_reason
                    }
                    if "script" in payload:
                        script_val = str(payload["script"])
                        processed_payload["script_preview"] = script_val[:300] + "..." if len(script_val) > 300 else script_val
                except Exception as e:
                    print(f"[SessionManager] Error offloading artifact payload: {e}")

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

        # Atomic append to session.jsonl
        try:
            with open(session.jsonl_path, "a", encoding="utf-8") as f:
                f.write(event.model_dump_json() + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        except Exception as e:
            print(f"[SessionManager] Error writing to session.jsonl: {e}")

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
        tab_group_id: Union[int, str],
        status: SessionStatus = SessionStatus.COMPLETED,
        end_reason: Optional[str] = None
    ) -> Optional[ActiveSession]:
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
            }
        )


        self._update_index_for_session(session)
        self.active_sessions.pop(tab_group_id, None)
        self.title_to_group_id.pop(session.tab_group_name, None)
        self.generate_session_document(session.session_dir)
        return session


    def check_inactivity(self, inactivity_threshold_seconds: float = 300.0) -> list[int]:
        """Checks for sessions exceeding the inactivity threshold (default 5min) and auto-closes them."""
        now = time.time()
        timed_out_gids = []

        for gid, session in list(self.active_sessions.items()):
            if (now - session.last_action_time) >= inactivity_threshold_seconds:
                print(f"[SessionManager] Session {session.session_id} (group {gid}) timed out after {inactivity_threshold_seconds}s of inactivity.")
                self.finalize_session(
                    tab_group_id=gid,
                    status=SessionStatus.STOPPED,
                    end_reason="inactivity_timeout"
                )
                timed_out_gids.append(gid)

        return timed_out_gids

    def handle_disconnect(self) -> list[int]:
        """Handles abrupt WebSocket/CDP disconnects by aborting all active sessions."""
        aborted_gids = []
        for gid, session in list(self.active_sessions.items()):
            print(f"[SessionManager] Abrupt browser disconnect detected. Aborting active session {session.session_id}.")
            self.finalize_session(
                tab_group_id=gid,
                status=SessionStatus.ABORTED,
                end_reason="browser_disconnected"
            )
            aborted_gids.append(gid)
        return aborted_gids

    # ========================================================================
    # Two-Step MCP & CLI Query / Introspection Methods
    # ========================================================================
    def query_history(
        self,
        query_hint: str = "",
        month: Optional[str] = None,
        limit: int = 10
    ) -> list[dict]:
        """
        Step 1: Scans index.json for matching session titles, tab groups, status, or date keywords.
        Returns lightweight summaries sorted newest first.
        """
        index_model = self._read_index()
        results: list[SessionSummaryModel] = []

        target_months = [month] if month and month in index_model.months else list(index_model.months.keys())
        query_hint_lower = query_hint.lower().strip()

        for m in target_months:
            summaries = index_model.months.get(m, [])
            for s in summaries:
                if not query_hint_lower:
                    results.append(s)
                else:
                    searchable = f"{s.session_id} {s.session_title} {s.tab_group_name} {s.status} {s.agent_name} {s.session_path} {s.end_reason or ''}".lower()
                    if query_hint_lower in searchable:
                        results.append(s)

        # Sort newest first
        results.sort(key=lambda s: s.start_time, reverse=True)
        return [s.model_dump() for s in results[:limit]]

    def format_session_thread(
        self,
        details_or_events: dict | list[dict],
        session_title: Optional[str] = None,
        total_duration_ms: Optional[float] = None
    ) -> str:
        """Formats chronological events into a tree-structured ASCII timeline thread."""
        return format_session_thread(
            details_or_events=details_or_events,
            session_title=session_title,
            total_duration_ms=total_duration_ms
        )

    def get_session_details(self, session_path: str) -> dict:
        """
        Step 2: Reads and parses session.jsonl from session_path.
        Reconstructs full chronological thread for agent drill-down analysis.
        """
        clean_path = session_path.replace("/", os.sep).replace("\\", os.sep)
        full_dir = clean_path if os.path.isabs(clean_path) else os.path.join(REPO_ROOT, clean_path)

        jsonl_path = os.path.join(full_dir, "session.jsonl") if os.path.isdir(full_dir) else full_dir

        if not os.path.exists(jsonl_path):
            return {
                "status": "error",
                "message": f"Session log file not found at: {jsonl_path}",
                "session_path": session_path,
                "events": [],
                "formatted_thread": "*Session log file not found.*"
            }

        events = []
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to read session log: {e}",
                "session_path": session_path,
                "events": [],
                "formatted_thread": f"*Failed to read session log: {e}*"
            }

        formatted_thread = format_session_thread(events)

        return {
            "status": "success",
            "session_path": self._get_relative_session_path(os.path.dirname(jsonl_path)),
            "event_count": len(events),
            "events": events,
            "formatted_thread": formatted_thread,
        }

    def get_session_artifact(self, session_path: str, artifact_name: str) -> dict | str:
        """
        Reads a specific offloaded heavy payload JSON or returns the file path for images.
        """
        clean_path = session_path.replace("/", os.sep).replace("\\", os.sep)
        full_dir = clean_path if os.path.isabs(clean_path) else os.path.join(REPO_ROOT, clean_path)

        if not os.path.isdir(full_dir):
            full_dir = os.path.dirname(full_dir)

        # Artifact might be passed as "artifacts/eval_result_evt_02.json" or "eval_result_evt_02.json"
        clean_art = artifact_name.replace("/", os.sep).replace("\\", os.sep)
        if clean_art.startswith("artifacts" + os.sep):
            clean_art = clean_art[len("artifacts" + os.sep):]

        artifact_file = os.path.join(full_dir, "artifacts", clean_art)
        if not os.path.exists(artifact_file):
            # Try directly in full_dir
            artifact_file = os.path.join(full_dir, clean_art)

        if not os.path.exists(artifact_file):
            return {
                "status": "error",
                "message": f"Artifact file not found: {artifact_name}",
                "resolved_path": artifact_file
            }

        if artifact_file.endswith(".json"):
            try:
                with open(artifact_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                return {"status": "error", "message": f"Failed to parse JSON artifact: {e}"}
        else:
            return artifact_file

    def generate_session_document(self, session_dir_or_path: str) -> str:
        """
        Constructs and writes a consolidated master Markdown document (SESSION_DOCUMENT.md & README.md)
        for a session containing executive summary, subskill playbook info, input/output inventories,
        adhoc tools, artifacts, and chronological execution timeline thread.
        """
        paths = self.get_session_paths(session_dir_or_path)
        session_dir = paths["session_dir"]
        session_path = paths["session_path"]
        input_dir = paths["input_dir"]
        output_dir = paths["output_dir"]
        adhocs_dir = paths["adhocs_dir"]
        artifacts_dir = paths["artifacts_dir"]
        jsonl_path = paths["jsonl_path"]
        sub_skill_path = paths["sub_skill_path"]

        # Ensure all folders exist
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(adhocs_dir, exist_ok=True)
        os.makedirs(artifacts_dir, exist_ok=True)

        # 1. Read Events & Metadata from session.jsonl
        events = []
        if os.path.exists(jsonl_path):
            try:
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except Exception:
                                pass
            except Exception as e:
                print(f"[SessionManager] Warning reading jsonl for doc generation: {e}")

        # Derive metadata
        first_evt = events[0] if events else {}
        first_payload = first_evt.get("payload") or {}
        session_id = first_payload.get("session_id") or first_evt.get("session_id") or os.path.basename(session_dir)
        session_title = first_payload.get("session_title") or first_evt.get("session_title") or os.path.basename(session_dir)
        tab_group_name = first_payload.get("tab_group_name") or first_payload.get("group_name") or session_title.split(" | ")[0]
        group_color = first_payload.get("group_color", "purple")
        agent_name = first_payload.get("agent_name", "AgentSocket Local")
        start_time = first_evt.get("start_time") or time.time()
        start_dt_str = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")

        status_str = "ACTIVE"
        end_reason = "In Progress"
        total_duration_ms = 0.0

        for evt in reversed(events):
            if evt.get("type") in ("session_end", "SessionEventType.SESSION_END"):
                p = evt.get("payload") or {}
                status_str = str(p.get("status", "COMPLETED")).upper()
                end_reason = str(p.get("end_reason", "task_complete"))
                total_duration_ms = p.get("total_duration_ms", 0.0)
                break

        if not total_duration_ms and events:
            last_time = events[-1].get("end_time") or events[-1].get("start_time") or start_time
            total_duration_ms = max(0.0, (last_time - start_time) * 1000.0)

        dur_str = f"{total_duration_ms / 1000.0:.1f}s"

        lines = [
            f"# 📜 Session Document: `{tab_group_name}`",
            f"\n> **Session ID:** `{session_id}`  ",
            f"> **Status:** `{status_str}` ({end_reason})  ",
            f"> **Start Time:** `{start_dt_str}`  ",
            f"> **Duration:** `{dur_str}`  ",
            f"> **Tab Group Accent:** `{group_color}` | **Agent:** `{agent_name}`  ",
            f"> **Session Directory:** `{session_path}`\n",
            "---",
        ]

        # 2. Subskill Playbook Contract
        lines.append("## 📖 Subskill Playbook Contract (`sub_skill.md`)")
        if os.path.exists(sub_skill_path):
            try:
                with open(sub_skill_path, "r", encoding="utf-8") as sf:
                    sub_content = sf.read().strip()
                sub_lines = sub_content.splitlines()
                preview_sub = "\n".join(sub_lines[:25])
                if len(sub_lines) > 25:
                    preview_sub += f"\n\n*(... {len(sub_lines) - 25} more lines in [sub_skill.md](sub_skill.md))*"
                lines.append(f"Playbook file: [`sub_skill.md`](sub_skill.md)\n")
                lines.append("```markdown")
                lines.append(preview_sub)
                lines.append("```\n")
            except Exception as e:
                lines.append(f"*Error reading sub_skill.md: {e}*\n")
        else:
            lines.append("*No dedicated `sub_skill.md` playbook attached to this session yet.*\n")

        # 3. Input Data Inventory
        lines.append("## 📥 Input Data Inventory (`input/`)")
        if os.path.exists(input_dir) and os.listdir(input_dir):
            input_files = sorted(os.listdir(input_dir))
            lines.append("| File Name | Size (Bytes) | Description / Notes |")
            lines.append("|:---|:---:|:---|")
            for f_name in input_files:
                f_path = os.path.join(input_dir, f_name)
                f_size = os.path.getsize(f_path) if os.path.isfile(f_path) else "-"
                row_info = ""
                if f_name.endswith(".csv") and os.path.isfile(f_path):
                    try:
                        with open(f_path, "r", encoding="utf-8", errors="replace") as cf:
                            num_rows = sum(1 for _ in cf) - 1
                            row_info = f"CSV dataset (~{max(0, num_rows)} records)"
                    except Exception:
                        pass
                lines.append(f"| [`{f_name}`](input/{f_name}) | `{f_size}` | {row_info or 'Input data file'} |")
            lines.append("")
        else:
            lines.append("*No input files loaded in `input/` folder.*\n")

        # 4. Output Deliverables Inventory
        lines.append("## 📤 Output Deliverables (`output/`)")
        if os.path.exists(output_dir) and os.listdir(output_dir):
            output_files = sorted(os.listdir(output_dir))
            lines.append("| File Name | Size (Bytes) | Deliverable Summary |")
            lines.append("|:---|:---:|:---|")
            for f_name in output_files:
                f_path = os.path.join(output_dir, f_name)
                f_size = os.path.getsize(f_path) if os.path.isfile(f_path) else "-"
                row_info = ""
                if f_name.endswith(".csv") and os.path.isfile(f_path):
                    try:
                        with open(f_path, "r", encoding="utf-8", errors="replace") as cf:
                            num_rows = sum(1 for _ in cf) - 1
                            row_info = f"Enriched CSV output ({max(0, num_rows)} records)"
                    except Exception:
                        pass
                lines.append(f"| [`{f_name}`](output/{f_name}) | `{f_size}` | {row_info or 'Generated output deliverable'} |")
            lines.append("")
        else:
            lines.append("*No output files written to `output/` folder yet.*\n")

        # 5. Adhoc Tools & Diagnostic Probes
        lines.append("## 🛠️ Adhoc Tools & Diagnostic Scripts (`adhocs/`)")
        if os.path.exists(adhocs_dir) and os.listdir(adhocs_dir):
            adhoc_files = sorted(os.listdir(adhocs_dir))
            lines.append("| Script / Probe | Size | Purpose / Docstring |")
            lines.append("|:---|:---:|:---|")
            for f_name in adhoc_files:
                f_path = os.path.join(adhocs_dir, f_name)
                f_size = os.path.getsize(f_path) if os.path.isfile(f_path) else "-"
                doc_summary = ""
                if f_name.endswith(".py") and os.path.isfile(f_path):
                    try:
                        with open(f_path, "r", encoding="utf-8", errors="replace") as pf:
                            content = pf.read(1024)
                            m_doc = re.search(r'"""(.*?)"""', content, re.DOTALL) or re.search(r"'''(.*?)'''", content, re.DOTALL)
                            if m_doc:
                                doc_summary = m_doc.group(1).strip().splitlines()[0]
                    except Exception:
                        pass
                lines.append(f"| [`{f_name}`](adhocs/{f_name}) | `{f_size}` | {doc_summary or 'Diagnostic / probe helper script'} |")
            lines.append("")
        else:
            lines.append("*No custom adhoc scripts saved in `adhocs/` folder.*\n")

        # 6. Artifacts & Visual Snapshots
        lines.append("## 🖼️ Artifacts & Visual Snapshots (`artifacts/`)")
        if os.path.exists(artifacts_dir) and os.listdir(artifacts_dir):
            art_files = sorted(os.listdir(artifacts_dir))
            lines.append("| Artifact File | Type | Link |")
            lines.append("|:---|:---:|:---|")
            for f_name in art_files:
                f_type = "Screenshot Image" if f_name.endswith(".png") else ("JSON Payload" if f_name.endswith(".json") else "File")
                lines.append(f"| `{f_name}` | {f_type} | [`artifacts/{f_name}`](artifacts/{f_name}) |")
            lines.append("")
        else:
            lines.append("*No heavy payload offloads or screenshots recorded in `artifacts/`.*\n")

        # 7. Chronological Execution Timeline
        lines.append("## 🧵 Chronological Execution Timeline Thread")
        formatted_thread = format_session_thread(events, session_title=session_title, total_duration_ms=total_duration_ms)
        lines.append("```text")
        lines.append(formatted_thread)
        lines.append("```\n")

        doc_content = "\n".join(lines) + "\n"

        # Write to SESSION_DOCUMENT.md
        try:
            doc_file = os.path.join(session_dir, "SESSION_DOCUMENT.md")
            with open(doc_file, "w", encoding="utf-8") as df:
                df.write(doc_content)
        except Exception as e:
            print(f"[SessionManager] Warning writing session document: {e}")

        return doc_content


    # ========================================================================
    # Subskills & Borrowing Engine Registry (Spec 13)
    # ========================================================================
    def list_subskills(
        self,
        query: str = "",
        tags: Optional[list[str]] = None
    ) -> list[dict]:
        """
        Lists registered subskills from subskills_index.json matching search query or tags.
        """
        index_model = self._read_subskills_index()
        query_lower = query.lower().strip()
        results: list[SubskillModel] = []

        for subskill in index_model.subskills.values():
            if query_lower:
                searchable = f"{subskill.name} {subskill.display_title} {subskill.description} {' '.join(subskill.tags)}".lower()
                if query_lower not in searchable:
                    continue

            if tags:
                sub_tags_lower = [t.lower() for t in subskill.tags]
                req_tags_lower = [t.lower() for t in tags]
                if not any(t in sub_tags_lower for t in req_tags_lower):
                    continue

            results.append(subskill)

        # Sort by most borrowed first, then alphabetically
        results.sort(key=lambda s: (s.times_borrowed, s.name), reverse=True)
        return [s.model_dump() for s in results]

    def get_subskill(self, name: str) -> Optional[dict]:
        """
        Retrieves a subskill by slug name, including metadata, playbook markdown content, and adhoc tools.
        """
        index_model = self._read_subskills_index()
        subskill = index_model.subskills.get(name)
        if not subskill:
            return None

        # Resolve playbook path
        sess_dir = subskill.latest_session_path.replace("/", os.sep).replace("\\", os.sep)
        full_dir = sess_dir if os.path.isabs(sess_dir) else os.path.join(REPO_ROOT, sess_dir)
        sub_file = os.path.join(full_dir, subskill.subskill_file)

        playbook_markdown = ""
        if os.path.exists(sub_file):
            try:
                with open(sub_file, "r", encoding="utf-8") as sf:
                    playbook_markdown = sf.read()
            except Exception as e:
                playbook_markdown = f"*Failed to read playbook: {e}*"

        # Check existing adhoc tools in directory
        adhocs_dir = os.path.join(full_dir, "adhocs")
        adhoc_files = []
        if os.path.exists(adhocs_dir):
            adhoc_files = [f for f in os.listdir(adhocs_dir) if os.path.isfile(os.path.join(adhocs_dir, f))]

        res = subskill.model_dump()
        res["playbook_markdown"] = playbook_markdown
        res["available_adhoc_tools"] = adhoc_files or subskill.adhoc_tools
        return res

    def register_subskill(
        self,
        session_path: str,
        name: str,
        display_title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        adhoc_tools: Optional[list[str]] = None,
        subskill_markdown: Optional[str] = None,
    ) -> dict:
        """
        Registers or updates a session as a reusable subskill in subskills_index.json.
        Ensures sub_skill.md and adhocs/ are validated and structured.
        """
        paths = self.get_session_paths(session_path)
        session_dir = paths["session_dir"]
        rel_session_path = paths["session_path"]
        sub_skill_file = paths["sub_skill_path"]
        adhocs_dir = paths["adhocs_dir"]

        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(adhocs_dir, exist_ok=True)

        # 1. Write or Read sub_skill.md
        if subskill_markdown:
            with open(sub_skill_file, "w", encoding="utf-8") as sf:
                sf.write(subskill_markdown)
        elif not os.path.exists(sub_skill_file):
            # Scaffold standard sub_skill.md
            scaffold = f"""---
name: {name}
description: "{description or f'Automated subskill playbook for {name}'}"
version: "1.0"
platform: "web"
rate_limit_pause_range: [3.0, 6.0]
---

# {display_title or name.replace('-', ' ').title()} Playbook

## 1. Tested Navigation Routes
* Target URL: `https://example.com/`

## 2. Verified DOM Selectors & Extraction Rules
* Main content: `main`
* Data extraction rules here.

## 3. Data Schema & Contracts
| Column | Type | Description |
|---|---|---|
| `id` | String | Unique identifier |
"""
            with open(sub_skill_file, "w", encoding="utf-8") as sf:
                sf.write(scaffold)

        # 2. Extract frontmatter if missing metadata
        if not display_title or not description or not tags:
            try:
                with open(sub_skill_file, "r", encoding="utf-8") as sf:
                    txt = sf.read()
                if txt.startswith("---"):
                    parts = txt.split("---", 2)
                    if len(parts) >= 3:
                        fm = parts[1]
                        for line in fm.splitlines():
                            line = line.strip()
                            if line.startswith("name:") and not name:
                                name = line.split("name:", 1)[1].strip().strip('"\'')
                            elif line.startswith("description:") and not description:
                                description = line.split("description:", 1)[1].strip().strip('"\'')
            except Exception:
                pass

        name = sanitize_filename(name).lower().replace("_", "-")
        display_title = display_title or name.replace("-", " ").title()
        description = description or f"Automated subskill recipe for {display_title}."
        if tags is None:
            tags = [t.strip().lower() for t in re.split(r"[-_\s]+", name) if t.strip()]

        # 3. Gather adhoc tools
        found_tools = []
        if os.path.exists(adhocs_dir):
            found_tools = [f for f in os.listdir(adhocs_dir) if os.path.isfile(os.path.join(adhocs_dir, f))]
        tools_list = adhoc_tools if adhoc_tools is not None else found_tools

        # 4. Determine session ID
        session_id = f"sess_{name}_{int(time.time())}"
        if os.path.exists(paths["jsonl_path"]):
            try:
                with open(paths["jsonl_path"], "r", encoding="utf-8") as f:
                    first_l = f.readline().strip()
                    if first_l:
                        data = json.loads(first_l)
                        session_id = data.get("session_id") or data.get("payload", {}).get("session_id") or session_id
            except Exception:
                pass

        # 5. Atomic Update in subskills_index.json
        index_model = self._read_subskills_index()
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        existing = index_model.subskills.get(name)
        created_at = existing.created_at if existing else now_iso
        times_borrowed = existing.times_borrowed if existing else 0

        subskill = SubskillModel(
            name=name,
            display_title=display_title,
            description=description,
            tags=tags,
            latest_session_id=session_id,
            latest_session_path=rel_session_path,
            subskill_file="sub_skill.md",
            adhoc_tools=tools_list,
            times_borrowed=times_borrowed,
            success_rate=1.0,
            created_at=created_at,
            updated_at=now_iso,
        )

        index_model.subskills[name] = subskill
        self._write_subskills_index(index_model)

        # 6. Log event & regenerate document
        for gid, sess in self.active_sessions.items():
            if sess.session_path == rel_session_path or sess.session_dir == session_dir:
                self.log_event(
                    tab_group_id=gid,
                    event_type=SessionEventType.SUBSKILL_REGISTERED,
                    title=f"Registered Subskill: {name}",
                    start_time=time.time(),
                    payload={
                        "subskill_name": name,
                        "display_title": display_title,
                        "tags": tags,
                        "adhoc_tools": tools_list,
                    }
                )
                break

        self.generate_session_document(session_dir)

        return {
            "status": "success",
            "message": f"Subskill '{name}' registered successfully.",
            "subskill": subskill.model_dump(),
        }

    def borrow_subskill(
        self,
        name: str,
        target_session_id_or_title_or_path: Optional[str] = None,
        tab_group_id: Optional[int] = None,
        input_file_path: Optional[str] = None,
    ) -> dict:
        """
        Borrows a subskill by copying its playbook (sub_skill.md) and adhoc tools (adhocs/)
        into the active session workspace, initializing input/ and output/ subfolders,
        incrementing times_borrowed, and logging a subskill_borrowed event.
        """
        index_model = self._read_subskills_index()
        subskill = index_model.subskills.get(name)
        if not subskill:
            return {
                "status": "error",
                "message": f"Subskill '{name}' was not found in central registry.",
            }

        # Resolve Source Directory
        src_sess_path = subskill.latest_session_path.replace("/", os.sep).replace("\\", os.sep)
        src_dir = src_sess_path if os.path.isabs(src_sess_path) else os.path.join(REPO_ROOT, src_sess_path)

        # Resolve Target Session
        target_session: Optional[ActiveSession] = None
        target_dir: str = ""
        gid: int = 1

        if tab_group_id and tab_group_id in self.active_sessions:
            target_session = self.active_sessions[tab_group_id]
            target_dir = target_session.session_dir
            gid = tab_group_id
        elif target_session_id_or_title_or_path:
            # Check if matching active session by title
            target_session = self.get_active_session_by_title(target_session_id_or_title_or_path)
            if target_session:
                target_dir = target_session.session_dir
                gid = target_session.tab_group_id
            elif "/" in target_session_id_or_title_or_path or "\\" in target_session_id_or_title_or_path:
                clean_target = target_session_id_or_title_or_path.replace("/", os.sep).replace("\\", os.sep)
                target_dir = clean_target if os.path.isabs(clean_target) else os.path.join(REPO_ROOT, clean_target)
                os.makedirs(target_dir, exist_ok=True)
            else:
                # Create new session with title
                gid = (int(time.time() * 1000) % 90000) + 1000
                target_session = self.get_or_create_session(
                    tab_group_id=gid,
                    tab_group_name=target_session_id_or_title_or_path
                )
                target_dir = target_session.session_dir
        else:
            # Create standard active session
            gid = (int(time.time() * 1000) % 90000) + 1000
            target_session = self.get_or_create_session(
                tab_group_id=gid,
                tab_group_name=f"Task: {subskill.display_title}"
            )
            target_dir = target_session.session_dir

        target_paths = self.get_session_paths(target_dir)
        os.makedirs(target_paths["input_dir"], exist_ok=True)
        os.makedirs(target_paths["output_dir"], exist_ok=True)
        os.makedirs(target_paths["adhocs_dir"], exist_ok=True)
        os.makedirs(target_paths["artifacts_dir"], exist_ok=True)

        borrowed_files = []

        # 1. Copy sub_skill.md
        src_subskill = os.path.join(src_dir, subskill.subskill_file)
        dst_subskill = os.path.join(target_dir, "sub_skill.md")
        if os.path.exists(src_subskill):
            try:
                shutil.copy2(src_subskill, dst_subskill)
                borrowed_files.append("sub_skill.md")
            except Exception as e:
                print(f"[SessionManager] Warning copying sub_skill.md: {e}")

        # 2. Copy adhocs/ tools
        src_adhocs = os.path.join(src_dir, "adhocs")
        dst_adhocs = target_paths["adhocs_dir"]
        if os.path.exists(src_adhocs):
            for item in os.listdir(src_adhocs):
                s_item = os.path.join(src_adhocs, item)
                d_item = os.path.join(dst_adhocs, item)
                try:
                    if os.path.isfile(s_item):
                        shutil.copy2(s_item, d_item)
                        borrowed_files.append(f"adhocs/{item}")
                    elif os.path.isdir(s_item):
                        if os.path.exists(d_item):
                            shutil.rmtree(d_item)
                        shutil.copytree(s_item, d_item)
                        borrowed_files.append(f"adhocs/{item}/")
                except Exception as e:
                    print(f"[SessionManager] Warning copying adhoc item {item}: {e}")

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
                    print(f"[SessionManager] Warning copying input file {full_inp}: {e}")

        # 4. Increment times_borrowed & update index
        subskill.times_borrowed += 1
        subskill.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
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
                    "source_session": subskill.latest_session_path,
                    "borrowed_files": borrowed_files,
                    "input_file": input_file_borrowed,
                }
            )

        # 6. Generate / refresh SESSION_DOCUMENT.md
        self.generate_session_document(target_dir)

        return {
            "status": "success",
            "message": f"Successfully borrowed subskill '{subskill.name}' into session.",
            "subskill_name": subskill.name,
            "display_title": subskill.display_title,
            "target_session_path": target_paths["session_path"],
            "target_session_dir": target_paths["session_dir"],
            "borrowed_files": borrowed_files,
            "input_dir": target_paths["input_dir"],
            "output_dir": target_paths["output_dir"],
            "adhocs_dir": target_paths["adhocs_dir"],
        }


    def export_all_to_markdown(
        self,
        month: Optional[str] = None,
        output_path: Optional[str] = None
    ) -> str:
        """
        Exports master timeline across past sessions to a formatted Markdown report.
        """
        index_model = self._read_index()
        months_to_export = [month] if month and month in index_model.months else sorted(index_model.months.keys(), reverse=True)

        lines = [
            "# 📜 AgentSocket Session History & Execution Timeline Master Report",
            f"\n*Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n",
            "---",
        ]

        total_sessions = 0
        total_actions = 0
        total_takeovers = 0
        total_artifacts = 0

        # Summary statistics calculation
        for m in months_to_export:
            for s in index_model.months.get(m, []):
                total_sessions += 1
                total_actions += s.action_count
                total_takeovers += s.takeover_count
                total_artifacts += s.artifacts_count

        lines.append("## 📊 Master Overview Metrics")
        lines.append(f"- **Total Recorded Sessions**: `{total_sessions}`")
        lines.append(f"- **Total Executed Actions**: `{total_actions}`")
        lines.append(f"- **Human Takeover Interventions**: `{total_takeovers}`")
        lines.append(f"- **Stored Artifacts**: `{total_artifacts}`\n")

        lines.append("## 📅 Past Sessions Table\n")
        lines.append("| Session ID | Title | Status | Duration (s) | Actions | Takeovers | Artifacts | Log Path |")
        lines.append("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|")

        for m in months_to_export:
            summaries = index_model.months.get(m, [])
            for s in sorted(summaries, key=lambda x: x.start_time, reverse=True):
                dur_s = f"{s.duration_ms / 1000.0:.1f}s" if s.duration_ms else "N/A"
                status_icon = "🟢" if s.status == SessionStatus.COMPLETED else ("🟡" if s.status == SessionStatus.ACTIVE else "🔴")
                lines.append(f"| `{s.session_id}` | **{s.tab_group_name}** | {status_icon} {s.status.value} | {dur_s} | {s.action_count} | {s.takeover_count} | {s.artifacts_count} | `{s.session_path}` |")

        lines.append("\n---\n")
        lines.append("## 🔍 Detailed Chronological Event Timelines\n")

        for m in months_to_export:
            summaries = index_model.months.get(m, [])
            for s in sorted(summaries, key=lambda x: x.start_time, reverse=True):
                lines.append(f"### 🗂️ `{s.session_title}`")
                lines.append(f"- **Session ID**: `{s.session_id}`")
                lines.append(f"- **Tab Group ID**: `{s.tab_group_id}` ({s.group_color})")
                lines.append(f"- **Status**: `{s.status.value}` (Reason: `{s.end_reason or 'N/A'}`)")
                lines.append(f"- **Session Directory**: `{s.session_path}`\n")

                details = self.get_session_details(s.session_path)
                events = details.get("events", [])
                formatted_thread = details.get("formatted_thread")
                if formatted_thread:
                    lines.append("```text")
                    lines.append(formatted_thread)
                    lines.append("```\n")

                if not events:
                    lines.append("*No individual event records found.* \n")
                else:
                    lines.append("| Event ID | Type | Step Duration | Summary / Target | Artifact |")
                    lines.append("|:---|:---|:---:|:---|:---|")
                    for evt in events:
                        eid = evt.get("event_id", "")
                        etype = evt.get("type", "")
                        dur = f"{evt.get('duration_ms', 0):.1f}ms"
                        title = evt.get("title", "")
                        payload = evt.get("payload") or {}
                        art = evt.get("artifact_link") or "-"
                        if art != "-":
                            art = f"[`{art}`]({art})"

                        details_summary = title
                        if "target_url" in payload:
                            details_summary += f" -> `{payload['target_url']}`"
                        elif "result_preview" in payload:
                            details_summary += f" (Output: {payload['result_preview']})"
                        elif "notes" in payload:
                            details_summary += f" (Operator notes: *{payload['notes']}*)"

                        lines.append(f"| `{eid}` | `{etype}` | `{dur}` | {details_summary} | {art} |")
                lines.append("\n")

        md_content = "\n".join(lines) + "\n"

        if output_path:
            clean_out = output_path if os.path.isabs(output_path) else os.path.join(REPO_ROOT, output_path)
            os.makedirs(os.path.dirname(clean_out), exist_ok=True)
            with open(clean_out, "w", encoding="utf-8") as f:
                f.write(md_content)
            print(f"[SessionManager] Exported master session history timeline to: {clean_out}")

        return md_content


# Singleton global manager instance
session_manager = SessionManager()
