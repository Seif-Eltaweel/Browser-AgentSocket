#!/usr/bin/env python3
"""
Universal Adhoc: Safe Browser Navigation Tool
Navigates active browser tab to target URL with load completion and tab group binding.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def navigate(
    url: str,
    session_title: str | None = None,
    requires_privacy_check: bool = False,
    wait_seconds: float = 1.0,
    server_url: str = "http://127.0.0.1:8000",
) -> dict:
    if not url.startswith(("http://", "https://", "chrome://", "about:")):
        url = "https://" + url

    title = session_title or os.environ.get("AGENTSOCKET_SESSION_TITLE", "Browser Task")
    payload = {
        "id": f"nav_{int(time.time() * 1000)}",
        "action_type": "navigate",
        "target_data": url,
        "session_title": title,
        "requires_privacy_check": requires_privacy_check,
    }

    req = urllib.request.Request(
        f"{server_url}/execute",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=35.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            data["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            return data
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return json.loads(err_body)
        except Exception:
            return {"status": "error", "error": f"HTTP {e.code}: {e.reason}", "detail": err_body}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Browser Navigation Adhoc")
    parser.add_argument("url", help="Destination URL (e.g. https://example.com)")
    parser.add_argument("--title", help="Session / Tab Group title", default=None)
    parser.add_argument("--privacy", action="store_true", help="Trigger privacy takeover check")
    parser.add_argument("--wait", type=float, default=1.0, help="Post-navigation wait seconds")
    parser.add_argument("--server", default=os.environ.get("AGENTSOCKET_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    res = navigate(args.url, args.title, args.privacy, args.wait, args.server)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res.get("status") == "success":
            inner_res = res.get("result") or {}
            tab_id = inner_res.get("tabId") if isinstance(inner_res, dict) else None
            group_id = inner_res.get("groupId") if isinstance(inner_res, dict) else None
            print(f"✅ Navigated to {args.url} (Tab: {tab_id}, Group: {group_id}, Latency: {res.get('duration_ms')}ms)")
        elif res.get("status") in ("security_abort", "security_locked"):
            print(f"🔒 Security Lockout: {res.get('message') or res.get('reason')}")
            sys.exit(2)
        else:
            print(f"❌ Navigation failed: {res.get('message') or res.get('error') or res}")
            sys.exit(1)


if __name__ == "__main__":
    main()
