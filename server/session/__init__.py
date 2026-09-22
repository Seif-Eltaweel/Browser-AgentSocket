"""
AgentSocket - Session Management Subsystem
Modular architecture for session lifecycle, atomic storage, ASCII timelines, and reports.
"""

from server.session.manager import (
    ActiveSession,
    AtomicStep,
    StepTracker,
    SessionManager,
    session_manager,
    seed_universal_adhocs,
)
from server.session.formatter import (
    format_session_thread,
    print_history_table,
    print_subskills_table,
    print_subskill_details,
    print_session_logs,
)
from server.session.storage import (
    SessionStorage,
    sanitize_filename,
    get_relative_session_path,
    DEFAULT_BASE_LOG_DIR,
)
from server.session.documenter import SessionDocumenter

__all__ = [
    "ActiveSession",
    "AtomicStep",
    "StepTracker",
    "SessionManager",
    "session_manager",
    "seed_universal_adhocs",
    "format_session_thread",
    "print_history_table",
    "print_subskills_table",
    "print_subskill_details",
    "print_session_logs",
    "SessionStorage",
    "sanitize_filename",
    "get_relative_session_path",
    "DEFAULT_BASE_LOG_DIR",
    "SessionDocumenter",
]

