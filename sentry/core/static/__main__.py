"""core/static: `python3 -m core.static <apk> [--out PATH]`, the standalone bridge scanner."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from core.static import discover_bridges, failed_result, summary_line


def to_json(result: dict) -> str:
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m core.static", description="Find JavaScript bridges in an APK.")
    parser.add_argument("apk", type=Path, help="APK file to scan.")
    parser.add_argument("--out", type=Path, help="Write the JSON artifact here instead of stdout.")
    args = parser.parse_args(argv)
    if not args.apk.is_file():
        print(f"Error: file not found: {args.apk}")
        return 1

    started = time.monotonic()
    try:
        result, code = discover_bridges(args.apk), 0
    except Exception as exc:  # the artifact records the failure
        result, code = failed_result(args.apk, exc, time.monotonic() - started), 2

    if args.out is None:
        sys.stdout.write(to_json(result))
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(to_json(result), encoding="utf-8")
        print(summary_line(result, str(args.out)) if code == 0 else f"Warning: static bridge discovery failed: {result['error']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
