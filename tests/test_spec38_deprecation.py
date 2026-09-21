"""Unit and integration tests for Spec 38: Legacy Deprecation & Canonical Branding Unification.

Verifies:
1. Formal retirement of /adhocs/run and /adhocs/resolve (HTTP 410 Gone).
2. Clean FastMCP tool introspection (zero deprecated adhoc execution tools).
3. PEP 257 docstring compliance and removal of scratch notes/typos in server/models.py.
4. Skill definition portability (zero hardcoded developer paths).
5. Canonical repository branding and test badge accuracy across documentation.
"""

from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

from server.models import ActionType, AgentActionPayload, ErrorCode, ResponseStatus
from server.socket_server import app
from server import socket_mcp

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSpec38DeprecationAndUnification(unittest.TestCase):
    """Test suite verifying legacy deprecation and canonical branding unification."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_adhocs_run_endpoint_returns_410_gone(self):
        """Test POST /adhocs/run returns HTTP 410 Gone with migration guidance."""
        payload = {
            "tool_name": "test_scraper.py",
            "session_path": "server/logs/test_session",
            "args": ["--help"],
        }
        response = self.client.post("/adhocs/run", json=payload)
        self.assertEqual(response.status_code, 410)
        data = response.json()
        self.assertEqual(data.get("status"), "deprecated")
        error = data.get("error", {})
        self.assertEqual(error.get("code"), "ENDPOINT_RETIRED")
        message = error.get("message", "")
        self.assertIn("retired", message.lower())
        self.assertIn("browser_observe", message)
        self.assertIn("browser_click", message)
        self.assertIn("browser_type", message)

    def test_adhocs_resolve_endpoint_returns_410_gone(self):
        """Test GET /adhocs/resolve returns HTTP 410 Gone with migration guidance."""
        response = self.client.get("/adhocs/resolve?tool_name=test_scraper.py")
        self.assertEqual(response.status_code, 410)
        data = response.json()
        self.assertEqual(data.get("status"), "deprecated")
        error = data.get("error", {})
        self.assertEqual(error.get("code"), "ENDPOINT_RETIRED")
        message = error.get("message", "")
        self.assertIn("retired", message.lower())
        self.assertIn("browser_observe", message)
        self.assertIn("browser_click", message)

    def test_adhocs_authenticated_requests_still_return_410(self):
        """Test that even with valid X-AgentSocket-Token header, /adhocs/run and /adhocs/resolve return 410 Gone."""
        from server.socket_server import state

        state.server_token = "secret-token-spec38"
        headers = {"X-AgentSocket-Token": "secret-token-spec38"}

        res_run = self.client.post(
            "/adhocs/run",
            json={"tool_name": "test.py", "session_path": "logs/test", "args": []},
            headers=headers,
        )
        self.assertEqual(res_run.status_code, 410)
        self.assertEqual(res_run.json().get("error", {}).get("code"), "ENDPOINT_RETIRED")

        res_resolve = self.client.get("/adhocs/resolve?tool_name=test.py", headers=headers)
        self.assertEqual(res_resolve.status_code, 410)
        self.assertEqual(res_resolve.json().get("error", {}).get("code"), "ENDPOINT_RETIRED")

    def test_mcp_introspection_excludes_retired_adhoc_tools(self):
        """Test that MCP server registry does not expose retired adhoc tools."""
        # Check registered tool names on socket_mcp.server
        tool_names = [tool.name for tool in socket_mcp.server._tools.values()] if hasattr(socket_mcp.server, "_tools") else []
        
        self.assertNotIn("socket_run_adhoc", tool_names)
        self.assertNotIn("socket_promote_adhoc", tool_names)
        self.assertNotIn("socket_list_adhocs", tool_names)

        # Also verify functions do not exist as callable tool definitions in the module
        self.assertFalse(hasattr(socket_mcp, "socket_run_adhoc"))
        self.assertFalse(hasattr(socket_mcp, "socket_promote_adhoc"))
        self.assertFalse(hasattr(socket_mcp, "socket_list_adhocs"))

    def test_models_docstring_professionalization(self):
        """Test that models.py contains professional docstrings without informal comments or typos."""
        models_path = os.path.join(REPO_ROOT, "server", "models.py")
        with open(models_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Verify old scratch typos are eliminated
        typos = ["commaned", "excuted", "responces", "who is in control", "aka functioning as both"]
        for typo in typos:
            self.assertNotIn(typo.lower(), content.lower(), f"Residual scratch note or typo found: '{typo}'")

        # Verify key models have proper docstrings
        self.assertTrue(AgentActionPayload.__doc__ and len(AgentActionPayload.__doc__.strip()) > 10)
        self.assertTrue(ResponseStatus.__doc__ and len(ResponseStatus.__doc__.strip()) > 10)
        self.assertTrue(ErrorCode.__doc__ and len(ErrorCode.__doc__.strip()) > 10)
        self.assertTrue(ActionType.__doc__ and len(ActionType.__doc__.strip()) > 10)

    def test_skill_definitions_portability(self):
        """Test that root SKILL.md and workspace SKILL.md contain zero hardcoded developer paths."""
        skill_paths = [
            os.path.join(REPO_ROOT, "SKILL.md"),
            os.path.join(REPO_ROOT, ".agents", "skills", "browser-socket", "SKILL.md"),
        ]

        for path in skill_paths:
            self.assertTrue(os.path.isfile(path), f"Skill file missing: {path}")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertNotIn("c:/users", content.lower(), f"Hardcoded developer path found in {path}")
            self.assertNotIn("c:\\users", content.lower(), f"Hardcoded developer path found in {path}")
            self.assertIn("agentsocket", content)
            self.assertIn("-m", content)
            self.assertIn("server.socket_mcp", content)

    def test_repository_branding_unification(self):
        """Test that public documentation and package metadata use canonical branding without legacy references."""
        check_files = [
            os.path.join(REPO_ROOT, "README.md"),
            os.path.join(REPO_ROOT, "INSTALL.md"),
            os.path.join(REPO_ROOT, "CONTRIBUTING.md"),
            os.path.join(REPO_ROOT, "pyproject.toml"),
            os.path.join(REPO_ROOT, "docs", "codebase_master_specification.md"),
        ]

        for path in check_files:
            self.assertTrue(os.path.isfile(path), f"File missing: {path}")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertNotIn(
                "agent_bro_hands",
                content,
                f"Legacy repository name 'agent_bro_hands' found in {os.path.relpath(path, REPO_ROOT)}",
            )

        # Verify Browser-AgentSocket repository URLs
        with open(os.path.join(REPO_ROOT, "pyproject.toml"), "r", encoding="utf-8") as f:
            pyproject_content = f.read()
        self.assertIn("https://github.com/Seif-Eltaweel/Browser-AgentSocket", pyproject_content)

        with open(os.path.join(REPO_ROOT, "README.md"), "r", encoding="utf-8") as f:
            readme_content = f.read()
        self.assertIn("https://github.com/Seif-Eltaweel/Browser-AgentSocket", readme_content)

    def test_readme_test_badge_accuracy(self):
        """Test that README.md badge reflects passing test count."""
        readme_path = os.path.join(REPO_ROOT, "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("tests-171", content, "README test badge does not reflect passing test count.")
        self.assertNotIn("tests-44", content, "Outdated 44/44 test badge remains in README.md.")


if __name__ == "__main__":
    unittest.main()
