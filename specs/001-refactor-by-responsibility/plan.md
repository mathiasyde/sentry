# Implementation Plan: Refactor Sentry by Responsibility

**Branch**: `001-refactor-by-responsibility` | **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-refactor-by-responsibility/spec.md`

## Summary

This plan reorganizes the Sentry analysis toolchain into three sibling directories under `sentry/`:

- **`browser/`**: code that runs inside WebView pages.
- **`native/`**: Android API hooks in the app process, with one module per API family.
- **`core/`**: the event vocabulary, the agent runtime and bundler, orchestration, the runners, the report pipeline and the benchmark runner.

None of this may change commands, outputs or report content.

The technical approach (details in [research.md](./research.md)):

- A stdlib-only Python **agent bundler** combines the browser, native and core agent sources into one Frida script. This is needed because separate `-l` scripts cannot share state.
- Browser scripts become standalone `.js` files that use placeholder identifiers, rendered at run time with the same `JSON.stringify` escaping as today.
- One JSON **event vocabulary** is shared by the agent and the report.
- The report becomes a package that separates loading, state tracking, detectors, findings and scoring, assembly, Markdown and the CLI.
- The orchestration is Python (R11): a `Host` facade, `Runner` strategies chosen by a factory, an `AnalysisSession` template method and a shared `package.py`. Only the two documented launchers remain as shell.
- Behavior is guarded by **golden reports** (generated with the legacy `report.py` before any code moves), a Node-based browser parity check, an event-stream comparator for live runs, and static layering and size checks.

## Technical Context

**Language/Version**:
- Python 3.10+ (stdlib only) for orchestration, runners, the container entry points and the benchmark runner. `analyse.sh` (POSIX `sh`) and `scripts/run-benchmarks-linux.sh` (`bash`) are launchers of about 5 lines.
- JavaScript for the Frida agent and the page scripts, using the ES2015+ features the current code already uses.
- Python 3.10+ for the report and the bundler (the current code uses `X | None` type hints). The container uses 3.14 and the local host 3.14.5.

**Primary Dependencies**: Frida / `frida-tools` (17.x on the device side, per `docker-compose.yml`), `adb`, Docker Compose, `aapt`. **No new runtime dependencies.** Node is optional and used only by the browser parity test.

**Storage**: Files only: `target/`, `logs/`, `benchmark-results/`, and fixtures under `tests/fixtures/`.

**Testing**: Python `unittest` from the standard library (`python3 -m unittest discover -s tests`). There are golden report comparisons, layering and size checks, a bundler test, and an optional Node `vm` browser parity test. End-to-end checks run in local mode, and in Docker mode on a Linux/KVM host.

**Target Platform**:
- Hosts: macOS and Linux, in local mode; Linux with KVM, in Docker mode.
- Devices: Android emulators and devices running `frida-server`.

**Project Type**: a CLI dynamic-analysis toolchain made of shell orchestration, a Frida agent and a Python report generator.

**Performance Goals**: No regression. Building the bundle adds less than 1 s to each run, and the probe polling rate stays at 1000 ms.

**Constraints**:
- Report output must be identical byte for byte for the same log.
- The same event types and fields must be emitted.
- The documented commands, environment variables, paths and exit codes stay the same.
- The per-run random page namespace is kept.
- The demo `android/` and `web/` directories and the `Benchmark/` folder are not touched.

**Scale/Scope**:
- About 2,850 lines are being moved: `webview.js` (1,294), `report.py` (1,019), `analyse.sh` (214), the benchmark runner (158) and small scripts.
- 16 event types, 7 native hook families and about 6 browser fragments.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the unfilled template, so no principles are ratified. **The gate is N/A and passes by default.** The design still follows the spec's own constraints: no new runtime dependencies, behavior preservation, and one-directional layering.

**Post-design re-check**: still N/A. The one open decision, unifying the shell helpers, was approved on 2026-10-16 (see Complexity Tracking).

## Project Structure

### Documentation (this feature)

```text
specs/001-refactor-by-responsibility/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R10
├── data-model.md        # Phase 1: entities and layering rules
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   ├── cli-analyse.md         # analyse.sh + benchmark runner contract
│   ├── cli-report.md          # report generator CLI + output contract
│   ├── event-vocabulary.md    # event types and payload fields
│   ├── browser-scripts.md     # page-side scripts, placeholders, probe shape
│   └── agent-bundle.md        # bundler manifest, order, output
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks), not created here
```

### Source Code (repository root)

```text
analyse.sh                          # 5-line launcher → python3 -m core.run
docker-compose.yml                  # run-frida-server: context ./sentry, core/runners/container/frida_server.Dockerfile
scripts/run-benchmarks-linux.sh     # 5-line launcher → python3 -m core.benchmark

