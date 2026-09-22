"""
AgentSocket - Feature Spec 36 Packaging & Runtime State Isolation Test Suite 📦⚙️
Validates OS state directory resolution, environment variable overrides, read-only repo resilience,
runtime artifact locations, and PEP 621 packaging / CLI entrypoint definitions.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.config import (
    APP_NAME,
    APP_AUTHOR,
    get_state_dir,
    get_pid_file_path,
    get_port_file_path,
    get_token_file_path,
    get_db_path,
    get_default_logs_dir,
)
from server.db import init_db, get_connection
from server.socket_server import (
    write_pid_file,
    remove_pid_file,
    write_port_file,
    remove_port_file,
    write_token_file,
    remove_token_file,
    get_or_generate_token,
    REPO_ROOT,
)
from server.socket_launcher import (
    build_cli_parser,
    clean_stale_pid_file,
    clean_stale_port_file,
    resolve_server_url,
)


class TestSpec36PackagingAndRuntime(unittest.TestCase):
    def test_default_state_dir_resolution(self):
        """Verify state dir resolves to standard OS user directory when no env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            path = get_state_dir()
            self.assertTrue(path.exists())
            self.assertTrue(path.is_dir())
            self.assertIn("AgentSocket", str(path))

    def test_state_dir_environment_override(self):
        """Verify AGENTSOCKET_STATE_DIR overrides default location."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGENTSOCKET_STATE_DIR": tmp}):
                resolved = get_state_dir()
                self.assertEqual(resolved, Path(tmp).resolve())
                self.assertTrue(resolved.exists())

    def test_db_path_environment_override(self):
        """Verify AGENTSOCKET_DB_PATH overrides database location."""
        with tempfile.TemporaryDirectory() as tmp:
            custom_db = Path(tmp) / "custom_agentsocket.db"
            with patch.dict(os.environ, {"AGENTSOCKET_DB_PATH": str(custom_db)}):
                self.assertEqual(get_db_path(), custom_db)
                self.assertTrue(custom_db.parent.exists())

    def test_default_logs_dir_resolution_and_override(self):
        """Verify session logs directory defaults to state_dir/logs and respects override."""
        with tempfile.TemporaryDirectory() as tmp:
            # 1. State dir derived logs
            with patch.dict(os.environ, {"AGENTSOCKET_STATE_DIR": tmp}, clear=True):
                logs_dir = get_default_logs_dir()
                self.assertEqual(logs_dir, Path(tmp).resolve() / "logs")
                self.assertTrue(logs_dir.exists())

            # 2. AGENTSOCKET_LOGS_DIR direct override
            custom_logs = Path(tmp) / "custom_logs"
            with patch.dict(os.environ, {"AGENTSOCKET_LOGS_DIR": str(custom_logs)}):
                resolved_logs = get_default_logs_dir()
                self.assertEqual(resolved_logs, custom_logs.resolve())
                self.assertTrue(resolved_logs.exists())

    def test_runtime_artifact_paths(self):
        """Verify artifact paths are anchored to the resolved state directory."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGENTSOCKET_STATE_DIR": tmp}):
                expected_root = Path(tmp).resolve()
                self.assertEqual(get_pid_file_path(), expected_root / ".socket_server.pid")
                self.assertEqual(get_port_file_path(), expected_root / ".socket_server.port")
                self.assertEqual(get_token_file_path(), expected_root / ".socket_server.token")
                self.assertEqual(get_db_path(), expected_root / "agentsocket.db")

    def test_read_only_repo_resilience(self):
        """Verify server boots and manages runtime state without touching REPO_ROOT."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGENTSOCKET_STATE_DIR": tmp}):
                # 1. Write PID, Port, and Token
                write_pid_file()
                write_port_file(9876)
                token = get_or_generate_token()

                # Verify files exist in state directory
                state_pid = get_pid_file_path()
                state_port = get_port_file_path()
                state_token = get_token_file_path()

                self.assertTrue(state_pid.exists())
                self.assertTrue(state_port.exists())
                self.assertTrue(state_token.exists())
                self.assertEqual(state_token.read_text(encoding="utf-8").strip(), token)
                self.assertEqual(state_port.read_text(encoding="utf-8").strip(), "9876")

                # Verify ZERO runtime files written to REPO_ROOT
                repo_pid = Path(REPO_ROOT) / ".socket_server.pid"
                repo_port = Path(REPO_ROOT) / ".socket_server.port"
                repo_token = Path(REPO_ROOT) / ".socket_server.token"
                self.assertFalse(repo_pid.exists(), "Found .socket_server.pid in REPO_ROOT!")
                self.assertFalse(repo_port.exists(), "Found .socket_server.port in REPO_ROOT!")
                self.assertFalse(repo_token.exists(), "Found .socket_server.token in REPO_ROOT!")

                # 2. Initialize Database in isolated state dir
                init_db()
                state_db = get_db_path()
                self.assertTrue(state_db.exists())
                with get_connection() as conn:
                    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    tables = [row[0] for row in cursor.fetchall()]
                    self.assertIn("sessions", tables)
                    self.assertIn("events", tables)
                    self.assertIn("subskills", tables)

                # 3. Clean up runtime artifacts
                remove_pid_file()
                remove_port_file()
                remove_token_file()

                self.assertFalse(state_pid.exists())
                self.assertFalse(state_port.exists())
                self.assertFalse(state_token.exists())

    def test_stale_cleanup_in_isolated_state_dir(self):
        """Verify stale PID and port files in state dir are detected and cleaned."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGENTSOCKET_STATE_DIR": tmp}):
                pid_path = get_pid_file_path()
                port_path = get_port_file_path()

                # Write dummy dead process PID
                pid_path.write_text("99999999", encoding="utf-8")
                port_path.write_text("8005", encoding="utf-8")

                self.assertTrue(pid_path.exists())
                self.assertTrue(port_path.exists())

                clean_stale_pid_file()
                self.assertFalse(pid_path.exists())

                clean_stale_port_file()
                self.assertFalse(port_path.exists())

    def test_pyproject_toml_configuration(self):
        """Verify pyproject.toml PEP 621 compliance, build system, and scripts."""
        pyproject_path = Path(REPO_ROOT) / "pyproject.toml"
        self.assertTrue(pyproject_path.exists(), "pyproject.toml must exist in repo root")

        content = pyproject_path.read_text(encoding="utf-8")
        self.assertIn('name = "agentsocket-browser"', content)
        self.assertIn('version = "1.1.0"', content)
        self.assertIn('build-backend = "hatchling.build"', content)
        self.assertIn('"platformdirs>=4.0.0"', content)
        self.assertIn('agentsocket = "server.socket_launcher:main"', content)
        self.assertIn('browser-socket = "server.socket_launcher:main"', content)
        self.assertIn('packages = ["server"]', content)

    def test_requirements_txt_contains_platformdirs(self):
        """Verify requirements.txt includes platformdirs."""
        req_path = Path(REPO_ROOT) / "requirements.txt"
        self.assertTrue(req_path.exists())
        content = req_path.read_text(encoding="utf-8")
        self.assertIn("platformdirs>=4.0.0", content)

    def test_cli_parser_help_and_commands(self):
        """Verify CLI argument parser defines required commands."""
        parser = build_cli_parser()
        # Verify subcommands exist
        actions = [action.dest for action in parser._actions]
        self.assertIn("command", actions)

        # Parse valid command
        parsed = parser.parse_args(["status"])
        self.assertEqual(parsed.command, "status")

        parsed_plug = parser.parse_args(["plug"])
        self.assertEqual(parsed_plug.command, "plug")


if __name__ == "__main__":
    unittest.main()
