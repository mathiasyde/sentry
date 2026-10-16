#!/bin/sh
# core launcher: keeps ./analyse.sh working; the analysis runs in sentry/core/run (Python).
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Sentry - version alpha\n\nError: python3 is not installed\n'
  exit 1
fi
SENTRY_PROG="$0" PYTHONPATH="$(dirname "$0")/sentry${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m core.run "$@"
