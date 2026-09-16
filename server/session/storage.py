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
import yaml

from server.db import init_db, get_connection, DB_PATH
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
        db_path: str | None = None,
    ):
        self.base_log_dir = os.path.abspath(base_log_dir)
        self.history_index_dir = os.path.join(self.base_log_dir, "sessions", "history_logs")
        self.index_file = os.path.join(self.history_index_dir, "index.json")

        if db_path:
            self.db_path = os.path.abspath(db_path)
        elif os.path.abspath(base_log_dir) == os.path.abspath(DEFAULT_BASE_LOG_DIR):
            self.db_path = DB_PATH
        else:
            self.db_path = os.path.join(self.base_log_dir, "agentsocket.db")

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
        """Ensures all base log, vault, and database connections are initialized."""
        os.makedirs(self.history_index_dir, exist_ok=True)
        os.makedirs(self.base_log_dir, exist_ok=True)
        os.makedirs(self.subskills_dir, exist_ok=True)
        os.makedirs(self.adhocs_dir, exist_ok=True)
        init_db(self.db_path)
        if not os.path.exists(self.subskills_index_file):
            self._migrate_or_init_subskills_index()

    def _migrate_or_init_subskills_index(self) -> None:
        """Migrates legacy logs/subskills_index.json if present, or initializes a clean version 2.0 index."""
        legacy_index_file = os.path.join(self.base_log_dir, "subskills_index.json")
        migrated_index = SubskillsIndexModel(version="2.1.0")

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
        """Reads and validates manifest from YAML frontmatter in SESSION_DOCUMENT.md."""
        doc_path = os.path.join(session_dir, "SESSION_DOCUMENT.md")
        if os.path.exists(doc_path):
            try:
                with open(doc_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        frontmatter_str = parts[1]
                        data = yaml.safe_load(frontmatter_str)
                        if isinstance(data, dict):
                            if "session_title" not in data and "tab_group_name" in data:
                                data["session_title"] = data["tab_group_name"]
                            elif "tab_group_name" not in data and "session_title" in data:
                                data["tab_group_name"] = data["session_title"]
                            return SessionManifestModel.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to parse YAML frontmatter from SESSION_DOCUMENT.md: {e}")

        # Legacy fallback to session_manifest.json
        manifest_path = os.path.join(session_dir, "session_manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SessionManifestModel.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to read session_manifest.json: {e}")
                return None
        return None

    def write_manifest(self, session_dir: str, manifest_model: SessionManifestModel) -> None:
        """Atomically writes manifest to YAML frontmatter in SESSION_DOCUMENT.md."""
        doc_path = os.path.join(session_dir, "SESSION_DOCUMENT.md")
        os.makedirs(session_dir, exist_ok=True)

        body = ""
        if os.path.exists(doc_path):
            try:
                with open(doc_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        body = parts[2].lstrip("\r\n")
                    else:
                        body = ""
                else:
                    body = content
            except Exception:
                body = ""

        if not body:
            title = manifest_model.tab_group_name or manifest_model.session_title
            status_str = str(manifest_model.status or "active").upper()
            body = (
                f"# 📜 Session Document: `{title}`\n\n"
                f"> **Session ID:** `{manifest_model.session_id}`  \n"
                f"> **Status:** `{status_str}`  \n"
            )

        frontmatter_dict = manifest_model.model_dump(mode="json", exclude_none=True)
        frontmatter_yaml = yaml.dump(frontmatter_dict, sort_keys=False, default_flow_style=False)
        new_content = f"---\n{frontmatter_yaml}---\n\n{body}\n"

        temp_fd, temp_path = tempfile.mkstemp(
            dir=session_dir,
            prefix="doc_",
            suffix=".tmp",
            text=True,
        )
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, doc_path)
        except Exception as e:
            logger.error(f"Error writing YAML frontmatter to SESSION_DOCUMENT.md: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    # ========================================================================
    # Index Reading & Atomic Writing (SQLite & Backward-Compatibility)
    # ========================================================================
    def read_index(self) -> MonthlyIndexModel:
        """
        Reads and builds MonthlyIndexModel dynamically from SQLite sessions table.
        Eliminates reading index.json file while preserving full backward compatibility.
        """
        model = MonthlyIndexModel()
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute("SELECT * FROM sessions ORDER BY start_time DESC")
                rows = cursor.fetchall()
                for r in rows:
                    d = dict(r)
                    start_t = d.get("start_time") or time.time()
                    dt = datetime.fromtimestamp(start_t)
                    month_key = dt.strftime("%Y-%m")
                    status_raw = d.get("status") or "active"
                    summary = SessionSummaryModel(
                        session_id=d.get("session_id", ""),
                        session_title=d.get("tab_group_name") or d.get("session_id", ""),
                        tab_group_id=d.get("tab_group_id") or 0,
                        tab_group_name=d.get("tab_group_name") or "",
                        agent_name=d.get("agent_name") or "AgentSocket Local",
                        group_color=d.get("group_color") or "purple",
                        status=status_raw,
                        start_time=start_t,
                        end_time=d.get("end_time"),
                        duration_ms=d.get("duration_ms", 0.0),
                        event_count=d.get("event_count", 0),
                        action_count=d.get("action_count", 0),
                        takeover_count=d.get("takeover_count", 0),
                        session_path=d.get("session_path", ""),
                        artifacts_count=d.get("artifacts_count", 0),
                        end_reason=d.get("end_reason"),
                    )
                    if month_key not in model.months:
                        model.months[month_key] = []
                    model.months[month_key].append(summary)
        except Exception as e:
            logger.warning(f"Failed to read sessions from SQLite: {e}")
            if os.path.exists(self.index_file):
                try:
                    with open(self.index_file, "r", encoding="utf-8") as f:
                        return MonthlyIndexModel.model_validate(json.load(f))
                except Exception:
                    pass
        return model

    def write_index(self, index_model: MonthlyIndexModel) -> None:
        """Deprecated: No-op to eliminate index.json disk thrashing."""
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
        """Atomically writes subskills_index.json and syncs to SQLite subskills table."""
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

        # Sync to SQLite subskills table
        try:
            with get_connection(self.db_path) as conn:
                for slug, sk in index_model.subskills.items():
                    tags_str = ",".join(sk.tags) if sk.tags else ""
                    conn.execute("""
                        INSERT INTO subskills (slug, display_title, description, tags, times_referenced, playbook_path, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(slug) DO UPDATE SET
                            display_title = excluded.display_title,
                            description = excluded.description,
                            tags = excluded.tags,
                            times_referenced = excluded.times_referenced,
                            playbook_path = excluded.playbook_path,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (
                        slug,
                        sk.display_title,
                        sk.description,
                        tags_str,
                        sk.times_referenced or sk.times_borrowed,
                        sk.playbook_path or (f"{sk.vault_path}/sub_skill.md" if sk.vault_path else f"server/subskills/{slug}/sub_skill.md"),
                    ))
        except Exception as e:
            logger.warning(f"Error syncing subskills to SQLite: {e}")

    def update_index_for_session(self, session: Any) -> None:
        """Atomic O(1) upsert into SQLite. Eliminates index.json disk thrashing."""
        title = getattr(session, "tab_group_name", None) or getattr(session, "session_title", "")
        status_str = session.status.value if hasattr(session.status, "value") else str(session.status)
        with get_connection(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sessions (
                    session_id, tab_group_id, tab_group_name, group_color, agent_name,
                    status, start_time, end_time, duration_ms, event_count,
                    action_count, takeover_count, session_path, artifacts_count, end_reason, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    tab_group_name = excluded.tab_group_name,
                    group_color = excluded.group_color,
                    agent_name = excluded.agent_name,
                    status = excluded.status,
                    end_time = excluded.end_time,
                    duration_ms = excluded.duration_ms,
                    event_count = excluded.event_count,
                    action_count = excluded.action_count,
                    takeover_count = excluded.takeover_count,
                    artifacts_count = excluded.artifacts_count,
                    end_reason = excluded.end_reason,
                    updated_at = CURRENT_TIMESTAMP;
            """, (
                session.session_id,
                session.tab_group_id,
                title,
                getattr(session, "group_color", "purple"),
                getattr(session, "agent_name", "AgentSocket Local"),
                status_str,
                session.start_time,
                session.end_time,
                session.duration_ms or 0.0,
                session.event_count,
                session.action_count,
                session.takeover_count,
                session.session_path,
                session.artifacts_count,
                session.end_reason,
            ))

    def log_event_index(
        self,
        event_id: str,
        session_id: str,
        event_type: str,
        timestamp: float,
        duration_ms: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Fast indexed insert into SQLite events table."""
        payload_json = json.dumps(payload) if payload else None
        try:
            with get_connection(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO events (event_id, session_id, event_type, timestamp, duration_ms, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (event_id, session_id, event_type, timestamp, duration_ms, payload_json))
        except Exception as e:
            logger.debug(f"SQLite event index insert skipped/failed: {e}")

    def query_history(
        self,
        query_hint: str = "",
        month: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fast indexed SQL query replacing full JSON file scans."""
        with get_connection(self.db_path) as conn:
            if query_hint:
                pattern = f"%{query_hint}%"
                cursor = conn.execute("""
                    SELECT * FROM sessions 
                    WHERE tab_group_name LIKE ? OR session_id LIKE ? OR agent_name LIKE ? OR status LIKE ?
                    ORDER BY start_time DESC LIMIT ?
                """, (pattern, pattern, pattern, pattern, limit))
            else:
                cursor = conn.execute("SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?", (limit,))

            rows = [dict(row) for row in cursor.fetchall()]
            for r in rows:
                if "session_title" not in r or not r["session_title"]:
                    r["session_title"] = r.get("tab_group_name", "")
            return rows

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
