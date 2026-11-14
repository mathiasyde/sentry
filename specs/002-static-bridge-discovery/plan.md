# Implementation Plan: Static JavaScript Bridge Discovery

**Branch**: `002-static-bridge-discovery` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-static-bridge-discovery/spec.md`

## Summary

Before the dynamic run, Sentry scans the APK and lists the JavaScript bridges it can register:

- every method marked `@JavascriptInterface`,
- every `addJavascriptInterface(obj, name)` call site, with the bridge name and the registered class worked out from the bytecode.

Static results are joined with the runtime bridge events in the report, and each bridge is labelled *static and runtime*, *static only* or *runtime only*. The scan is on by default. `--discover-bridge-interfaces=false` or `--no-discover-bridge-interfaces` turns it off.

Technical approach (details in [research.md](research.md)):

- A new **stdlib-only** package, `sentry/core/static/`, reads the APK with `zipfile`. It parses DEX and binary-XML manifests with `struct`, and runs a small dataflow analysis within each method to resolve the name and object arguments at each call site.
- `core.run` gains option parsing. It runs the scan in-process before the runner and writes `target/static-bridges.json`.
- The report CLI gains `--static-bridges <path>`. It adds a static inventory section and an info-level finding for each static-only bridge.
- None of the report output changes when the option is not passed, so the existing golden fixtures stay byte-identical.

## Technical Context

**Language/Version**: Python 3.14 (host and `sentry` container image). No new language.

**Primary Dependencies**: Standard library only (`zipfile`, `struct`, `re`, `json`, `argparse`). No new pip, apt or SDK dependency (research R1).

**Storage**: Files in the run workspace. New: `target/static-bridges.json`.

**Testing**: `python3 -m unittest discover -s tests -t .`. The tests use:
- the eight committed `Benchmark/*.apk` files as ground truth;
- bytecode unit tests built from hand-assembled code units;
- new golden report fixtures fed by synthetic static artifacts.

**Target Platform**: The host where `analyse.sh` runs (macOS or Linux). The scan runs on the host for both runners, so the Docker image is unchanged.

**Project Type**: CLI tool (security analysis pipeline).

**Performance Goals**: The scan adds ≤ 30 s for APKs up to 50 MB (SC-003). Benchmark APKs carry about 9.8 MB of DEX each. Target: under 10 s each on a laptop.

**Constraints**:
- The scan never fails a run (FR-015).
- With the option off, output is identical to today's (FR-016, SC-004).
- `core/` layering rules: only `host.py` runs processes, `report/rules/` does no I/O, and module size limits apply (`run/` ≤ 100 lines, `report/` ≤ 340 lines). The new `static/` modules follow the same ≤ 340-line limit.

**Scale/Scope**: Multidex APKs with tens of thousands of classes (AndroidX and Compose). Analysis is intra-procedural; inter-procedural name resolution is out of scope (spec Assumptions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template, so there are no ratified principles to check against. The binding project rules are the ones in `sentry/core/README.md` § Rules, which `tests/test_layering_*.py` enforce. They serve as the gates here:

| Gate (source) | Status | How the design meets it |
|---|---|---|
| Only `host.py` runs processes (`test_only_host_touches_processes`) | PASS | The scan is pure Python. It runs no `aapt`, `java` or decompiler. |
| `report/rules/` does no file I/O or printing (`test_rules_do_no_io`) | PASS | The static artifact is read in `report/cli.py`. The new rule only gets a parsed dict. |
| `tracker`, `assemble` and `markdown` create no findings | PASS | The join lives in a new pure module, `report/correlate.py`. Findings come from `rules/static_bridges.py`. |
| `report/` does not depend on `browser/` or `native/` | PASS | The only contract is the JSON artifact. |
| Size limits (`test_sizes`) | PASS | Option parsing (`run/options.py`) and the discovery step (`run/discovery.py`) are separate files, so `session.py` stays ≤ 100 lines. `static/` is split into modules of ≤ 340 lines, and `test_sizes` is extended to cover it. |
| Module header docstrings (`test_headers`) | PASS | Every new file starts with a `"""core/static: …"""` header. |
| Golden reports byte-identical unless the change is meant to alter output (core README) | PASS | All static output depends on `--static-bridges`. The existing fixtures don't pass it. |
| `analyse.sh` stdout matches legacy (`test_matches_legacy_output`) | **DEVIATION (justified)** | FR-018 requires the option in the usage text, so the `no_args` usage output gains one line. See Complexity Tracking. |

**Post-design re-check (after Phase 1)**: All gates still pass. The one deviation is unchanged and recorded in [contracts/cli-analyse-option.md](contracts/cli-analyse-option.md).

## Project Structure

### Documentation (this feature)

```text
specs/002-static-bridge-discovery/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-analyse-option.md     # analyse.sh option grammar, messages, step order
│   ├── cli-static.md             # python3 -m core.static (standalone scanner)
│   ├── static-artifact.md        # target/static-bridges.json schema
│   └── report-static-section.md  # report CLI flag, JSON section, Markdown section, finding
├── checklists/requirements.md
└── tasks.md                      # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
sentry/core/
├── static/                    # NEW: APK static analysis, stdlib only, no processes
│   ├── __init__.py            # discover_bridges(apk_path) -> dict (artifact payload)
│   ├── __main__.py            # python3 -m core.static <apk> [--out PATH]
│   ├── apk.py                 # zip access: ordered classes*.dex blobs, AndroidManifest.xml
│   ├── axml.py                # minimal binary-XML reader: package, minSdk, targetSdk
│   ├── dex.py                 # DEX reader: ids tables, class defs/data, annotations, static values, code items
│   ├── insns.py               # Dalvik opcode width table + decoder for the opcodes the analysis needs
│   ├── dataflow.py            # per-method may-analysis of register values; reports call sites
│   └── discover.py            # class index across dex files, exposed methods, linking, inheritance, API<17 rule
├── run/
│   ├── options.py             # NEW: parse --[no-]discover-bridge-interfaces[=v]; positional args untouched
│   ├── discovery.py           # NEW: run the scan, write artifact, print one status line, never raise
│   ├── session.py             # CHANGED: options → … → prepare → discovery → runner; usage line
│   ├── reporting.py           # CHANGED: pass --static-bridges when the artifact exists
│   └── workspace.py           # CHANGED: static_bridges path; prepare() removes a stale copy
├── report/
│   ├── cli.py                 # CHANGED: --static-bridges PATH (read + validate here)
│   ├── analyzer.py            # CHANGED: accepts static result; runs static rule after events
│   ├── correlate.py           # NEW: pure join of static registrations and tracker bridges
│   ├── assemble.py            # CHANGED: "static_bridges" key only when static result given
│   ├── markdown.py            # CHANGED: "## Static Bridge Inventory" only when present
│   └── rules/static_bridges.py # NEW: WV-STATIC-BRIDGE-UNOBSERVED (info)
└── benchmark/suite.py         # CHANGED: archive target/static-bridges.json

tests/
├── test_static_insns.py        # NEW: width table, decoding, payload skipping
├── test_static_dataflow.py     # NEW: const/move/sget/new-instance/check-cast/branches/unresolved
├── test_static_benchmarks.py   # NEW: Benchmark/*.apk vs ground truth (SC-001, SC-002, SC-003)
├── test_static_discover.py      # NEW: linking, inheritance/override hiding, API<17, ambiguity (fake index)
├── test_static_discovery_run.py# NEW: option parsing, failure isolation (SC-005), disabled = unchanged
├── test_report_golden.py       # CHANGED: adds synthetic__static_* scenarios
├── test_cli_contract.py        # CHANGED: usage deviation; option error message
├── test_layering_core.py       # CHANGED: static/ size, no processes, import boundaries
└── fixtures/
    ├── static/ground_truth.json          # NEW: hand-made from Benchmark/*.zip sources
    ├── static/synthetic_*.json           # NEW: static artifacts for report goldens
    └── expected/synthetic__static_*/     # NEW: golden report.json / report.md / stdout.txt
