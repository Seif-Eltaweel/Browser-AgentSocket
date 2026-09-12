"""
AgentSocket - Session Tree Formatting & Presentation Engine
Provides ASCII timeline thread visualization, table formatting, and terminal renderers.
"""

from __future__ import annotations
import datetime
import json
import sys
import time
from typing import Any


def format_session_thread(
    details_or_events: dict[str, Any] | list[dict[str, Any]],
    session_title: str | None = None,
    total_duration_ms: float | None = None,
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
            dt_start = datetime.datetime.fromtimestamp(first_start)
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

        dt = datetime.datetime.fromtimestamp(evt_start)
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


def print_history_table(summaries: list[dict[str, Any]]) -> None:
    """Formats session summaries into a clean ASCII table."""
    if not summaries:
        print("\n[History] No recorded browser sessions found.\n")
        return

    print("\n" + "=" * 110)
    print(f"{'SESSION ID':<30} | {'TAB GROUP':<25} | {'STATUS':<10} | {'DUR(s)':<8} | {'ACTS':<5} | {'TAKOVR':<6} | {'PATH'}")
    print("=" * 110)
    for s in summaries:
        sid = s.get("session_id", "")[:28]
        title = s.get("tab_group_name", "")[:23]
        status = s.get("status", "")[:9]
        dur_ms = s.get("duration_ms")
        dur_str = f"{dur_ms/1000.0:.1f}s" if dur_ms else "N/A"
        acts = str(s.get("action_count", 0))
        tak = str(s.get("takeover_count", 0))
        spath = s.get("session_path", "")
        print(f"{sid:<30} | {title:<25} | {status:<10} | {dur_str:<8} | {acts:<5} | {tak:<6} | {spath}")
    print("=" * 110 + "\n")


def print_subskills_table(subskills: list[dict[str, Any]]) -> None:
    """Formats subskills into a clean ASCII table."""
    if not subskills:
        print("\n[Subskills] No registered subskills found in central vault.\n")
        return

    print("\n" + "=" * 120)
    print(f"{'SUBSKILL NAME':<26} | {'DISPLAY TITLE':<28} | {'BORROWED':<9} | {'TAGS':<18} | {'VAULT PATH'}")
    print("=" * 120)
    for s in subskills:
        name = s.get("name", "")[:25]
        title = s.get("display_title", "")[:26]
        borrowed = str(s.get("times_borrowed", 0))
        tags_str = ", ".join(s.get("tags", []))[:16]
        path = s.get("vault_path") or s.get("latest_session_path", "")
        print(f"{name:<26} | {title:<28} | {borrowed:<9} | {tags_str:<18} | {path}")
    print("=" * 120 + "\n")


def print_subskill_details(details: dict[str, Any] | None) -> None:
    """Displays formatted details of a single subskill."""
    if not details:
        print("\n[Subskills] Subskill not found in central vault.\n")
        return

    name = details.get("name", "")
    title = details.get("display_title", "")
    desc = details.get("description", "")
    tags = ", ".join(details.get("tags", []))
    borrowed = details.get("times_borrowed", 0)
    vault_path = details.get("vault_path") or details.get("latest_session_path", "")
    origin_sid = details.get("origin_session_id") or details.get("latest_session_id", "N/A")
    tools = details.get("available_adhoc_tools", [])
    playbook = details.get("playbook_markdown", "")

    print("\n" + "=" * 80)
    print(f"📦 Subskill: {title} (`{name}`)")
    print("=" * 80)
    print(f"• Description   : {desc}")
    print(f"• Tags          : {tags}")
    print(f"• Times Borrowed: {borrowed}")
    print(f"• Vault Path    : {vault_path}")
    print(f"• Origin Session: {origin_sid}")
    print(f"• Adhoc Tools   : {', '.join(tools) if tools else 'None'}")
    print("-" * 80)
    print("📖 Playbook Contract (sub_skill.md):")
    print(playbook if playbook else "*No playbook markdown content.*")
    print("=" * 80 + "\n")


def print_session_logs(details: dict[str, Any]) -> None:
    """Formats session.jsonl events into a tree-structured chronological thread."""
    if details.get("status") == "error":
        print(f"\n[Logs Error] {details.get('message')}\n")
        return

    formatted_thread = details.get("formatted_thread")
    if not formatted_thread:
        formatted_thread = format_session_thread(details)

    try:
        print("\n" + formatted_thread + "\n")
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_str = formatted_thread.encode(enc, errors="replace").decode(enc)
        print("\n" + safe_str + "\n")
