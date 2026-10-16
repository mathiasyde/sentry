"""core/benchmark: `python3 -m core.benchmark [benchmark-dir]`, invoked by scripts/run-benchmarks-linux.sh."""

from core.benchmark.suite import main

raise SystemExit(main())