sentry/
├── Dockerfile                      # COPY browser/ native/ core/; build agent; CMD python3 -m core.runners.container.entry
├── report.py                       # thin launcher → core.report.cli:main
├── browser/                        # runs INSIDE WebView pages (see browser/README.md)
├── native/                         # Frida hooks, one module per API family (see native/README.md)
└── core/
    ├── host.py                     # Facade: env, PATH, platform/KVM, processes, tee
    ├── events/                     # event_types.json (THE vocabulary) + EventType
    ├── agent/                      # manifest.json, build_agent.py, sanitize.js, emitter.js
    ├── run/                        # session.py (Template Method), package.py, workspace.py, reporting.py, __main__.py
    ├── runners/                    # base.py, docker.py, local.py (Strategy), adb.py (Adapter), __init__.py (Factory)
    │   └── container/              # entry.py, frida_server.py, frida_server.Dockerfile
    ├── report/                     # cli, loader, values, urls, tracker, findings, analyzer, assemble, markdown, rules/
    └── benchmark/                  # suite.py (BenchmarkSuite), __main__.py

tests/
├── fixtures/
│   ├── logs/synthetic/*.log        # hand-authored, full branch/rule coverage + empty/malformed
│   ├── logs/benchmark/*.log        # captured with PRE-refactor code (one per Benchmark APK)
│   ├── expected/<case>/report.{json,md}
│   └── legacy/webview.js           # frozen copy for browser parity
├── tools/
│   ├── regen_expected.py
│   └── compare_event_streams.py
├── test_report_golden.py
├── test_agent_bundle.py
├── test_browser_parity.py          # skipped without node
├── test_native_parity.py           # mocked Java runtime; skipped without node
├── test_cli_contract.py  test_events.py  test_package.py  test_extension_point.py
├── test_local_simulation.py  test_runners.py  test_benchmark.py   # fake adb/frida, FakeHost
├── fakes.py
├── layering_helpers.py
└── test_layering_{browser,native,core,layout}.py
```

These are removed once their contents have moved: `sentry/hooks/`, `sentry/run.sh` and `run-frida-server/`.

**Structure Decision**:
- The three category directories are siblings under `sentry/`, as the spec requires (FR-007). They live there because `sentry/` is the Docker build context for the `sentry` service.
- The root entry points (`analyse.sh`, `scripts/run-benchmarks-linux.sh`, `sentry/report.py`) stay as thin launchers that contain no logic, so every documented command still works (FR-001, FR-005, FR-006).
- Tests live outside the three areas.

### Migration order (input for `/speckit-tasks`)

Each step must leave the golden tests passing.

1. **Baseline.** Freeze the legacy `webview.js` and `report.py`. Write the synthetic fixtures. Capture the benchmark logs on Linux/KVM. Generate and commit the expected reports. Add the golden test.
2. **Vocabulary.** Add `core/events/event_types.json` and the Python `EventType`.
3. **Report package.** Extract the report in this order: `values`/`urls`/`loader`, then `markdown`, `assemble`, `findings`, `tracker` and `rules/*`, then `analyzer`, then `cli`. Turn `sentry/report.py` into a launcher.
4. **Bundler.** Write the bundler, the manifest and `core/agent/{sanitize,emitter}.js`. First bundle the *unchanged* `webview.js` body as a single native file to prove the bundled agent behaves the same.
5. **Browser extraction.** Move the code into `browser/`, add `renderBrowserScript`, and add the parity test.
6. **Native split.** Split the native code into the family modules and `main.js`, and fold in the `getenv` shim.
7. **Shell split.** Split the shell into `core/run`, `core/runners` and a shared `package.sh`. Move the benchmark body.
8. **Container wiring.** Update the `Dockerfile`, `entry.sh` and the compose path for `frida-server`.
9. **Layering, size and README checks.** Add the remaining tests, the area READMEs and the root README layout section.
10. **Live verification.** Run the end-to-end checks in local and Docker modes and compare the event streams ([quickstart.md](./quickstart.md)).

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| A new build step (agent bundler) | Frida `-l` scripts do not share globals. Splitting the code into modules needs one combined script. | Separate `-l` files break the shared state. `frida-compile` adds a Node toolchain. |
| Unifying `find_aapt` and the package-name parsing (small behavior deviation, R5) | FR-014 requires one shared helper. The two copies differ today. | Keeping both variants leaves the duplication. **Approved on 2026-10-16** and recorded as the FR-001 exception. |
| Benchmark logs captured before the refactor | FR-017 needs real benchmark coverage, and no captured logs exist. | Synthetic fixtures alone do not cover "every benchmark case". |
