# Quickstart: validating the refactor

These are the scenarios that show the refactor kept behavior the same and produced the three-area layout. Run every command from the repository root.

## Prerequisites

| Scenario | Needs |
|---|---|
| A–D (offline) | `python3` ≥ 3.10; optional `node` for the parity and syntax checks |
| E (local live) | `adb`, `frida`, a booted emulator with `frida-server`, and `aapt` or an explicit package name |
| F (Docker live) | A Linux host with `/dev/kvm`, Docker and Compose |
| Baseline capture | Same as F, **using the pre-refactor commit** (see [research R6](./research.md#r6-proving-behavior-is-preserved-without-existing-reference-logs)) |

## 0. Baseline: once, before any code moves

```bash
git checkout 7936080                               # pre-refactor code (detached), Linux/KVM host
scripts/run-benchmarks-linux.sh
git checkout -                                     # back to the working branch
# copy benchmark-results/<case>/output.log → tests/fixtures/logs/benchmark/<case>.log
git show 7936080:sentry/report.py > /tmp/legacy_report.py
python3 tests/tools/regen_expected.py --legacy /tmp/legacy_report.py
git show 7936080:sentry/hooks/webview.js > tests/fixtures/legacy/webview.js
```

**Expected**:
- `tests/fixtures/expected/<case>/report.{json,md}` exists for every synthetic and benchmark log.
- There is one benchmark log per APK under `Benchmark/`.

## A. Golden reports (SC-001, FR-003, FR-016, FR-017)

```bash
python3 -m unittest tests.test_report_golden -v
```

**Expected**: every case passes, each one compared byte for byte, and the rule-coverage guard reports all 22 rule ids as covered.

## B. Report CLI is unchanged (FR-005)

```bash
python3 sentry/report.py tests/fixtures/logs/synthetic/full.log --json /tmp/r.json --markdown /tmp/r.md
diff /tmp/r.json tests/fixtures/expected/full/report.json && diff /tmp/r.md tests/fixtures/expected/full/report.md
```

**Expected**: the `Generated report: …` line is printed, the exit code is 0 and both diffs are empty.

## C. Bundle and browser parity (FR-004, FR-008, FR-011)

```bash
python3 -m unittest tests.test_agent_bundle tests.test_browser_parity -v
python3 sentry/core/agent/build_agent.py --out /tmp/agent.js && node --check /tmp/agent.js
```

**Expected**:
- Two builds produce identical output.
- The parity test shows the same drained page events for the legacy and the new observer.
- `node --check` reports no syntax errors.

## D. Layering, size and docs (FR-007–FR-015, SC-004, SC-005, SC-006, SC-007)

```bash
python3 -m unittest tests.test_layering_browser tests.test_layering_native tests.test_layering_core tests.test_layering_layout -v
ls sentry/browser sentry/native sentry/core
```

**Expected**:
- Every check passes.
- Exactly the three category directories exist under `sentry/`, next to `Dockerfile` and `report.py`.
- `sentry/hooks/`, `sentry/run.sh` and `run-frida-server/` are gone.

**Manual (SC-005 and SC-006)**:
1. Ask someone unfamiliar with the code to use the READMEs to find where to make each of the four sample changes, and time it.
2. Add a dummy detector to `rules/settings.py`, register it in `rules/__init__.py` and confirm that `git diff --stat` touches only `sentry/core/report/rules/`. Then revert it.

## E. Local live run (US1, SC-002, SC-003)

```bash
SENTRY_RUNNER=local ./analyse.sh Benchmark/JsUpdateCaseF.apk com.example.jsUpdatecaseF
python3 tests/tools/compare_event_streams.py tests/fixtures/logs/benchmark/JsUpdateCaseF.log logs/output.log
```

**Expected**:
- The console messages are the same as before.
- `logs/output.log`, `logs/report.md`, `target/output.log` and `target/report.json` exist.
- The comparator reports no differences in event types or payload keys.
- The findings and risk score are the same as in the expected report for that case.

Also check the error paths:
- `./analyse.sh` with no arguments prints the usage text and exits 1.
- `SENTRY_RUNNER=bogus ./analyse.sh x.apk` prints the invalid-runner error and exits 1.
- Pressing Ctrl-C during a run still generates the report and exits 130.

## F. Docker live run (US1, SC-002)

```bash
SENTRY_RUNNER=docker ./analyse.sh Benchmark/JsUpdateCaseF.apk com.example.jsUpdatecaseF
scripts/run-benchmarks-linux.sh                   # full sweep
```

**Expected**:
- The `sentry` image builds `/sentry/build/agent.js`.
- The `benchmark-results/<case>/` layout and the status values are unchanged.
- The findings and risk score for every case match the baseline.

## G. README commands (SC-003, FR-018)

Run every command block in `README.md` that applies to your host. **Expected**: they all work exactly as written. The new "Project layout" section names `browser/`, `native/` and `core/`.
