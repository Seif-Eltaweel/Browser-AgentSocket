"""
AgentSocket - Centralized Logging Infrastructure
Configurable structured logging with stdio isolation for MCP and server gateways.
"""

from __future__ import annotations
import logging
import os
import sys

def setup_logger(name: str = "agentsocket") -> logging.Logger:
    """
    Sets up and returns a configured logger.
    Logs to sys.stderr so MCP stdio communication remains unpolluted.
    """
    level_name = os.environ.get("SOCKET_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    return logger

logger = setup_logger("agentsocket")
