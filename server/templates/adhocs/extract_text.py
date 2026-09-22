#!/usr/bin/env python3
"""
Universal Adhoc: Text & Attribute Extraction Tool
Scrapes text content, HTML attributes, or lists of elements from any web page.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

JS_EXTRACT_TEMPLATE = """
(() => {
    const selector = %s;
    const attrName = %s;
    const multiple = %s;
    const trimText = %s;

    function getVal(el) {
        if (!el) return null;
        if (attrName) {
            return el.getAttribute(attrName);
        }
        let txt = el.innerText || el.textContent || "";
        return trimText ? txt.trim() : txt;
    }

    if (multiple) {
        let elements = [];
        if (selector.startsWith("//") || selector.startsWith("(//")) {
            const iter = document.evaluate(selector, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
            for (let i = 0; i < iter.snapshotLength; i++) {
                elements.push(iter.snapshotItem(i));
            }
        } else {
            elements = Array.from(document.querySelectorAll(selector));
        }

        const items = elements.map(el => getVal(el)).filter(v => v !== null && v !== "");
        return {
            status: "success",
            selector: selector,
            multiple: true,
            count: items.length,
            result: items
        };
    } else {
        let el = null;
        if (selector.startsWith("//") || selector.startsWith("(//")) {
            const res = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            el = res.singleNodeValue;
        } else {
            el = document.querySelector(selector);
        }

        if (!el) {
            return { status: "error", error: "Element not found for selector: " + selector };
        }

        const val = getVal(el);
        return {
            status: "success",
            selector: selector,
            multiple: false,
            tag: el.tagName,
            result: val
        };
    }
})()
"""


def extract_text(
    selector: str,
    attr: str | None = None,
    multiple: bool = False,
    trim: bool = True,
    server_url: str = "http://127.0.0.1:8000",
) -> dict:
    js_code = JS_EXTRACT_TEMPLATE % (
        json.dumps(selector),
        json.dumps(attr) if attr else "null",
        "true" if multiple else "false",
        "true" if trim else "false",
    )

    payload = {
        "id": f"ext_{int(os.getpid())}",
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
    parser = argparse.ArgumentParser(description="Universal Text & Attribute Extraction Adhoc")
    parser.add_argument("selector", help="CSS selector or XPath to extract from")
    parser.add_argument("--attr", help="Attribute name to extract (e.g. href, src, data-id)")
    parser.add_argument("--multiple", action="store_true", help="Extract from all matching elements")
    parser.add_argument("--no-trim", action="store_true", help="Do not trim whitespace")
    parser.add_argument("--server", default=os.environ.get("AGENTSOCKET_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    res = extract_text(
        selector=args.selector,
        attr=args.attr,
        multiple=args.multiple,
        trim=not args.no_trim,
        server_url=args.server,
    )

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if isinstance(res, dict) and res.get("status") == "success":
            val = res.get("result")
            if isinstance(val, list):
                print(f"📋 Extracted {len(val)} items ({args.selector}):")
                for item in val:
                    print(f"  • {item}")
            else:
                print(f"📋 Extracted ({args.selector}): {val}")
        else:
            print(f"❌ Extraction failed: {res.get('error') or res}")
            sys.exit(1)


if __name__ == "__main__":
    main()
