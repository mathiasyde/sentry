#!/usr/bin/env python3
"""core launcher: keeps `python3 sentry/report.py` working; all logic lives in core/report/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.report.cli import main  # noqa: E402

raise SystemExit(main())
