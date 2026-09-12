#!/usr/bin/env python3
"""
Universal Adhoc: Page & Feed Scroller Tool
Controls smooth directional scrolling, feed pagination, and bottom detection.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

JS_SCROLL_TEMPLATE = """
(() => {
    const direction = %s;
    const distance = %d;

    const initialY = window.scrollY;
    const maxScrollY = Math.max(
        document.body.scrollHeight, document.documentElement.scrollHeight,
        document.body.offsetHeight, document.documentElement.offsetHeight,
        document.body.clientHeight, document.documentElement.clientHeight
    ) - window.innerHeight;

    if (direction === "bottom") {
        window.scrollTo({ top: maxScrollY, behavior: "smooth" });
    } else if (direction === "top") {
        window.scrollTo({ top: 0, behavior: "smooth" });
    } else if (direction === "up") {
        window.scrollBy({ top: -distance, behavior: "smooth" });
    } else {
        window.scrollBy({ top: distance, behavior: "smooth" });
    }

    const newY = window.scrollY;
    const isBottom = (window.innerHeight + window.scrollY) >= (document.body.scrollHeight - 50);

    return {
        status: "success",
        direction: direction,
        distance: distance,
        initialScrollY: initialY,
        currentScrollY: newY,
        maxScrollY: maxScrollY,
        reachedBottom: isBottom
    };
})()
"""


def scroll_page(
    direction: str = "down",
    distance: int = 800,
    repeats: int = 1,
    pause: float = 1.0,
    server_url: str = "http://127.0.0.1:8000",
) -> dict:
    js_code = JS_SCROLL_TEMPLATE % (json.dumps(direction), distance)

    last_res = {}
    for i in range(repeats):
        payload = {
            "id": f"scroll_{int(time.time() * 1000)}",
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
                    last_res = data["result"]["output"]
                else:
                    last_res = data.get("result") or data
        except Exception as e:
            return {"status": "error", "error": str(e)}

        if i < repeats - 1 and pause > 0:
            time.sleep(pause)

    return last_res


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Page & Feed Scroller Adhoc")
    parser.add_argument("--direction", choices=["down", "up", "top", "bottom"], default="down", help="Scroll direction")
    parser.add_argument("--distance", type=int, default=800, help="Scroll distance in pixels")
    parser.add_argument("--repeat", type=int, default=1, help="Number of times to repeat scroll")
    parser.add_argument("--pause", type=float, default=1.0, help="Pause seconds between repeats")
    parser.add_argument("--server", default=os.environ.get("AGENTSOCKET_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    res = scroll_page(
        direction=args.direction,
        distance=args.distance,
        repeats=args.repeat,
        pause=args.pause,
        server_url=args.server,
    )

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if isinstance(res, dict) and res.get("status") == "success":
            print(f"📜 Scrolled {args.direction} ({args.distance}px, {args.repeat}x). Reached bottom: {res.get('reachedBottom')}")
        else:
            print(f"❌ Scroll failed: {res.get('error') or res}")
            sys.exit(1)


if __name__ == "__main__":
    main()
