"""core/report: allow `python3 -m core.report` from the sentry/ directory."""

from core.report.cli import main

raise SystemExit(main())