```

**Structure Decision**: Static analysis is not instrumentation, so it lives in `core/` as a new sibling package, `core/static/`, next to `report/` and `run/`. It depends on nothing in `run/` or `runners/`. Its one import from `report/` is the shared sensitive-name pattern in `report/rules/catalog.py`, kept in one place so that FR-009 holds. `report/` never imports `static/`: the artifact file is the contract between them, just as the event log is the contract with `native/`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `analyse.sh` no-args output differs from the legacy script (one extra usage line) | FR-018 requires the option in the usage text | Keeping usage byte-identical would hide a default-on behaviour from users. Documenting it only in the README fails FR-018. The first usage line is kept unchanged, so scripts that grep for it keep working. |
| A custom DEX/AXML reader (~700 lines) instead of a library | Keeps the host free of pip dependencies (today the host needs only `python3`, `adb` and `frida`) and keeps everything inside `Host` and testable | Androguard brings a heavy dependency tree and a first host-side pip requirement, and it still leaves the per-method register analysis to us. `jadx`/`baksmali` need Java and a subprocess, plus output scraping. See research R1. |

## Implementation notes and traceability (2026-10-16)

The implementation added a few things to the structure above:
- `sentry/core/static/index.py`: the class index and resolver adapter, split out of `discover.py` to keep both under 340 lines.
- `sentry/core/report/markdown_static.py`: the inventory renderer, kept apart from `markdown.py`.
- `tests/static_asm.py`: a tiny Dalvik assembler and fake index for the unit tests.
- `tests/test_static_readers.py` and `tests/test_run_options.py`.
- Static-report goldens live in `tests/fixtures/expected_static/`, not `tests/fixtures/expected/`, because the legacy oracle can't produce them.
- The legacy-parity simulations in `tests/test_local_simulation.py` now run the current tree with `--no-discover-bridge-interfaces` (FR-016). A new test covers the default-on path.

| Requirement | Implemented in | Verified by |
|---|---|---|
| FR-001 to FR-003 option grammar, default on | `run/options.py`, `run/session.py` | `test_run_options`, `test_cli_contract` |
| FR-004 scan before the run, no device | `run/discovery.py`, `run/session.py` | `test_static_discovery_run.test_default_runs_discovery_before_runner` |
| FR-005 annotated methods | `static/dex.py`, `static/index.py` | `test_static_benchmarks`, `test_static_discover` |
| FR-006 and FR-007 call sites, literal or unresolved names | `static/dataflow.py`, `static/discover.py` | `test_static_dataflow`, `test_static_discover` |
| FR-008 name → class → methods, inheritance | `static/discover.py` | `test_static_discover.test_inheritance_and_override_hiding` |
| FR-009 sensitive flag | `static/discover.py` (shared catalog regex) | `test_static_discover` |
| FR-010 pre-API-17 | `static/discover.py`, `static/axml.py` | `test_static_discover.test_pre_17_exposes_all_public_methods` |
| FR-011 artifact always written | `run/discovery.py` | `test_static_discovery_run` |
| FR-012 inventory with provenance | `report/correlate.py`, `report/assemble.py`, `report/markdown_static.py` | `test_report_static` |
| FR-013 static-only info finding | `report/rules/static_bridges.py` | `test_report_static.test_mixed_provenance_and_finding` |
| FR-014 discovery status in report | `report/markdown_static.py` | `test_report_static.test_failed_artifact` |
| FR-015 failure never fails the run | `run/discovery.py` | `test_static_discovery_run.test_failure_does_not_stop_the_run`, `test_local_simulation.test_default_discovery_failure_keeps_the_run` |
| FR-016 off = legacy behaviour | `run/session.py`, `run/reporting.py` | `test_static_discovery_run.test_disabled_leaves_no_trace`, `test_local_simulation` (legacy parity) |
| FR-017 benchmark archive | `benchmark/suite.py` | `test_benchmark` |
| FR-018 usage text and README | `run/options.py`, `README.md` | `test_cli_contract.test_no_args` |
| SC-001 and SC-002 ground truth | | `test_static_benchmarks.test_ground_truth` (8 of 8 APKs) |
| SC-003 under 30 s | | `test_static_benchmarks` (measured about 0.1 s per benchmark APK) |
| SC-004 goldens byte-identical | | `test_report_golden`, `test_report_static.test_without_option_output_is_unchanged` |
| SC-005 failure isolation | | `test_static_benchmarks.test_truncated_apk_fails_cleanly`, `test_static_discovery_run` |
| SC-006 coverage gaps readable from the report | | `test_report_static` goldens (review of `report.md`) |
