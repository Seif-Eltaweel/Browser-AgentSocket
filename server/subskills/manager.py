"""
AgentSocket - SOP Markdown Subskills & Dual SQLite/JSON Catalog Manager (Spec 26)

Manages Standard Operating Procedure (SOP) playbooks stored in server/subskills/<name>/sub_skill.md.
Provides dual SQLite table synchronization for fast indexed search with automatic fallback
to portable subskills_index.json (version 2.1.0).
"""

import json
import os
import re
import shutil
import tempfile
import time
from typing import Any
import yaml

from server.db import init_db, get_connection, DB_PATH
from server.logger import logger
from server.models import SubskillModel, SubskillsIndexModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SUBSKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))


def sanitize_slug(name: str) -> str:
    """Sanitizes name to a clean url/file friendly slug."""
    clean = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name.strip())
    clean = clean.strip("._")
    return clean.lower().replace("_", "-") or "subskill"


def parse_sop_playbook(content: str) -> tuple[dict[str, Any], str]:
    """Parses YAML frontmatter and markdown body from an SOP playbook."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                if isinstance(fm, dict):
                    return fm, parts[2].strip()
            except Exception as e:
                logger.warning(f"Failed to parse playbook YAML frontmatter: {e}")
    return {}, content.strip()


class SubskillsManager:
    """
    Subskills & SOP Playbook Catalog Manager.
    Dual SQLite and JSON architecture:
    - Primary: Embedded SQLite indexed subskills table.
    - Fallback & Portable Export: subskills_index.json (version 2.1.0).
    """

    def __init__(
        self,
        subskills_dir: str | None = None,
        db_path: str | None = None,
        index_file: str | None = None,
    ):
        self.subskills_dir = os.path.abspath(subskills_dir) if subskills_dir else DEFAULT_SUBSKILLS_DIR
        self.db_path = os.path.abspath(db_path) if db_path else DB_PATH
        self.subskills_index_file = os.path.abspath(index_file) if index_file else os.path.join(self.subskills_dir, "subskills_index.json")

        os.makedirs(self.subskills_dir, exist_ok=True)
        init_db(self.db_path)
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Ensures subskills_index.json exists and SQLite subskills table is synchronized."""
        if os.path.exists(self.subskills_index_file):
            try:
                index_model = self._read_subskills_index()
                # Upsert existing subskills from index to SQLite
                for sk in index_model.subskills.values():
                    self.upsert_subskill_sqlite(sk)
            except Exception as e:
                logger.warning(f"Error syncing initial subskills to SQLite: {e}")
        else:
            self.sync_all_playbooks()

    # ========================================================================
    # SQLite Subskills Operations (Spec 26 Section 3.1)
    # ========================================================================
    def upsert_subskill_sqlite(self, subskill: SubskillModel) -> bool:
        """
        Upserts a subskill into the SQLite subskills table:
        INSERT INTO subskills (slug, display_title, description, tags, times_referenced, playbook_path, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(slug) DO UPDATE SET ...
        """
        try:
            init_db(self.db_path)
            tags_str = ",".join(subskill.tags) if subskill.tags else ""
            with get_connection(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO subskills (slug, display_title, description, tags, times_referenced, playbook_path, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(slug) DO UPDATE SET
                        display_title = excluded.display_title,
                        description = excluded.description,
                        tags = excluded.tags,
                        times_referenced = excluded.times_referenced,
                        playbook_path = excluded.playbook_path,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (
                        subskill.name,
                        subskill.display_title,
                        subskill.description,
                        tags_str,
                        subskill.times_referenced,
                        subskill.playbook_path,
                    ),
                )
            return True
        except Exception as e:
            logger.warning(f"Failed to upsert subskill to SQLite ({subskill.name}): {e}")
            return False

    def list_subskills_sqlite(
        self,
        query: str = "",
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]] | None:
        """
        Queries subskills from the SQLite table.
        Returns None if SQLite is unavailable or table is empty to trigger fallback.
        """
        try:
            with get_connection(self.db_path) as conn:
                sql = "SELECT slug, display_title, description, tags, times_referenced, playbook_path, created_at, updated_at FROM subskills"
                params: list[Any] = []
                conditions: list[str] = []

                if query:
                    q = f"%{query.strip().lower()}%"
                    conditions.append(
                        "(LOWER(slug) LIKE ? OR LOWER(display_title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags) LIKE ?)"
                    )
                    params.extend([q, q, q, q])

                if conditions:
                    sql += " WHERE " + " AND ".join(conditions)

                sql += " ORDER BY times_referenced DESC, slug ASC;"

                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()
                if not rows and not query and not tags:
                    return None

                results: list[dict[str, Any]] = []
                for row in rows:
                    r = dict(row)
                    slug = r["slug"]
                    raw_tags = r.get("tags") or ""
                    tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()] if isinstance(raw_tags, str) else list(raw_tags)

                    if tags:
                        row_tags_lower = [t.lower() for t in tag_list]
                        req_tags_lower = [t.lower() for t in tags]
                        if not any(t in row_tags_lower for t in req_tags_lower):
                            continue

                    playbook_path = r.get("playbook_path") or f"server/subskills/{slug}/sub_skill.md"
                    vault_path = os.path.dirname(playbook_path).replace("\\", "/")

                    results.append({
                        "name": slug,
                        "slug": slug,
                        "display_title": r.get("display_title", slug),
                        "description": r.get("description", ""),
                        "tags": tag_list,
                        "times_referenced": r.get("times_referenced") or 0,
                        "times_borrowed": r.get("times_referenced") or 0,
                        "playbook_path": playbook_path,
                        "vault_path": vault_path,
                        "subskill_file": "sub_skill.md",
                        "created_at": r.get("created_at"),
                        "updated_at": r.get("updated_at"),
                    })
                return results
        except Exception as e:
            logger.warning(f"Error querying subskills from SQLite: {e}")
            return None

    def get_subskill_sqlite(self, name: str) -> dict[str, Any] | None:
        """Retrieves a single subskill record from SQLite."""
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT slug, display_title, description, tags, times_referenced, playbook_path, created_at, updated_at FROM subskills WHERE slug = ?;",
                    (name,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                r = dict(row)
                slug = r["slug"]
                raw_tags = r.get("tags") or ""
                tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()] if isinstance(raw_tags, str) else list(raw_tags)
                playbook_path = r.get("playbook_path") or f"server/subskills/{slug}/sub_skill.md"
                vault_path = os.path.dirname(playbook_path).replace("\\", "/")

                playbook_markdown = self._read_playbook_markdown(playbook_path, slug)
                adhoc_tools = self._find_adhoc_tools(vault_path, slug)

                return {
                    "name": slug,
                    "slug": slug,
                    "display_title": r.get("display_title", slug),
                    "description": r.get("description", ""),
                    "tags": tag_list,
                    "times_referenced": r.get("times_referenced") or 0,
                    "times_borrowed": r.get("times_referenced") or 0,
                    "playbook_path": playbook_path,
                    "vault_path": vault_path,
                    "subskill_file": "sub_skill.md",
                    "playbook_markdown": playbook_markdown,
                    "adhoc_tools": adhoc_tools,
                    "available_adhoc_tools": adhoc_tools,
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                }
        except Exception as e:
            logger.warning(f"Error retrieving subskill '{name}' from SQLite: {e}")
            return None

    def increment_reference_sqlite(self, name: str) -> bool:
        """Increments the times_referenced counter in SQLite atomically."""
        try:
            with get_connection(self.db_path) as conn:
                conn.execute(
                    "UPDATE subskills SET times_referenced = times_referenced + 1, updated_at = CURRENT_TIMESTAMP WHERE slug = ?;",
                    (name,),
                )
            return True
        except Exception as e:
            logger.warning(f"Error incrementing times_referenced for '{name}' in SQLite: {e}")
            return False

    # ========================================================================
    # JSON Catalog & File Operations (Spec 26 Section 3.2)
    # ========================================================================
    def _read_subskills_index(self) -> SubskillsIndexModel:
        """Reads and validates subskills_index.json."""
        if not os.path.exists(self.subskills_index_file):
            return SubskillsIndexModel(version="2.1.0")
        try:
            with open(self.subskills_index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SubskillsIndexModel.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to read subskills_index.json: {e}")
            return SubskillsIndexModel(version="2.1.0")

    def _write_subskills_index(self, index_model: SubskillsIndexModel) -> None:
        """Atomically writes subskills_index.json and syncs to SQLite."""
        index_model.version = "2.1.0"
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

        # Sync to SQLite
        for sk in index_model.subskills.values():
            self.upsert_subskill_sqlite(sk)

    def _resolve_playbook_path(self, playbook_path: str, slug: str) -> str:
        """Resolves relative playbook path to an absolute filesystem path."""
        candidates = [
            os.path.join(self.subskills_dir, slug, "sub_skill.md"),
            playbook_path,
            os.path.join(REPO_ROOT, playbook_path),
            os.path.join(self.subskills_dir, os.path.basename(os.path.dirname(playbook_path)), "sub_skill.md"),
        ]
        for c in candidates:
            if not c:
                continue
            clean = c.replace("/", os.sep).replace("\\", os.sep)
            if os.path.isfile(clean):
                return clean
        return os.path.join(self.subskills_dir, slug, "sub_skill.md")

    def _read_playbook_markdown(self, playbook_path: str, slug: str) -> str:
        """Reads Markdown content from an SOP playbook."""
        resolved = self._resolve_playbook_path(playbook_path, slug)
        if os.path.exists(resolved):
            try:
                with open(resolved, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"*Failed to read playbook: {e}*"
        return ""

    def _find_adhoc_tools(self, vault_path: str, slug: str) -> list[str]:
        """Finds any existing adhoc tools for backward compatibility."""
        candidates = [
            os.path.join(self.subskills_dir, slug, "adhocs"),
            os.path.join(REPO_ROOT, vault_path, "adhocs"),
        ]
        for c in candidates:
            if os.path.isdir(c):
                return sorted([f for f in os.listdir(c) if os.path.isfile(os.path.join(c, f))])
        return []

    # ========================================================================
    # Public Gateway Methods (SQLite with JSON Fallback)
    # ========================================================================
    def list_subskills(
        self,
        query: str = "",
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lists registered subskills matching search query or tags.
        Primary: Fast indexed SQLite query.
        Fallback: Reads subskills_index.json if SQLite is empty or unavailable.
        """
        # 1. Attempt SQLite query
        sqlite_results = self.list_subskills_sqlite(query=query, tags=tags)
        if sqlite_results is not None:
            return sqlite_results

        # 2. Fallback to subskills_index.json
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

        results.sort(key=lambda s: (s.times_referenced, s.times_borrowed, s.name), reverse=True)
        dumped: list[dict[str, Any]] = []
        for s in results:
            d = s.model_dump()
            d["slug"] = s.name
            dumped.append(d)
        return dumped

    def get_subskill(self, name: str) -> dict[str, Any] | None:
        """
        Retrieves a subskill by slug name, including metadata and playbook markdown.
        Primary: SQLite query.
        Fallback: subskills_index.json.
        """
        # 1. Attempt SQLite query
        res = self.get_subskill_sqlite(name)
        if res:
            return res

        # 2. Fallback to subskills_index.json
        index_model = self._read_subskills_index()
        subskill = index_model.subskills.get(name)
        if not subskill:
            return None

        playbook_path = subskill.playbook_path or f"server/subskills/{name}/sub_skill.md"
        vault_path = subskill.vault_path or os.path.dirname(playbook_path).replace("\\", "/")
        playbook_markdown = self._read_playbook_markdown(playbook_path, name)
        adhoc_tools = self._find_adhoc_tools(vault_path, name) or subskill.adhoc_tools

        d = subskill.model_dump()
        d["slug"] = subskill.name
        d["playbook_markdown"] = playbook_markdown
        d["available_adhoc_tools"] = adhoc_tools
        return d

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
        """
        Registers or updates a session/playbook as a permanent reusable SOP subskill.
        Upserts into SQLite subskills table and exports to subskills_index.json.
        """
        slug = sanitize_slug(name)

        # Resolve paths
        clean_sess = session_path.replace("/", os.sep).replace("\\", os.sep)
        session_dir = clean_sess if os.path.isabs(clean_sess) else os.path.join(REPO_ROOT, clean_sess)
        sub_skill_file = os.path.join(session_dir, "sub_skill.md")
        adhocs_dir = os.path.join(session_dir, "adhocs")

        os.makedirs(session_dir, exist_ok=True)

        if subskill_markdown:
            with open(sub_skill_file, "w", encoding="utf-8") as sf:
                sf.write(subskill_markdown)
        elif not os.path.exists(sub_skill_file):
            scaffold = f"""---
name: {slug}
display_title: "{display_title or slug.replace('-', ' ').title()}"
description: "{description or f'Automated SOP playbook for {slug}'}"
tags: {json.dumps(tags or [slug])}
version: "2.1.0"
---

# Playbook: {display_title or slug.replace('-', ' ').title()}

## Strategic Objective
Automate standard operating procedure for {display_title or slug}.

## Recommended OODA Steps
1. Call `browser_observe`. Locate `[role="main"]` and inspect available actions.
2. Formulate atomic actions and verify required interactive elements.
3. If blocked or human intervention required:
   - Call `browser_set_milestone("Awaiting Human 2FA")`.
   - Wait for user Takeover.
"""
            with open(sub_skill_file, "w", encoding="utf-8") as sf:
                sf.write(scaffold)

        # Parse frontmatter from playbook if metadata missing
        if not display_title or not description or not tags:
            try:
                if os.path.exists(sub_skill_file):
                    with open(sub_skill_file, "r", encoding="utf-8") as sf:
                        content = sf.read()
                    fm, _ = parse_sop_playbook(content)
                    if fm:
                        display_title = display_title or fm.get("display_title")
                        description = description or fm.get("description")
                        if tags is None and "tags" in fm:
                            tags = fm.get("tags")
            except Exception as e:
                logger.warning(f"Failed to extract frontmatter in register_subskill: {e}")

        display_title = display_title or slug.replace("-", " ").title()
        description = description or f"Standard operating procedure for {display_title}."
        if tags is None:
            tags = [t.strip().lower() for t in re.split(r"[-_\s]+", slug) if t.strip()]

        # Permanent central subskills vault promotion
        vault_subskill_dir = os.path.join(self.subskills_dir, slug)
        os.makedirs(vault_subskill_dir, exist_ok=True)

        dst_playbook = os.path.join(vault_subskill_dir, "sub_skill.md")
        if os.path.exists(sub_skill_file):
            shutil.copy2(sub_skill_file, dst_playbook)

        # Spec 18/33: Maintain backward-compatible adhoc copy if candidates explicitly provided
        promoted_tools: list[str] = []
        if os.path.exists(adhocs_dir):
            vault_adhocs_dir = os.path.join(vault_subskill_dir, "adhocs")
            os.makedirs(vault_adhocs_dir, exist_ok=True)
            candidate_tools = adhoc_tools if adhoc_tools is not None else os.listdir(adhocs_dir)
            for t_name in candidate_tools:
                src_tool = os.path.join(adhocs_dir, t_name)
                if os.path.isfile(src_tool):
                    dst_tool = os.path.join(vault_adhocs_dir, t_name)
                    shutil.copy2(src_tool, dst_tool)
                    promoted_tools.append(t_name)

        try:
            rel = os.path.relpath(vault_subskill_dir, REPO_ROOT)
            if not rel.startswith(".."):
                vault_rel_path = rel.replace("\\", "/")
            else:
                vault_rel_path = vault_subskill_dir.replace("\\", "/")
        except Exception:
            vault_rel_path = vault_subskill_dir.replace("\\", "/")

        playbook_rel_path = f"{vault_rel_path}/sub_skill.md".replace("\\", "/")

        index_model = self._read_subskills_index()
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        existing = index_model.subskills.get(slug)
        created_at = existing.created_at if existing else now_iso
        times_ref = existing.times_referenced if existing else 0

        subskill = SubskillModel(
            name=slug,
            display_title=display_title,
            description=description,
            tags=tags,
            vault_path=vault_rel_path,
            subskill_file="sub_skill.md",
            playbook_path=playbook_rel_path,
            adhoc_tools=promoted_tools,
            times_borrowed=times_ref,
            times_referenced=times_ref,
            success_rate=1.0,
            origin_session_id=None,
            created_at=created_at,
            updated_at=now_iso,
        )

        # Save to JSON index
        index_model.subskills[slug] = subskill
        self._write_subskills_index(index_model)

        # Upsert directly to SQLite
        self.upsert_subskill_sqlite(subskill)

        res_dict = subskill.model_dump()
        res_dict["slug"] = slug

        return {
            "status": "success",
            "message": f"Subskill '{slug}' registered into catalog successfully.",
            "subskill": res_dict,
            "vault_path": vault_rel_path,
            "playbook_path": playbook_rel_path,
        }

    def borrow_subskill(
        self,
        name: str,
        target_session_dir: str,
        input_file_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Borrows an SOP subskill into target session workspace (Zero-Waste architecture):
        1. Catalog lookup via SQLite with JSON fallback.
        2. Copies ONLY sub_skill.md into target session workspace.
        3. Copies input file to target input/ if provided.
        4. Increments times_referenced in SQLite and subskills_index.json.
        """
        subskill = self.get_subskill(name)
        if not subskill:
            return {"status": "error", "message": f"Subskill '{name}' not found in catalog."}

        os.makedirs(target_session_dir, exist_ok=True)

        # 1. Copy sub_skill.md (Zero-Waste: pure markdown playbook, no executable code duplication)
        playbook_path = subskill.get("playbook_path") or f"server/subskills/{name}/sub_skill.md"
        src_playbook = self._resolve_playbook_path(playbook_path, name)
        dst_playbook = os.path.join(target_session_dir, "sub_skill.md")

        if os.path.exists(src_playbook):
            shutil.copy2(src_playbook, dst_playbook)
        else:
            with open(dst_playbook, "w", encoding="utf-8") as f:
                f.write(subskill.get("playbook_markdown") or f"# Playbook: {subskill.get('display_title', name)}\n")

        # 2. Copy input file if provided
        if input_file_path and os.path.isfile(input_file_path):
            input_dir = os.path.join(target_session_dir, "input")
            os.makedirs(input_dir, exist_ok=True)
            dst_input = os.path.join(input_dir, os.path.basename(input_file_path))
            shutil.copy2(input_file_path, dst_input)

        # 3. Increment counters
        self.increment_reference_sqlite(name)

        index_model = self._read_subskills_index()
        if name in index_model.subskills:
            index_model.subskills[name].times_referenced += 1
            index_model.subskills[name].times_borrowed += 1
            self._write_subskills_index(index_model)

        return {
            "status": "success",
            "message": f"Subskill '{name}' borrowed successfully.",
            "target_session_dir": target_session_dir,
            "playbook_path": dst_playbook,
            "times_referenced": (subskill.get("times_referenced") or 0) + 1,
        }

    def sync_all_playbooks(self) -> int:
        """
        Scans all folders in server/subskills/ for sub_skill.md.
        Extracts metadata and upserts them into both SQLite and subskills_index.json.
        Returns the count of synced playbooks.
        """
        index_model = self._read_subskills_index()
        count = 0

        if not os.path.isdir(self.subskills_dir):
            return 0

        for entry in os.listdir(self.subskills_dir):
            folder = os.path.join(self.subskills_dir, entry)
            if not os.path.isdir(folder) or entry.startswith(".") or entry == "adhocs":
                continue

            playbook_file = os.path.join(folder, "sub_skill.md")
            if not os.path.isfile(playbook_file):
                continue

            try:
                with open(playbook_file, "r", encoding="utf-8") as f:
                    content = f.read()
                fm, _ = parse_sop_playbook(content)

                slug = fm.get("name") or sanitize_slug(entry)
                display_title = fm.get("display_title") or slug.replace("-", " ").title()
                description = fm.get("description") or f"Standard operating procedure for {display_title}."
                tags = fm.get("tags") or [t.strip().lower() for t in re.split(r"[-_\s]+", slug) if t.strip()]
                now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

                existing = index_model.subskills.get(slug)
                times_ref = existing.times_referenced if existing else 0

                adhocs = self._find_adhoc_tools(f"server/subskills/{slug}", slug)

                subskill = SubskillModel(
                    name=slug,
                    display_title=display_title,
                    description=description,
                    tags=tags,
                    vault_path=f"server/subskills/{slug}".replace("\\", "/"),
                    subskill_file="sub_skill.md",
                    playbook_path=f"server/subskills/{slug}/sub_skill.md".replace("\\", "/"),
                    adhoc_tools=adhocs,
                    times_borrowed=times_ref,
                    times_referenced=times_ref,
                    created_at=existing.created_at if existing else now_iso,
                    updated_at=now_iso,
                )

                index_model.subskills[slug] = subskill
                self.upsert_subskill_sqlite(subskill)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to sync playbook from '{folder}': {e}")

        self._write_subskills_index(index_model)
        return count


# Singleton instance for default server root
subskills_manager = SubskillsManager()
