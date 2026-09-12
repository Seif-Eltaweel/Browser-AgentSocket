#!/usr/bin/env python3
"""
Universal Adhoc: Structured Data to CSV Exporter Tool
Exports JSON data, lists of dictionaries, or tabular data to CSV.
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import sys


def export_csv(
    data: list[dict] | str,
    output_path: str,
    columns: list[str] | None = None,
) -> dict:
    if isinstance(data, str):
        if os.path.isfile(data):
            with open(data, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(data)

    if isinstance(data, dict):
        # Single record or dict with list under key
        if any(isinstance(v, list) for v in data.values()):
            for v in data.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    data = v
                    break
            else:
                data = [data]
        else:
            data = [data]

    if not isinstance(data, list) or not data:
        return {"status": "error", "message": "No valid list of data records found to export."}

    # Deduce columns
    if not columns:
        cols_ordered = []
        for row in data:
            if isinstance(row, dict):
                for k in row.keys():
                    if k not in cols_ordered:
                        cols_ordered.append(k)
        columns = cols_ordered

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            if isinstance(row, dict):
                clean_row = {}
                for k in columns:
                    v = row.get(k, "")
                    if isinstance(v, (dict, list)):
                        clean_row[k] = json.dumps(v, ensure_ascii=False)
                    else:
                        clean_row[k] = "" if v is None else str(v)
                writer.writerow(clean_row)

    return {
        "status": "success",
        "output_path": output_path,
        "record_count": len(data),
        "columns": columns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Structured Data to CSV Exporter")
    parser.add_argument("--input", "-i", help="Input JSON file path containing list of records")
    parser.add_argument("--data", "-d", help="Raw JSON string")
    parser.add_argument("--output", "-o", required=True, help="Output CSV file path")
    parser.add_argument("--columns", "-c", help="Comma-separated list of column headers")
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")
    args = parser.parse_args()

    raw_data = args.data or args.input
    if not raw_data:
        print("❌ Error: Either --input or --data must be provided.")
        sys.exit(1)

    cols = [c.strip() for c in args.columns.split(",") if c.strip()] if args.columns else None
    res = export_csv(data=raw_data, output_path=args.output, columns=cols)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res.get("status") == "success":
            print(f"📊 Exported {res.get('record_count')} rows to `{res.get('output_path')}`.")
        else:
            print(f"❌ Export failed: {res.get('message') or res.get('error')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
