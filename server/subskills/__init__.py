"""
AgentSocket - Subskills & Standard Operating Procedure (SOP) Catalog (Spec 26)
Dual SQLite & JSON Catalog Engine for Zero-Waste SOP Markdown Playbooks.
"""

from server.subskills.manager import (
    SubskillsManager,
    subskills_manager,
    parse_sop_playbook,
    sanitize_slug,
)

__all__ = [
    "SubskillsManager",
    "subskills_manager",
    "parse_sop_playbook",
    "sanitize_slug",
]
