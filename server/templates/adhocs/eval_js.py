#!/usr/bin/env python3
"""
Universal Adhoc: JavaScript Evaluator Tool
Executes arbitrary JavaScript code strings or script files in the active tab context.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def eval_js(
    code: str,
    server_url: str = "http://127.0.0.1:8000",
) -> dict:
    payload = {
        "id": f"eval_{int(os.getpid())}",
        "action_type": "execute_js",
        "target_data": code,
        "session_title": os.environ.get("AGENTSOCKET_SESSION_TITLE", "Browser Task"),
        "requires_privacy_check": False,
    }

    req = urllib.request.Request(
        f"{server_url}/execute",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data.get("result"), dict) and "output" in data["result"]:
                return {"status": "success", "result": data["result"]["output"]}
            return {"status": "success", "result": data.get("result")}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal JavaScript Evaluator Adhoc")
    parser.add_argument("code", nargs="?", default=None, help="JavaScript code string to evaluate")
    parser.add_argument("--file", "-f", help="Path to JavaScript file to execute")
    parser.add_argument("--server", default=os.environ.get("AGENTSOCKET_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    js_code = args.code
    if args.file:
        if not os.path.exists(args.file):
            print(f"❌ Error: Script file not found: {args.file}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as sf:
            js_code = sf.read()

    if not js_code:
        print("❌ Error: Must provide code string or --file script.js")
        parser.print_help()
        sys.exit(1)

    res = eval_js(js_code, args.server)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res.get("status") == "success":
            out = res.get("result")
            if isinstance(out, (dict, list)):
                print(json.dumps(out, indent=2))
            else:
                print(f"⚡ JS Result: {out}")
        else:
            print(f"❌ JS Evaluation error: {res.get('error') or res}")
            sys.exit(1)


if __name__ == "__main__":
    main()
