"""
AgentSocket - Feature Spec 37 Continuous Integration & Verification Matrix Test Suite 🤖🌐
Validates the GitHub Actions workflow schema, matrix definitions, extension test presence,
development requirements, linter configuration, and documentation updates.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestSpec37CIMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow_file = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        cls.req_dev_file = REPO_ROOT / "requirements-dev.txt"
        cls.pyproject_file = REPO_ROOT / "pyproject.toml"
        cls.contributing_file = REPO_ROOT / "CONTRIBUTING.md"

    def test_ci_workflow_exists_and_valid_yaml(self):
        """Verify .github/workflows/ci.yml exists and has valid YAML syntax."""
        self.assertTrue(self.workflow_file.exists(), "ci.yml workflow must exist")

        with open(self.workflow_file, "r", encoding="utf-8") as f:
            workflow = yaml.safe_load(f)

        self.assertIsInstance(workflow, dict)
        self.assertEqual(workflow.get("name"), "CI Pipeline")

        # Verify triggers
        triggers = workflow.get("on") or workflow.get(True) or {}
        self.assertIn("push", triggers)
        self.assertIn("pull_request", triggers)
        self.assertIn("main", triggers["push"]["branches"])
        self.assertIn("main", triggers["pull_request"]["branches"])

        # Verify concurrency
        concurrency = workflow.get("concurrency", {})
        self.assertTrue(concurrency.get("cancel-in-progress"))

    def test_ci_jobs_declaration(self):
        """Verify all 4 core pipeline jobs are declared with correct dependencies."""
        with open(self.workflow_file, "r", encoding="utf-8") as f:
            workflow = yaml.safe_load(f)

        jobs = workflow.get("jobs", {})
        self.assertIn("lint", jobs)
        self.assertIn("test-python", jobs)
        self.assertIn("test-extension", jobs)
        self.assertIn("package-check", jobs)

        # Dependencies
        self.assertEqual(jobs["test-python"].get("needs"), ["lint"])
        self.assertEqual(jobs["package-check"].get("needs"), ["test-python", "test-extension"])

    def test_cross_platform_and_python_matrix(self):
        """Verify tri-platform OS and Python 3.10-3.14 test matrix configuration."""
        with open(self.workflow_file, "r", encoding="utf-8") as f:
            workflow = yaml.safe_load(f)

        matrix = workflow["jobs"]["test-python"]["strategy"]["matrix"]
        self.assertFalse(workflow["jobs"]["test-python"]["strategy"].get("fail-fast", True))

        # Check OS matrix
        expected_os = {"ubuntu-latest", "windows-latest", "macos-latest"}
        self.assertEqual(set(matrix["os"]), expected_os)

        # Check Python versions (must include 3.10 through 3.14)
        expected_py = {"3.10", "3.11", "3.12", "3.13", "3.14"}
        self.assertEqual(set(matrix["python-version"]), expected_py)

    def test_extension_test_suites_referenced_and_present(self):
        """Verify all 5 Chrome extension JS test suites exist on disk and are in ci.yml."""
        expected_suites = [
            "tests/test_protocol.test.js",
            "tests/test_content_aria.test.js",
            "tests/test_content_atomic_driver.test.js",
            "tests/test_content_hud_ticker.test.js",
            "tests/test_spec32_extension_hud.test.js",
        ]

        # Verify on filesystem
        for suite in expected_suites:
            suite_path = REPO_ROOT / suite
            self.assertTrue(suite_path.exists(), f"Extension test suite missing: {suite}")

        # Verify referenced in workflow
        with open(self.workflow_file, "r", encoding="utf-8") as f:
            content = f.read()
        for suite in expected_suites:
            self.assertIn(suite, content, f"Workflow does not execute: {suite}")

    def test_package_check_job_steps(self):
        """Verify package-check runs build and tests CLI entrypoints."""
        with open(self.workflow_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("python -m build", content)
        self.assertIn("agentsocket --help", content)
        self.assertIn("browser-socket --help", content)

    def test_requirements_dev_txt_contents(self):
        """Verify requirements-dev.txt contains necessary CI dependencies."""
        self.assertTrue(self.req_dev_file.exists(), "requirements-dev.txt must exist")
        content = self.req_dev_file.read_text(encoding="utf-8")

        self.assertIn("-r requirements.txt", content)
        self.assertIn("pytest>=8.0.0", content)
        self.assertIn("httpx>=0.27.0", content)
        self.assertIn("ruff>=0.4.0", content)
        self.assertIn("build>=1.0.0", content)
        self.assertIn("platformdirs>=4.0.0", content)

    def test_contributing_md_ci_updates(self):
        """Verify CONTRIBUTING.md contains the CI badge and updated testing instructions."""
        self.assertTrue(self.contributing_file.exists())
        content = self.contributing_file.read_text(encoding="utf-8")

        self.assertIn("actions/workflows/ci.yml/badge.svg", content)
        self.assertIn("ruff check server tests", content)
        self.assertIn("node tests/test_protocol.test.js", content)
        self.assertIn("node tests/test_spec32_extension_hud.test.js", content)
        self.assertIn("python -m build", content)

    def test_pyproject_toml_ci_configuration(self):
        """Verify pyproject.toml specifies build tool and ruff lint configuration."""
        self.assertTrue(self.pyproject_file.exists())
        content = self.pyproject_file.read_text(encoding="utf-8")

        self.assertIn('"build>=1.0.0"', content)
        self.assertIn("[tool.ruff.lint]", content)

    def test_ruff_lint_passes_cleanly(self):
        """Verify ruff check server tests exits with returncode 0."""
        res = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "server", "tests"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"Ruff linter failed with output:\n{res.stdout}\n{res.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
