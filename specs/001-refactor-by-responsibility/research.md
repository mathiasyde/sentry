# Research: Refactor Sentry by Responsibility

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-10-16

This file records each design decision in the order it came up. Every entry gives the decision, the reason for it, and the alternatives that were rejected.

---

## R1. How to load instrumentation that is split across many files

**Context**: Today Frida loads two scripts with `-l webview.js -l getenv.js`. Each `-l` becomes a **separate Frida script with its own global scope**, so files loaded that way cannot share state. The WebView hooks need shared state across all families: the WebView registry, the message queue, the bridge maps and the random namespace. Splitting `webview.js` into one `-l` file per family would therefore break it.

**Decision**: Add a small, dependency-free **agent bundler**, `sentry/core/agent/build_agent.py`, written with the Python standard library only. It reads an ordered manifest (`sentry/core/agent/manifest.json`) and produces **one** script, `agent.js`, which contains:

1. a generated header with the event vocabulary (`const EVENT_TYPE = Object.freeze({...})`) taken from `core/events/event_types.json` (see R3);
2. the browser-side sources from `sentry/browser/` embedded as JSON string literals in `const BROWSER_SOURCES = {...}` (see R2);
3. the core agent runtime (`core/agent/sanitize.js`, `core/agent/emitter.js`);
4. the native modules from `sentry/native/`, concatenated in manifest order, ending with `native/main.js`.

Before writing the output, the bundler fails if two files declare the same top-level name. Both runners load only the generated file:

- local mode: `-l ./target/agent.js`, built on every run;
- container mode: `-l /sentry/build/agent.js`, built when the image is built.

**Rationale**:
- No new runtime dependencies: `python3` is already required by `analyse.sh`, and the `sentry` image is based on `python:3.14-slim`.
- The output is deterministic, so it is easy to diff and to inspect when debugging.
- One script keeps all the shared state in one scope, exactly as now.

