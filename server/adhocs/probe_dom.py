#!/usr/bin/env python3
"""
Universal Adhoc: DOM Tree & Interactive Element Probe Tool
Inspects DOM elements, interactive buttons, form inputs, links, and structure.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

JS_PROBE_TEMPLATE = """
(() => {
    const rootSelector = %s;
    const interactiveOnly = %s;
    const root = rootSelector ? document.querySelector(rootSelector) : document.body;
    if (!root) {
        return { status: "error", message: `Root element '${rootSelector}' not found.` };
    }

    const title = document.title;
    const url = window.location.href;

    const interactiveSelectors = [
        'button', 'a[href]', 'input', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[role="tab"]',
        '[contenteditable="true"]', '[tabindex]:not([tabindex="-1"])'
    ];

    const elements = [];
    const matched = interactiveOnly
        ? Array.from(root.querySelectorAll(interactiveSelectors.join(', ')))
        : Array.from(root.querySelectorAll('h1, h2, h3, p, button, a[href], input, select, textarea, form, [role="button"]'));

    for (const el of matched.slice(0, 100)) {
        const tag = el.tagName.toLowerCase();
        const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 100);
        const id = el.id ? `#${el.id}` : '';
        const classes = el.className && typeof el.className === 'string'
            ? '.' + el.className.trim().split(/\\s+/).slice(0, 3).join('.')
            : '';
        const role = el.getAttribute('role') || '';
        const href = el.getAttribute('href') || '';
        const inputType = el.getAttribute('type') || '';

        elements.push({
            tag,
            selector: `${tag}${id}${classes}`,
            text,
            role: role || undefined,
            href: href || undefined,
            type: inputType || undefined
        });
    }

    return {
        status: "success",
        url,
        title,
        element_count: elements.length,
        elements
    };
})()
"""


def probe_dom(
    selector: str = "body",
    interactive_only: bool = True,
    server_url: str = "http://127.0.0.1:8000",
) -> dict:
    js_code = JS_PROBE_TEMPLATE % (json.dumps(selector), "true" if interactive_only else "false")
    payload = {
        "id": f"probe_{int(time.time() * 1000)}",
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
    parser = argparse.ArgumentParser(description="Universal DOM Tree & Selector Probe")
    parser.add_argument("--selector", default="body", help="Root CSS selector to probe")
    parser.add_argument("--all", action="store_true", help="Probe all content elements instead of interactive only")
    parser.add_argument("--server", default=os.environ.get("AGENTSOCKET_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    res = probe_dom(
        selector=args.selector,
        interactive_only=not args.all,
        server_url=args.server,
    )

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if isinstance(res, dict) and res.get("status") == "success":
            print(f"🔍 Probed DOM '{res.get('title')}' ({res.get('element_count')} elements found):")
            for el in res.get("elements", []):
                extra = f" -> {el['href']}" if el.get("href") else ""
                print(f"  • [{el.get('tag').upper()}] {el.get('selector')} : \"{el.get('text')}\"{extra}")
        else:
            print(f"❌ DOM probe failed: {res.get('error') or res.get('message') or res}")
            sys.exit(1)


if __name__ == "__main__":
    main()
