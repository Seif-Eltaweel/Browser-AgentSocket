#!/usr/bin/env python3
"""
Universal Adhoc: Media & Asset Downloader Tool
Downloads files, images, videos, and page assets to a local target folder.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def download_media(
    url: str,
    output_path: str,
    headers: dict[str, str] | None = None,
) -> dict:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            with open(output_path, "wb") as f:
                f.write(data)

        return {
            "status": "success",
            "url": url,
            "output_path": output_path,
            "bytes_downloaded": len(data),
            "content_type": content_type,
        }
    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Media & Asset Downloader")
    parser.add_argument("--url", "-u", required=True, help="URL of media/asset to download")
    parser.add_argument("--output", "-o", required=True, help="Target file path to save downloaded media")
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")
    args = parser.parse_args()

    res = download_media(url=args.url, output_path=args.output)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res.get("status") == "success":
            print(f"📥 Downloaded asset ({res.get('bytes_downloaded')} bytes) to `{res.get('output_path')}`.")
        else:
            print(f"❌ Download failed: {res.get('error')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