**Alternatives considered**:
- *Several `-l` scripts that share state through `globalThis`*: rejected. Each Frida script has its own isolated global, so cross-script sharing is not reliable.
- *`frida-compile` with ES modules*: rejected. It adds a Node/npm build toolchain (or depends on Frida's built-in compiler being present in every environment), and it cannot import page scripts as text without a loader plugin.
- *Keeping a single hand-written `webview.js`*: rejected, because it fails FR-008 and FR-009.

---

## R2. Keeping browser-side code as standalone files

**Context**: The in-page observer, the bridge-taint wrapper call and the probe currently exist only as template strings inside `webview.js` (`buildInjectionScript`, `buildBridgeTaintScript`, `buildProbeScript`). Run-time values are spliced in with `${JSON.stringify(...)}`.

**Decision**:
- Move each page-side script into its own file under `sentry/browser/`.
- Write runtime values as **placeholder identifiers**: `__SENTRY_NAMESPACE__`, `__SENTRY_WEBVIEW_ID__`, `__SENTRY_INTERFACE_NAME__`, `__SENTRY_METHOD_NAME__`, `__SENTRY_SOURCE__`. Identifiers keep each file syntactically valid JavaScript, so it can be read and linted on its own.
- Split the in-page observer into ordered fragments under `browser/observer/` (`00_namespace.js` … `50_bridge_wrapper.js`). The bundler concatenates them into one closure. The observer has to stay a single IIFE because all fragments share its `state`.
- At run time, `native/browser_delivery.js` renders a script with `renderBrowserScript(name, values)`. That function replaces each placeholder with `JSON.stringify(value)`, the same encoding as today.

**Rationale**:
- This meets FR-008: browser code becomes standalone content and is no longer text embedded inside native code.
- Using `JSON.stringify` for substitution keeps the escaping exactly as it is today.
- The random per-run namespace is still generated natively when the agent starts, so page scripts still cannot predict it (spec edge case).

**Alternatives considered**:
- *`${...}` template syntax kept inside the `.js` files*: rejected, because the files would no longer parse as JavaScript.
- *Mustache-style `{{ }}` tokens*: rejected for the same reason.
- *One file per page-side API family*: this is effectively adopted through the observer fragments: namespace and buffer, serialization, taint, intercepts, storage, bridge wrapper.

---

## R3. A single event vocabulary shared by the agent (JavaScript) and the report (Python)

**Decision**:
- `sentry/core/events/event_types.json` is the only definition of the event vocabulary. It maps each constant name to its wire string, for example `"URL_LOADED": "url.loaded"`.
- The bundler generates the `EVENT_TYPE` object for the agent from this file.
- `core/events/__init__.py` loads the same file and exposes `EventType.URL_LOADED` and the other constants. The report's event dispatch uses these constants instead of string literals.
- The per-type payload fields are documented in [contracts/event-vocabulary.md](./contracts/event-vocabulary.md). The report keeps reading payloads with `.get()`, as it does now.

**Rationale**:
- This meets FR-011. JSON can be read by both languages with no extra dependencies.
- Only the browser layer emits page events (`name`/`arguments`), and those are not vocabulary types. Native wraps them in `js.probe` events. So the browser layer does not need the vocabulary, which keeps the rule that browser code depends on nothing else (FR-012).

**Alternatives**:
- *A Python module that generates JS*: same effect, but it is harder for maintainers working on the JS side to read.
- *A JSON Schema of the payloads, validated in tests*: deferred, because it would add rules the current system does not enforce, and this is a pure refactor.

---

## R4. How to split the report generator so that detection is isolated

**Context**: The `Analyzer.observe_*` methods (`report.py:225-810`) interleave state updates (WebView inventory, bridges, flows) with `add_finding` calls. Two things depend on order:
- findings with equal sort keys keep their insertion order;
- `evidence` is capped at 20 items in the order they were added.

**Decision**: Split the analyzer into a package under `sentry/core/report/`, done in small steps:

| Module | Contents |
|---|---|
| `loader.py` | `load_events` |
| `values.py` | `normalize_value`, `parse_bool`, `first_arg`, `compact` |
| `urls.py` | URL and origin classification |
| `tracker.py` | WebView state and the per-event state updates; no findings |
| `findings.py` | `FindingStore`: deduplication, the evidence cap, ordering, risk scoring |
| `rules/catalog.py` | Rule data: severities, `DANGEROUS_SETTINGS`, regexes, sink sets |
| `rules/settings.py`, `rules/navigation.py`, `rules/bridges.py`, `rules/permissions.py`, `rules/javascript.py` | Detector functions `detect(event, data, tracker, findings)` |
| `analyzer.py` | Dispatches each event type to its tracker update and detector, in the same order as the original method body; also holds `build_report` |
| `assemble.py` | `render_webviews`, `render_origin_bridge_map`, the summary |
| `markdown.py` | `markdown_report` |
| `cli.py` | Argument parsing and file writing |

If an original method updates state *between* two findings, the dispatch keeps that order. Two ways are allowed: split the tracker update into before and after steps, or have the detector take the snapshot it needs. The golden tests (R6) are the safety net, and they run after every extraction step.

**Rationale**:
- This meets FR-009 and FR-013, and US4/SC-006: a new rule means a new detector in `rules/`, registered in one table in the same package.
- Detectors never do file I/O; only `cli.py` reads and writes files.

**Alternatives**:
- *Leave the observers whole and just move the class into its own file*: rejected. It fails SC-006 and SC-007, because the class body is about 585 lines.
- *An event-sourced rule engine with declarative rules*: rejected. It is a redesign, not a refactor, and it risks changing results.

---

## R5. Splitting the shell scripts and sharing helpers

**Decision**:
- `analyse.sh` stays at the repo root as a POSIX `sh` launcher of about 10 lines. It sets `SENTRY_HOME="$(dirname "$0")/sentry"`, sources `sentry/core/run/*.sh` and calls `sentry_analyse "$@"`. Sourcing, rather than `exec`, keeps the `EXIT`/`INT`/`TERM` traps and the exit codes in the same shell process, so they behave exactly as they do now.
- The modules under `sentry/core/run/` are:
  - `common.sh`: `check_missing_commands`, the banner;
  - `package.sh`: `find_aapt`, `apk_package_name`, shared with the benchmark runner;
  - `workspace.sh`: prepares `target/` and `logs/` and writes `.env`;
  - `report.sh`: `generate_report`;
  - `main.sh`: validates input, selects the runner and dispatches to it.
- The runners live in `sentry/core/runners/docker.sh` and `local.sh`. In-container scripts move to `sentry/core/runners/container/`:
  - `entry.sh` is the former `sentry/run.sh`;
  - `frida-server/` is the former top-level `run-frida-server/`. Its build path in `docker-compose.yml` is updated.
- `scripts/run-benchmarks-linux.sh` stays where it is, because it is a documented path. It becomes a launcher for `sentry/core/benchmark/run.sh`, which sources `core/run/package.sh`.
- The libraries must be POSIX `sh`. `package.sh` is sourced by both `sh` and `bash`.

**Exception, approved by the project owner on 2026-10-16 and recorded as the FR-001 exception**: `analyse.sh` and the benchmark runner do the same two things in slightly different ways.

| Helper | `analyse.sh` | Benchmark runner |
|---|---|---|
| `find_aapt` | `PATH`, then Homebrew paths | `PATH`, then the newest `$ANDROID_HOME`/`$ANDROID_SDK_ROOT` `build-tools` |
| Package name | `grep package \| cut` (can join several lines if more than one line contains "package") | `sed -n "s/^package: name='…'.*/\1/p" \| head -n 1` |

FR-014 requires a single implementation, so this plan **unifies** them:
- `find_aapt` searches `PATH`, then SDK `build-tools`, then Homebrew.
- `apk_package_name` uses the stricter `sed` form.

Observable behavior changes only in cases where one caller used to fail or return a garbled package name. Error messages and exit codes are kept for every path. The change is recorded in [contracts/cli-analyse.md](./contracts/cli-analyse.md#intentional-deviations).

**Alternative**: keep the two parsing variants as two differently named functions in `package.sh`. That gives identical behavior but leaves the duplication in place; it is the fallback if you reject the unification.

---

## R6. Proving behavior is preserved without existing reference logs

**Context**: No captured logs exist in the repo: `logs/`, `target/` and `benchmark-results/` are git-ignored and absent. FR-016 and FR-017 need reference logs together with their expected reports.

**Decision**:
- **Before any code moves**, build the reference set in two tiers:
  1. **Synthetic fixtures** (`tests/fixtures/logs/synthetic/*.log`). These are hand-authored event streams that together reach every `observe_*` branch and every rule id in the catalog. They also include:
     - an empty file;
     - a malformed file (non-JSON lines, JSON with no `type`, Frida banner noise);
     - a run with `--trusted-origin`.
  2. **Benchmark captures** (`tests/fixtures/logs/benchmark/<case>.log`). These are produced by running `scripts/run-benchmarks-linux.sh` with the **pre-refactor** code on a Linux/KVM host, then copying `benchmark-results/<case>/output.log`. There is one log per APK under `Benchmark/`.
- `tests/tools/regen_expected.py --legacy <path-to-legacy-report.py>` creates the expected `report.json` and `report.md` for each log using the original `report.py` at commit `7936080`. Those outputs are committed once, as `tests/fixtures/expected/`.
- `tests/test_report_golden.py` (stdlib `unittest`) runs the new CLI on every log and compares the outputs **byte for byte**. The current output is already deterministic: `sort_keys=True`, and there are no timestamps in the report.
- A coverage guard test asserts that the expected reports, taken together, contain every rule id in the catalog.

**Live-stream equivalence (FR-004)**: `tests/tools/compare_event_streams.py old.log new.log` normalizes timestamps, the namespace, `hashCode`-based ids and `taint-<ms>` ids. It then compares the multiset of `(type, sorted payload keys)` and the normalized payloads. It is used in the quickstart for the end-to-end checks.

**Risk**: The benchmark-capture tier needs a Linux/KVM host **before** the refactor begins. If none is available, the synthetic tier still gates every change, but FR-017 ("every benchmark case") and SC-001 stay open until captures exist. Tasks must schedule the capture first.

**Alternatives**:
- *Snapshot only the synthetic tier*: rejected, because it is not enough to meet FR-017.
- *Compare against `git stash`ed old code at test time*: rejected as fragile. The frozen expected outputs are simpler to review.

---

## R7. Checking browser-side parity without a device

**Decision**: Add `tests/test_browser_parity.py`. It runs the **legacy** injection script (from a frozen copy, `tests/fixtures/legacy/webview.js`) and the **new** rendered observer, each in a Node `vm` context with a minimal fake `window` (stubs for `fetch`, `XMLHttpRequest`, `Storage`, `navigator.sendBeacon`, `postMessage`, `location`). It drives the same scripted calls through both and compares the drained probe payloads after normalizing timestamps and taint ids. The test is **skipped if `node` is not on `PATH`**, so Node is a development convenience, not a runtime dependency.

**Rationale**: The page-side code is the part most likely to break silently when the template strings are converted to files. This check catches that without an emulator.

**Alternative**: rely only on end-to-end runs. Rejected as the only gate, because it needs devices and is slow.

---

## R8. Enforcing the layering and size budgets

**Decision**: Add a set of cheap static checks, split into one file per area (`tests/test_layering_browser.py`, `_native`, `_core`, `_layout`) that share `tests/layering_helpers.py`:

| Check | What it enforces |
|---|---|
| `browser/**` never mentions `Java.`, `EVENT_TYPE`, or `send(`/`console.log(` | browser code runs only in the page context |
| `native/**` contains no `window.`/`window[` and no `document.` | no page-side code inside native |
| Python under `core/report/rules/` does not use `open(`, `Path(…).write`, `print(` | FR-013 |
| `core/report/markdown.py` and `assemble.py` do not import `rules` | FR-013 |
| `core/report/**` does not reference `browser/` or `native/` | FR-012 |
| Each area and sub-area file starts with a responsibility header comment | FR-015 |
| Line budgets: each file in `browser/` and `native/` ≤ 430 lines (one-third of 1,294); each `core/report/` module ≤ 340 lines (one-third of 1,019); each `core/run/` and `core/runners/` script ≤ 72 lines (one-third of 214); each `core/benchmark/` script ≤ 53 lines (one-third of 158) | SC-007 |

**Alternative**: linters such as eslint and ruff. Rejected because they add new dependencies; the plain `unittest` checks are enough.

---

## R9. Where tests and documentation live

**Decision**:
- Tests go in a top-level `tests/` directory. Tests are not toolchain logic, so they stay outside `browser/`, `native/` and `core/` (FR-007). Run them with `python3 -m unittest discover -s tests`.
- Each area gets a `README.md` (`sentry/browser/README.md`, `sentry/native/README.md`, `sentry/core/README.md`) that lists its sub-areas and says which change goes where (FR-015, SC-005).
- The root `README.md` gains a short "Project layout" section; the usage sections stay unchanged (FR-018, SC-003).

---

## R10. The constitution

The file `.specify/memory/constitution.md` is still the unfilled template, so there are no ratified principles to check against. The Constitution Check in the plan is therefore **N/A, passing by default**. Running `/speckit-constitution` before `/speckit-tasks` is recommended if the project wants principles enforced, for example "no new runtime dependencies" or "golden-test gate on report changes".

---

## R11. Moving the shell orchestration to Python (follow-up, 2026-10-16)

**Context**: After R5, the orchestration was 16 sourced shell files. The shell traps, pipelines and `set -e` behaviour were hard to follow, and none of it could be unit-tested.

**Decision**: Rewrite the orchestration in stdlib Python using four patterns:

| Pattern | Where | Why |
|---|---|---|
| **Facade** | `core/host.py` (`Host`) | It is the only place that touches the environment, `PATH`, platform/KVM detection, processes and the `tee` pipeline. Tests swap in a recording `FakeHost` (`tests/fakes.py`). |
| **Strategy + Factory** | `core/runners/` (`Runner`, `DockerRunner`, `LocalRunner`, `select_runner`) | Adding a runner means adding a class and registering it. `auto` selection lives in one place. |
| **Template Method** | `core/run/session.py` (`AnalysisSession.run`) | Fixes the step order (validate → package → runner → preflight → workspace → run). Runners only fill in `preflight` and `run`. |
| **Adapter** | `core/runners/adb.py` (`Adb`) | Wraps `SENTRY_ADB_SERIAL`, the boot wait and the frida-server startup. |

Shell constructs are mapped as follows:
- the `EXIT` trap becomes the `report_on_exit` context manager;
- `trap 'exit 130' INT` and `'exit 143' TERM` become signal handlers that raise `SystemExit`;
- `echo …; exit 1` becomes `host.die(...)`;
- `cmd | tee a b` becomes `Host.tee` (exit status ignored, as in the shell pipeline);
- `set -eu` in the container scripts becomes `Host.run_checked`.

`analyse.sh` and `scripts/run-benchmarks-linux.sh` stay as launchers of about 5 lines, because they are the documented commands (FR-001, FR-006). The `run-frida-server` image now builds from `sentry/` with `core/runners/container/frida_server.Dockerfile` and installs `python3`.

**Verification**:
- `tests/test_local_simulation.py` runs the legacy shell and the new launcher side by side with fake `adb` and `frida` on `PATH`. It checks identical stdout, event logs, reports, `.env` and adb call sequence, and that Ctrl-C exits 130 with an identical report.
- The `FakeHost` tests cover the Docker runner, the container entry points and the benchmark suite.

**Size limits (SC-007)**: these are now per Python module: `run/` and `runners/` ≤ 100 lines; `benchmark/suite.py` and `host.py` ≤ 160 lines.

**Alternatives**: keeping the 16 shell modules (rejected: hard to test and maintain); a CLI framework such as Click or Typer (rejected: a new runtime dependency); `invoke`/`make` tasks (rejected: a different interface from the documented commands).
