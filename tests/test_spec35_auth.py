"""
Unit and Integration Tests for Feature Spec 35:
Transport, Gateway Hardening & Historical Secret Sanitization 🛡️🔐
"""

import os
import subprocess
import unittest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server.socket_server import app, state

client = TestClient(app)


class TestSpec35TransportHardening(unittest.TestCase):
    def setUp(self):
        state.server_token = "test_spec35_gateway_token_abcdef123456"

    def test_api_token_cross_origin_blocked(self):
        """Verify cross-origin web requests to /api/token are rejected with 403."""
        # 1. GET with web Origin header
        response = client.get(
            "/api/token",
            headers={"Origin": "http://localhost:3000"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("error"), "Origin access forbidden")
        self.assertNotIn("access-control-allow-origin", response.headers)

        # 2. Preflight OPTIONS request with web Origin
        options_resp = client.options(
            "/api/token",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        self.assertEqual(options_resp.status_code, 403)
        self.assertNotIn("access-control-allow-origin", options_resp.headers)

        # 3. GET with Sec-Fetch-Site cross-site
        cross_site_resp = client.get(
            "/api/token",
            headers={"Sec-Fetch-Site": "cross-site"}
        )
        self.assertEqual(cross_site_resp.status_code, 403)
        self.assertEqual(cross_site_resp.json().get("error"), "Cross-origin access forbidden")

    def test_api_token_direct_loopback_allowed(self):
        """Verify direct process loopback without cross-origin headers can read token."""
        # 1. Direct loopback request (no Origin header, no Sec-Fetch-Site)
        response = client.get("/api/token")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("token"), "test_spec35_gateway_token_abcdef123456")

        # 2. Request with authorized extension origin
        ext_response = client.get(
            "/api/token",
            headers={"Origin": "chrome-extension://abcdefghijklmnop"}
        )
        self.assertEqual(ext_response.status_code, 200)
        self.assertEqual(ext_response.json().get("token"), "test_spec35_gateway_token_abcdef123456")

    def test_ws_extension_rejects_unauthenticated_connection(self):
        """Verify /ws/extension closes unauthenticated connection with code 1008."""
        unauth_client = TestClient(app)
        with self.assertRaises(WebSocketDisconnect) as cm:
            with unauth_client.websocket_connect("/ws/extension"):
                pass
        self.assertEqual(cm.exception.code, 1008)

    def test_ws_extension_rejects_spoofed_origin_without_token(self):
        """Verify /ws/extension closes connection even if Origin is chrome-extension://."""
        spoofed_client = TestClient(app)
        with self.assertRaises(WebSocketDisconnect) as cm:
            with spoofed_client.websocket_connect(
                "/ws/extension",
                headers={"Origin": "chrome-extension://fake-extension-id"}
            ):
                pass
        self.assertEqual(cm.exception.code, 1008)

    def test_ws_extension_accepts_valid_token(self):
        """Verify /ws/extension accepts connection with valid token parameter or header."""
        authed_client = TestClient(app)
        # 1. Query parameter authentication
        with authed_client.websocket_connect(f"/ws/extension?token={state.server_token}") as ws:
            self.assertIsNotNone(state.extension_ws)

        # 2. Header authentication
        with authed_client.websocket_connect(
            "/ws/extension",
            headers={"X-AgentSocket-Token": state.server_token}
        ) as ws:
            self.assertIsNotNone(state.extension_ws)

    def test_no_hardcoded_paths_in_repo(self):
        """Verify no files in the tracked repository contain author-specific paths."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            tracked_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        except Exception:
            self.skipTest("git command unavailable to list tracked files")

        matches = []
        forbidden_patterns = ["Users/20106", r"Users\20106", "20106"]

        for rel_path in tracked_files:
            # Skip this test file itself when scanning for pattern constants
            if rel_path.replace("\\", "/").endswith("test_spec35_auth.py"):
                continue

            full_path = os.path.join(repo_root, rel_path)
            if not os.path.isfile(full_path):
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    for pat in forbidden_patterns:
                        if pat in content:
                            matches.append(f"{rel_path}: contains '{pat}'")
            except Exception:
                pass

        self.assertEqual(
            len(matches),
            0,
            f"Found forbidden hardcoded author machine paths in tracked files:\n" + "\n".join(matches)
        )


if __name__ == "__main__":
    unittest.main()
