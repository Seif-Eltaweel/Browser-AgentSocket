"""
AgentSocket - Session Storage & Atomic Persistence Subsystem
Handles atomic index updates, path resolution, JSONL file parsing, and artifact retrieval.
"""

from __future__ import annotations
import json
import os
import re
import tempfile
import time
from datetime import datetime
from typing import Any

from server.logger import logger
from server.models import (
    MonthlyIndexModel,
    SessionSummaryModel,
    SubskillsIndexModel,
    SubskillModel,
    SessionManifestModel,
    BorrowedSubskillReference,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_BASE_LOG_DIR = os.path.join(REPO_ROOT, "server", "logs")
DEFAULT_SUBSKILLS_DIR = os.path.join(REPO_ROOT, "server", "subskills")
DEFAULT_ADHOCS_DIR = os.path.join(REPO_ROOT, "server", "adhocs")


def sanitize_filename(name: str) -> str:
    """Sanitizes strings for safe cross-platform folder and file naming."""
    clean = re.sub(r"[^\w\-]+", "_", name).strip("_")
    return clean if clean else "session"


def get_relative_session_path(session_dir: str) -> str:
    """Returns relative path formatted with forward slashes starting from repo root."""
    try:
        rel = os.path.relpath(session_dir, REPO_ROOT)
        return rel.replace("\\", "/")
    except ValueError:
        return session_dir.replace("\\", "/")


class SessionStorage:
    """Manages disk persistence, atomic indexes, and file reading for sessions and central vault."""

    def __init__(
        self,
        base_log_dir: str = DEFAULT_BASE_LOG_DIR,
        subskills_dir: str | None = None,
        adhocs_dir: str | None = None,
    ):
        self.base_log_dir = os.path.abspath(base_log_dir)
        self.history_index_dir = os.path.join(self.base_log_dir, "sessions", "history_logs")
        self.index_file = os.path.join(self.history_index_dir, "index.json")

        if subskills_dir:
            self.subskills_dir = os.path.abspath(subskills_dir)
        elif os.path.abspath(base_log_dir) == os.path.abspath(DEFAULT_BASE_LOG_DIR):
            self.subskills_dir = os.path.abspath(DEFAULT_SUBSKILLS_DIR)
        else:
            self.subskills_dir = os.path.abspath(os.path.join(os.path.dirname(self.base_log_dir), "subskills"))

        if adhocs_dir:
            self.adhocs_dir = os.path.abspath(adhocs_dir)
        elif os.path.abspath(base_log_dir) == os.path.abspath(DEFAULT_BASE_LOG_DIR):
            self.adhocs_dir = os.path.abspath(DEFAULT_ADHOCS_DIR)
        else:
            self.adhocs_dir = os.path.abspath(os.path.join(os.path.dirname(self.base_log_dir), "adhocs"))

        self.subskills_index_file = os.path.join(self.subskills_dir, "subskills_index.json")
        self.ensure_directories()

    def ensure_directories(self) -> None:
        """Ensures all base log, vault, and index directories exist on disk."""
        os.makedirs(self.history_index_dir, exist_ok=True)
        os.makedirs(self.base_log_dir, exist_ok=True)
        os.makedirs(self.subskills_dir, exist_ok=True)
        os.makedirs(self.adhocs_dir, exist_ok=True)
        if not os.path.exists(self.index_file):
            self.write_index(MonthlyIndexModel())
        if not os.path.exists(self.subskills_index_file):
            self._migrate_or_init_subskills_index()

    def _migrate_or_init_subskills_index(self) -> None:
        """Migrates legacy logs/subskills_index.json if present, or initializes a clean version 2.0 index."""
        legacy_index_file = os.path.join(self.base_log_dir, "subskills_index.json")
        migrated_index = SubskillsIndexModel(version="2.0")

        if os.path.exists(legacy_index_file):
            try:
                with open(legacy_index_file, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                for k, v in old_data.get("subskills", {}).items():
                    v_dict = dict(v)
                    v_dict["vault_path"] = v_dict.get("vault_path") or f"server/subskills/{k}"
                    v_dict["origin_session_id"] = v_dict.get("origin_session_id") or v_dict.get("latest_session_id")
                    migrated_index.subskills[k] = SubskillModel.model_validate(v_dict)
            except Exception as e:
                logger.warning(f"Failed to migrate legacy subskills_index: {e}")

        self.write_subskills_index(migrated_index)

    def get_session_paths(self, session_dir_or_path: str, active_sessions: dict[int, Any] | None = None) -> dict[str, str]:
        """Returns normalized absolute and relative paths for all session subdirectories."""
        full_dir = None
        # 1. Match against active session IDs or titles if provided
        if active_sessions:
            for s in active_sessions.values():
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
                full_dir = found or (
                    os.path.join(self.base_log_dir, clean_path)
                    if not os.path.exists(os.path.join(REPO_ROOT, clean_path))
                    else os.path.join(REPO_ROOT, clean_path)
                )

        if full_dir and not os.path.isdir(full_dir) and os.path.isfile(full_dir):
            full_dir = os.path.dirname(full_dir)

        return {
            "session_dir": full_dir,
            "session_path": get_relative_session_path(full_dir),
            "input_dir": os.path.join(full_dir, "input"),
            "output_dir": os.path.join(full_dir, "output"),
            "adhocs_dir": os.path.join(full_dir, "adhocs"),
            "artifacts_dir": os.path.join(full_dir, "artifacts"),
            "jsonl_path": os.path.join(full_dir, "session.jsonl"),
            "sub_skill_path": os.path.join(full_dir, "sub_skill.md"),
            "session_doc_path": os.path.join(full_dir, "SESSION_DOCUMENT.md"),
            "manifest_path": os.path.join(full_dir, "session_manifest.json"),
            "thread_path": os.path.join(full_dir, "THREAD.md"),
        }

    def read_manifest(self, session_dir: str) -> SessionManifestModel | None:
        """Reads and validates session_manifest.json."""
        manifest_path = os.path.join(session_dir, "session_manifest.json")
        if not os.path.exists(manifest_path):
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionManifestModel.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to read session_manifest.json: {e}")
            return None

    def write_manifest(self, session_dir: str, manifest_model: SessionManifestModel) -> None:
        """Atomically writes session_manifest.json."""
        manifest_path = os.path.join(session_dir, "session_manifest.json")
        os.makedirs(session_dir, exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=session_dir,
            prefix="mnf_",
            suffix=".tmp",
            text=True,
        )
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(manifest_model.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, manifest_path)
        except Exception as e:
            logger.error(f"Error writing atomic session_manifest.json: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    # ========================================================================
    # Index Reading & Atomic Writing
    # ========================================================================
    def read_index(self) -> MonthlyIndexModel:
        """Reads and validates the monthly master index from index.json."""
        if not os.path.exists(self.index_file):
            return MonthlyIndexModel()
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MonthlyIndexModel.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to read index.json: {e}")
            return MonthlyIndexModel()

    def write_index(self, index_model: MonthlyIndexModel) -> None:
        """Atomically writes index.json via temporary file and replace."""
        index_model.updated_at = time.time()
        os.makedirs(os.path.dirname(self.index_file), exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.index_file),
            prefix="idx_",
            suffix=".tmp",
            text=True,
        )
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(index_model.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.index_file)
        except Exception as e:
            logger.error(f"Error writing atomic index.json: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def read_subskills_index(self) -> SubskillsIndexModel:
        """Reads and validates subskills_index.json."""
        if not os.path.exists(self.subskills_index_file):
            return SubskillsIndexModel()
        try:
            with open(self.subskills_index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SubskillsIndexModel.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to read subskills_index.json: {e}")
            return SubskillsIndexModel()

    def write_subskills_index(self, index_model: SubskillsIndexModel) -> None:
        """Atomically writes subskills_index.json."""
        index_model.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        os.makedirs(os.path.dirname(self.subskills_index_file), exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.subskills_index_file),
            prefix="subsk_",
            suffix=".tmp",
            text=True,
        )
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(index_model.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.subskills_index_file)
        except Exception as e:
            logger.error(f"Error writing atomic subskills_index.json: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def update_index_for_session(self, session: Any) -> None:
        """Upserts a session's summary in the monthly master index."""
        index_model = self.read_index()
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

        self.write_index(index_model)

    def query_history(
        self,
        query_hint: str = "",
        month: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Scans index.json for matching session titles, tab groups, status, or date keywords.
        Returns lightweight summaries sorted newest first.
        """
        index_model = self.read_index()
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

        results.sort(key=lambda s: s.start_time, reverse=True)
        return [s.model_dump() for s in results[:limit]]

    def get_session_details(self, session_path: str, formatter_fn: Any | None = None) -> dict[str, Any]:
        """
        Reads and parses session.jsonl from session_path.
        Reconstructs full chronological thread for drill-down analysis.
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
                "formatted_thread": "*Session log file not found.*",
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
                "formatted_thread": f"*Failed to read session log: {e}*",
            }

        formatted_thread = formatter_fn(events) if formatter_fn else ""

        return {
            "status": "success",
            "session_path": get_relative_session_path(os.path.dirname(jsonl_path)),
            "event_count": len(events),
            "events": events,
            "formatted_thread": formatted_thread,
        }

    def get_session_artifact(self, session_path: str, artifact_name: str) -> dict[str, Any] | str:
        """
        Reads a specific offloaded heavy payload JSON or returns the file path for images/binary files.
        """
        clean_path = session_path.replace("/", os.sep).replace("\\", os.sep)
        full_dir = clean_path if os.path.isabs(clean_path) else os.path.join(REPO_ROOT, clean_path)

        if not os.path.isdir(full_dir):
            full_dir = os.path.dirname(full_dir)

        clean_art = artifact_name.replace("/", os.sep).replace("\\", os.sep)
        if clean_art.startswith("artifacts" + os.sep):
            clean_art = clean_art[len("artifacts" + os.sep):]

        artifact_file = os.path.join(full_dir, "artifacts", clean_art)
        if not os.path.exists(artifact_file):
            artifact_file = os.path.join(full_dir, clean_art)

        if not os.path.exists(artifact_file):
            return {
                "status": "error",
                "message": f"Artifact file not found: {artifact_name}",
                "resolved_path": artifact_file,
            }

        if artifact_file.endswith(".json"):
            try:
                with open(artifact_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                return {"status": "error", "message": f"Failed to parse JSON artifact: {e}"}
        else:
            return artifact_file
