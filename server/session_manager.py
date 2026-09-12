"""
AgentSocket - Session Manager Backward Compatibility Shim
This module re-exports components from the modular server.session package.
"""

from server.session import (
    ActiveSession,
    SessionManager,
    session_manager,
    format_session_thread,
    sanitize_filename,
    get_relative_session_path,
    DEFAULT_BASE_LOG_DIR,
    SessionStorage,
    SessionDocumenter,
    seed_universal_adhocs,
    print_history_table,
    print_subskills_table,
    print_subskill_details,
    print_session_logs,
)
from server.session.manager import (
    OFFLOAD_STRING_THRESHOLD,
    OFFLOAD_ARRAY_THRESHOLD,
    REPO_ROOT,
)

__all__ = [
    "ActiveSession",
    "SessionManager",
    "session_manager",
    "format_session_thread",
    "sanitize_filename",
    "get_relative_session_path",
    "DEFAULT_BASE_LOG_DIR",
    "SessionStorage",
    "SessionDocumenter",
    "seed_universal_adhocs",
    "print_history_table",
    "print_subskills_table",
    "print_subskill_details",
    "print_session_logs",
    "OFFLOAD_STRING_THRESHOLD",
    "OFFLOAD_ARRAY_THRESHOLD",
    "REPO_ROOT",
]
