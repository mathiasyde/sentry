"""core/run: `python3 -m core.run <apk> [<package>]`, invoked by ./analyse.sh."""

from core.run.session import main

raise SystemExit(main())
