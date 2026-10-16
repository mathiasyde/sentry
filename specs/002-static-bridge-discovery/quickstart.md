# Quickstart: validating static bridge discovery

Run everything from the repository root. Scenarios 1 to 4 need no device. Scenarios 5 and 6 need a working local or Docker runner.

## 0. Test suite

```bash
python3 -m unittest discover -s tests -t .
```

Expected: everything passes. The existing `tests/fixtures/expected/synthetic__*` goldens are unchanged (SC-004). The new `test_static_benchmarks` checks all eight `Benchmark/*.apk` files against `tests/fixtures/static/ground_truth.json` (SC-001, SC-002) within the time budget (SC-003).

## 1. Standalone scan of a benchmark APK

```bash
PYTHONPATH=sentry python3 -m core.static Benchmark/strongUpdate.apk | python3 -m json.tool | head -60
```

Expected:
- `status: "completed"`;
- one registration with `name: "Android"`, `class_name: "com.example.strongupdate.BridgeClass"` and `class_resolution: "exact"`;
- its methods include `showData`.

Repeat with `Benchmark/JsUpdateCaseF.apk`. Expected: `class_name` is `com.example.jsUpdatecaseF.MainActivity`, with method `getData`. Use the exact package casing found in the APK.

## 2. Timing

```bash
time PYTHONPATH=sentry python3 -m core.static Benchmark/JSUpdateCaseD.apk --out /tmp/sb.json
```

Expected: under 30 s (target under 10 s), followed by a one-line summary.

## 3. Failure isolation (SC-005)

```bash
head -c 4096 Benchmark/strongUpdate.apk > /tmp/broken.apk
PYTHONPATH=sentry python3 -m core.static /tmp/broken.apk; echo "exit=$?"
```

Expected: JSON with `status: "failed"` and a non-empty `error`, then `exit=2`. Within `analyse.sh`, the same failure prints the `Warning:` line, and the run carries on.

## 4. Option parsing (no device needed)

```bash
./analyse.sh                                            # usage now has an "Options:" line, exit 1
./analyse.sh --discover-bridge-interfaces=maybe x.apk   # invalid value error, exit 1, target/ untouched
./analyse.sh --no-discover-bridge-interfaces missing.apk # "File not found: missing.apk", exit 1
```

## 5. End-to-end with discovery on (default)

```bash
SENTRY_RUNNER=local ./analyse.sh Benchmark/strongUpdate.apk com.example.strongupdate
```

Expected:
- A `Static bridge discovery: 1 registration(s), 0 with unresolved names, 1 bridge class(es) -> target/static-bridges.json` line before the runner starts.
- `target/report.json` has a `static_bridges` key.
- `logs/report.md` has a `## Static Bridge Inventory` section, showing `Android` as `[static+runtime]` if the run reached `loadWeb()`, or `[static-only]` with a `WV-STATIC-BRIDGE-UNOBSERVED` info finding if it did not (US2).

## 6. End-to-end with discovery off (US3, FR-016)

```bash
SENTRY_RUNNER=local ./analyse.sh --no-discover-bridge-interfaces Benchmark/strongUpdate.apk com.example.strongupdate
```

Expected: no discovery line, no `target/static-bridges.json`, and no `static_bridges` key or Markdown section. The output matches a run from before this feature.

## 7. Report-only check with a synthetic artifact

```bash
PYTHONPATH=sentry python3 -m core.report tests/fixtures/logs/synthetic/bridge.log \
  --static-bridges tests/fixtures/static/synthetic_mixed.json --json /tmp/r.json --markdown /tmp/r.md
```

Expected:
- With `synthetic_mixed.json`: two `static+runtime` entries (one of them an unresolved name matched by class) and one `static-only` entry, plus exactly one `WV-STATIC-BRIDGE-UNOBSERVED` finding.
- With `synthetic_inventory.json`: the `runtime-only` entries.
- In both cases, the `risk_score` equals the run without `--static-bridges`.

## Results (2026-10-16, macOS, Python 3.14)

- Scenarios 0 to 4 and 7: pass. `test_report_golden.test_benchmark_logs_complete` was already failing before this feature: it needs device captures from feature 001.
- Scenario 2 timing: 0.09 to 0.10 s for each of the 8 benchmark APKs, against a 30 s budget.
- Scenarios 5 and 6 (end-to-end with an emulator): **not run**, because no device or emulator was available in this session.
