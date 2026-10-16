#!/usr/bin/env bash
# core launcher: keeps scripts/run-benchmarks-linux.sh working; the runner lives in sentry/core/benchmark (Python).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is not installed" >&2; exit 1; }
SENTRY_ROOT="$ROOT" SENTRY_PROG="$(basename "$0")" PYTHONPATH="$ROOT/sentry${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m core.benchmark "$@"
