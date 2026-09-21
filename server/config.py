"""
AgentSocket - Centralized Configuration & Path Management (Spec 36)
Handles standard OS user data paths, environment overrides, and read-only resilience.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
import platformdirs

APP_NAME = "AgentSocket"
APP_AUTHOR = "AgentSocket"


# 1. State Directory Resolution
def get_state_dir() -> Path:
    """
    Returns the resolved state directory path.
    Priority:
    1. AGENTSOCKET_STATE_DIR environment variable
    2. platformdirs.user_data_dir(appname=APP_NAME, appauthor=APP_AUTHOR)
    """
    env_dir = os.environ.get("AGENTSOCKET_STATE_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
    else:
        path = Path(platformdirs.user_data_dir(appname=APP_NAME, appauthor=APP_AUTHOR))

    path.mkdir(parents=True, exist_ok=True)
    return path


# 2. Runtime Artifact Paths
def get_pid_file_path() -> Path:
    """Returns the process ID file path inside the resolved state directory."""
    return get_state_dir() / ".socket_server.pid"


def get_port_file_path() -> Path:
    """Returns the port discovery file path inside the resolved state directory."""
    return get_state_dir() / ".socket_server.port"


def get_token_file_path() -> Path:
    """Returns the ephemeral gateway token file path inside the resolved state directory."""
    return get_state_dir() / ".socket_server.token"


def get_db_path() -> Path:
    """
    Returns the resolved SQLite database path.
    Priority:
    1. AGENTSOCKET_DB_PATH environment variable
    2. get_state_dir() / 'agentsocket.db'
    """
    env_db = os.environ.get("AGENTSOCKET_DB_PATH")
    if env_db:
        p = Path(env_db).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return get_state_dir() / "agentsocket.db"


def get_default_logs_dir() -> Path:
    """
    Returns the resolved session logs directory path.
    Priority:
    1. AGENTSOCKET_LOGS_DIR environment variable
    2. get_state_dir() / 'logs'
    """
    env_logs = os.environ.get("AGENTSOCKET_LOGS_DIR")
    if env_logs:
        p = Path(env_logs).expanduser().resolve()
    else:
        p = get_state_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p
