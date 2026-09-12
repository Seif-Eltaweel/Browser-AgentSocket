"""
AgentSocket - Consolidated Markdown Documentation & Master Report Generator
Generates SESSION_DOCUMENT.md per session and master timeline markdown reports.
"""

from __future__ import annotations
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Callable

from server.logger import logger
from server.models import MonthlyIndexModel, SessionStatus

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SessionDocumenter:
    """Generates markdown documentation for sessions and historical master reports."""

    @staticmethod
    def generate_session_document(
        paths: dict[str, str],
        format_session_thread_fn: Callable[..., str],
    ) -> str:
        """
        Constructs and writes a consolidated master Markdown document (SESSION_DOCUMENT.md)
        containing executive summary, subskill playbook, input/output inventories,
        adhoc tools, artifacts, and chronological execution timeline thread.
        """
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
        events: list[dict[str, Any]] = []
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
                logger.warning(f"Warning reading jsonl for doc generation: {e}")

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

        # 5. Borrowed Subskills & Central Vault Tools (Spec 18)
        manifest_path = paths.get("manifest_path") or os.path.join(session_dir, "session_manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    m_data = json.load(mf)
                borrowed = m_data.get("borrowed_subskills", [])
                if borrowed:
                    lines.append("## 🏛️ Borrowed Subskills & Referenced Vault Tools")
                    lines.append("| Subskill | Borrowed At | Vault Path | Active Adhoc Tools |")
                    lines.append("|:---|:---|:---|:---|")
                    for b in borrowed:
                        tools_str = ", ".join(f"`{t}`" for t in b.get("referenced_adhocs", []))
                        lines.append(f"| `{b.get('name')}` | `{b.get('borrowed_at')}` | `{b.get('vault_path')}` | {tools_str or 'None'} |")
                    lines.append("")
            except Exception:
                pass

        # 6. Adhoc Tools & Diagnostic Scripts
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
        lines.append("Dedicated standalone thread log: [`THREAD.md`](THREAD.md)\n")
        formatted_thread = format_session_thread_fn(events, session_title=session_title, total_duration_ms=total_duration_ms)
        lines.append("```text")
        lines.append(formatted_thread)
        lines.append("```\n")

        doc_content = "\n".join(lines) + "\n"

        # Write to SESSION_DOCUMENT.md
        try:
            doc_file = paths.get("session_doc_path") or os.path.join(session_dir, "SESSION_DOCUMENT.md")
            with open(doc_file, "w", encoding="utf-8") as df:
                df.write(doc_content)
        except Exception as e:
            logger.warning(f"Warning writing session document: {e}")

        # Also generate and write standalone THREAD.md
        SessionDocumenter.generate_thread_document(paths=paths, format_session_thread_fn=format_session_thread_fn)

        return doc_content

    @staticmethod
    def generate_thread_document(
        paths: dict[str, str],
        format_session_thread_fn: Callable[..., str],
    ) -> str:
        """
        Constructs and writes a dedicated standalone ASCII execution log (THREAD.md).
        """
        session_dir = paths["session_dir"]
        jsonl_path = paths["jsonl_path"]

        events: list[dict[str, Any]] = []
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
                logger.warning(f"Warning reading jsonl for thread generation: {e}")

        first_evt = events[0] if events else {}
        first_payload = first_evt.get("payload") or {}
        session_id = first_payload.get("session_id") or first_evt.get("session_id") or os.path.basename(session_dir)
        session_title = first_payload.get("session_title") or first_evt.get("session_title") or os.path.basename(session_dir)
        tab_group_name = first_payload.get("tab_group_name") or first_payload.get("group_name") or session_title.split(" | ")[0]
        tab_group_id_val = first_payload.get("tab_group_id") or first_evt.get("tab_group_id") or first_evt.get("tab_group_id_val") or "N/A"
        group_color = first_payload.get("group_color", "purple")
        start_time = first_evt.get("start_time") or time.time()

        total_duration_ms = 0.0
        action_count = 0
        for evt in events:
            etype = str(evt.get("type", "")).lower()
            if any(a in etype for a in ("navigate", "execute_js", "task_complete")):
                action_count += 1

        for evt in reversed(events):
            etype = str(evt.get("type", "")).lower()
            if "session_end" in etype:
                p = evt.get("payload") or {}
                total_duration_ms = p.get("total_duration_ms", 0.0)
                break

        if not total_duration_ms and events:
            last_time = events[-1].get("end_time") or events[-1].get("start_time") or start_time
            total_duration_ms = max(0.0, (last_time - start_time) * 1000.0)

        total_seconds = total_duration_ms / 1000.0
        if total_seconds >= 60:
            m = int(total_seconds // 60)
            s = int(total_seconds % 60)
            exec_time_str = f"{m}m {s}s"
        else:
            exec_time_str = f"{total_seconds:.1f}s"

        formatted_thread = format_session_thread_fn(events, session_title=session_title, total_duration_ms=total_duration_ms)

        lines = [
            f"# 🧵 Session Execution Thread: {tab_group_name}\n",
            f"* **Session ID:** `{session_id}`",
            f"* **Total Actions:** {action_count}",
            f"* **Total Execution Time:** {exec_time_str}",
            f"* **Tab Group ID:** `{tab_group_id_val}` ({group_color})\n",
            "---",
            "\n## ⏱️ Chronological Execution Log\n",
            "```text",
            formatted_thread,
            "```\n",
        ]

        thread_content = "\n".join(lines)

        try:
            thread_file = paths.get("thread_path") or os.path.join(session_dir, "THREAD.md")
            with open(thread_file, "w", encoding="utf-8") as tf:
                tf.write(thread_content)
        except Exception as e:
            logger.warning(f"Warning writing THREAD.md: {e}")

        return thread_content

    @staticmethod
    def export_all_to_markdown(
        index_model: MonthlyIndexModel,
        get_session_details_fn: Callable[[str], dict[str, Any]],
        month: str | None = None,
        output_path: str | None = None,
    ) -> str:
        """
        Exports master timeline across past sessions to a formatted Markdown report.
        """
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

                details = get_session_details_fn(s.session_path)
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
            logger.info(f"Exported master session history timeline to: {clean_out}")

        return md_content
