#!/usr/bin/env python3
"""
Universal Adhoc: Robust Element Click Tool
Locates DOM element, auto-scrolls into view, and dispatches native mouse click events.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

JS_CLICK_TEMPLATE = """
(() => {
    const selector = %s;
    let el = null;
    if (selector.startsWith("//") || selector.startsWith("(//")) {
        const res = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        el = res.singleNodeValue;
    } else {
        el = document.querySelector(selector);
    }

    if (!el) {
        return { status: "error", error: "Element not found: " + selector };
    }

    el.scrollIntoView({ behavior: "instant", block: "center" });
    el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
    el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
    el.click();

    return {
        status: "success",
        selector: selector,
        tag: el.tagName,
        text: el.innerText ? el.innerText.trim().slice(0, 80) : ""
    };
})()
"""


def click_element(
    selector: str,
    wait_seconds: float = 0.5,
    server_url: str = "http://127.0.0.1:8000",
) -> dict:
    js_code = JS_CLICK_TEMPLATE % json.dumps(selector)
    payload = {
        "id": f"click_{int(time.time() * 1000)}",
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
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            if isinstance(data.get("result"), dict) and "output" in data["result"]:
                return data["result"]["output"]
            return data.get("result") or data
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Element Click Adhoc")
    parser.add_argument("selector", help="CSS selector or XPath of element to click")
    parser.add_argument("--wait", type=float, default=0.5, help="Seconds to wait after click")
    parser.add_argument("--server", default=os.environ.get("AGENTSOCKET_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    res = click_element(args.selector, args.wait, args.server)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if isinstance(res, dict) and res.get("status") == "success":
            print(f"🖱️ Clicked {res.get('tag')} ({args.selector}) [text: '{res.get('text')}']")
        else:
            print(f"❌ Click failed: {res.get('error') or res}")
            sys.exit(1)


if __name__ == "__main__":
    main()
