#!/usr/bin/env python3
"""Create expected golden reports for every fixture log, using the frozen legacy report generator."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.helpers import EXPECTED_DIR, case_name, iter_logs, normalize_stdout, run_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", type=Path, required=True, help="Path to the legacy report.py oracle.")
    parser.add_argument("--only", action="append", default=[], help="Only regenerate this case (repeatable).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing expected outputs.")
    args = parser.parse_args()

    status = 0
    for log in iter_logs():
        case = case_name(log)
        if args.only and case not in args.only:
            continue
        target = EXPECTED_DIR / case
        if target.exists() and not args.force:
            print(f"skip {case}: expected output exists (use --force)")
            continue

        with tempfile.TemporaryDirectory() as tmp:
            result = run_report(args.legacy, log, Path(tmp))
            if result.returncode != 0:
                print(f"FAIL {case}: legacy exited {result.returncode}\n{result.stderr}", file=sys.stderr)
                status = 1
                continue
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(tmp) / "report.json", target / "report.json")
            shutil.copyfile(Path(tmp) / "report.md", target / "report.md")
            (target / "stdout.txt").write_text(normalize_stdout(result.stdout, Path(tmp)), encoding="utf-8")
        print(f"wrote {case}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
