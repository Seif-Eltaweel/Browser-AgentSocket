#!/usr/bin/env python3
"""
Universal Adhoc: Robust Input Writing & Typing Tool
Locates DOM input/textarea/contenteditable elements and simulates complete event cycle.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

JS_WRITE_TEMPLATE = """
(() => {
    const selector = %s;
    const textToType = %s;
    const clearFirst = %s;
    const appendMode = %s;
    const pressEnter = %s;
    const triggerBlur = %s;

    let el = null;
    if (selector.startsWith("//") || selector.startsWith("(//")) {
        const result = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        el = result.singleNodeValue;
    } else {
        el = document.querySelector(selector);
    }

    if (!el) {
        return { status: "error", error: "Element not found for selector: " + selector };
    }

    el.scrollIntoView({ behavior: "instant", block: "center", inline: "nearest" });
    el.focus();
    el.dispatchEvent(new Event("focus", { bubbles: true }));

    const isContentEditable = el.isContentEditable || el.getAttribute("contenteditable") === "true";
    
    if (clearFirst && !appendMode) {
        if (isContentEditable) {
            el.innerText = "";
        } else {
            el.value = "";
        }
        el.dispatchEvent(new Event("input", { bubbles: true }));
    }

    if (isContentEditable) {
        if (appendMode) {
            el.innerText += textToType;
        } else {
            el.innerText = textToType;
        }
    } else {
        if (appendMode) {
            el.value += textToType;
        } else {
            el.value = textToType;
        }
    }

    el.dispatchEvent(new KeyboardEvent("keydown", { key: "Unidentified", bubbles: true }));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent("keyup", { key: "Unidentified", bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));

    if (pressEnter) {
        el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
        el.dispatchEvent(new KeyboardEvent("keypress", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
        el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    }

    if (triggerBlur) {
        el.blur();
        el.dispatchEvent(new Event("blur", { bubbles: true }));
    }

    return {
        status: "success",
        selector: selector,
        tag: el.tagName,
        isContentEditable: isContentEditable,
        current_value: isContentEditable ? el.innerText : el.value
    };
})()
"""


def write_input(
    selector: str,
    text: str,
    clear: bool = True,
    append: bool = False,
    enter: bool = False,
    blur: bool = False,
    server_url: str = "http://127.0.0.1:8000",
) -> dict:
    js_code = JS_WRITE_TEMPLATE % (
        json.dumps(selector),
        json.dumps(text),
        "true" if clear else "false",
        "true" if append else "false",
        "true" if enter else "false",
        "true" if blur else "false",
    )

    payload = {
        "id": f"input_{int(time.time() * 1000)}",
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
            if isinstance(data.get("result"), dict) and "output" in data["result"]:
                return data["result"]["output"]
            return data.get("result") or data
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Input Writing & Typing Adhoc")
    parser.add_argument("selector", help="CSS or XPath selector (e.g. input[name='q'], #email)")
    parser.add_argument("text", help="Text to type into element")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear existing value")
    parser.add_argument("--append", action="store_true", help="Append to existing value")
    parser.add_argument("--enter", action="store_true", help="Press Enter after typing")
    parser.add_argument("--blur", action="store_true", help="Trigger blur after typing")
    parser.add_argument("--server", default=os.environ.get("AGENTSOCKET_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    res = write_input(
        selector=args.selector,
        text=args.text,
        clear=not args.no_clear,
        append=args.append,
        enter=args.enter,
        blur=args.blur,
        server_url=args.server,
    )

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if isinstance(res, dict) and res.get("status") == "success":
            print(f"✍️ Typed '{args.text}' into {res.get('tag')} ({args.selector})")
        else:
            print(f"❌ Failed to type input: {res.get('error') or res}")
            sys.exit(1)


if __name__ == "__main__":
    main()
