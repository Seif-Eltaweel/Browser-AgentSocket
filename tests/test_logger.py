"""
Tests for Centralized Logging Infrastructure (server.logger)
"""

import io
import logging
import os
import sys
import unittest

from server.logger import setup_logger, logger


class TestLogger(unittest.TestCase):
    def test_logger_instance(self):
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "agentsocket")

    def test_logger_stream_handler(self):
        # Verify logger has at least one StreamHandler targeting sys.stderr
        handlers = logger.handlers
        self.assertTrue(len(handlers) >= 1)
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)]
        self.assertTrue(len(stream_handlers) >= 1)
        # Handler stream should be stderr
        self.assertIn(stream_handlers[0].stream, [sys.stderr, sys.__stderr__])

    def test_custom_log_level_env(self):
        os.environ["SOCKET_LOG_LEVEL"] = "DEBUG"
        custom_logger = setup_logger("agentsocket.test")
        self.assertEqual(custom_logger.level, logging.DEBUG)
        os.environ["SOCKET_LOG_LEVEL"] = "INFO"


if __name__ == "__main__":
    unittest.main()
