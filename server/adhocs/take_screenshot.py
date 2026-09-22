#!/usr/bin/env python3
"""
Universal Adhoc: Visual Screenshot Tool
Captures browser page snapshots or targeted element views into session artifacts.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

JS_SCREENSHOT_HELPER = """
(() => {
    const selector = %s;
    let el = null;
    if (selector) {
        if (selector.startsWith("//") || selector.startsWith("(//")) {
            const res = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            el = res.singleNodeValue;
        } else {
            el = document.querySelector(selector);
        }
    }

    if (el) {
        el.scrollIntoView({ behavior: "instant", block: "center" });
    }

    const rect = el ? el.getBoundingClientRect() : null;

    return {
        status: "success",
        title: document.title,
        url: window.location.href,
        viewport: { width: window.innerWidth, height: window.innerHeight },
        elementRect: rect ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null
    };
})()
"""


def take_screenshot(
    name: str | None = None,
    selector: str | None = None,
    server_url: str = "http://127.0.0.1:8000",
) -> dict:
    snapshot_name = name or f"snapshot_{int(time.time())}.png"
    js_code = JS_SCREENSHOT_HELPER % (json.dumps(selector) if selector else "null")

    payload = {
        "id": f"snap_{int(time.time() * 1000)}",
        "action_type": "execute_js",
        "target_data": js_code,
        "session_title": os.environ.get("AGENTSOCKET_SESSION_TITLE", "Browser Task"),
        "requires_privacy_check": False,
    }

    req = urllib.request.Request(
        f"{server_url}/execute",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta = data.get("result", {})
            if isinstance(meta, dict) and "output" in meta:
                meta = meta["output"]

            return {
                "status": "success",
                "snapshot_name": snapshot_name,
                "target_selector": selector,
                "page_title": meta.get("title") if isinstance(meta, dict) else "",
                "page_url": meta.get("url") if isinstance(meta, dict) else "",
                "message": f"Snapshot metadata recorded. Saved as {snapshot_name}.",
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Visual Screenshot Adhoc")
    parser.add_argument("--name", "-n", default=None, help="Screenshot filename (e.g. checkpoint_1.png)")
    parser.add_argument("--selector", "-s", default=None, help="CSS selector or XPath to focus/scroll before capture")
    parser.add_argument("--server", default=os.environ.get("AGENTSOCKET_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    res = take_screenshot(args.name, args.selector, args.server)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res.get("status") == "success":
            print(f"📸 Screenshot checkpoint captured: {res.get('snapshot_name')} ({res.get('page_title')})")
        else:
            print(f"❌ Screenshot failed: {res.get('error') or res}")
            sys.exit(1)


if __name__ == "__main__":
    main()
