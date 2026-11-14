"""core/report: command-line entry point: read the log, analyze it, write the JSON and Markdown reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.report.analyzer import Analyzer
from core.report.loader import load_events
from core.report.markdown import markdown_report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate WebView security findings from Sentry JSON logs.",
    )
    parser.add_argument("log_file", type=Path, help="Path to the Sentry output log.")
    parser.add_argument(
        "--json",
        dest="json_output",
        type=Path,
        default=Path("target/report.json"),
        help="Path for the machine-readable JSON report.",
    )
    parser.add_argument(
        "--markdown",
        dest="markdown_output",
        type=Path,
        default=Path("logs/report.md"),
        help="Path for the Markdown report.",
    )
    parser.add_argument(
        "--trusted-origin",
        action="append",
        default=[],
        help="Trusted WebView origin, for example https://app.example.com. Can be repeated.",
    )
    parser.add_argument(
        "--static-bridges",
        dest="static_bridges",
        type=Path,
        default=None,
        help="Static bridge discovery artifact (target/static-bridges.json) to compare with the runtime events.",
    )
    return parser


def load_static(path: Path | None) -> dict | None:
    """The parsed artifact, or None (with a warning) when it cannot be used."""
    if path is None:
        return None
    try:
        static = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        reason = "not found"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        reason = "invalid JSON"
    else:
        schema = static.get("schema") if isinstance(static, dict) else None
        if schema == 1:
            return static
        reason = f"unsupported schema {schema}"
    print(f"Warning: ignoring static bridge artifact: {reason}")
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    events, skipped = load_events(args.log_file)
    analyzer = Analyzer(set(args.trusted_origin), static=load_static(args.static_bridges))
    report = analyzer.build_report(events, skipped)

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)

    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown_report(report), encoding="utf-8")

    print(
        "Generated report: "
        f"{args.json_output} and {args.markdown_output} "
        f"({report['summary']['finding_count']} findings, "
        f"risk score {report['summary']['risk_score']}/100)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
