---

description: "Task list for static JavaScript bridge discovery"
---

# Tasks: Static JavaScript Bridge Discovery

**Input**: Design documents from `specs/002-static-bridge-discovery/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The spec's success criteria SC-001 to SC-005 need automated checks, and the plan names the test files. The repo convention (`sentry/core/README.md`) is to run `python3 -m unittest discover -s tests -t .` before and after every change.

**Organization**: Tasks are grouped by user story, so each story can be built and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (a different file, with no dependency on an unfinished task)
- **[Story]**: US1 (P1, static inventory), US2 (P2, static/runtime comparison), US3 (P3, turning discovery off)

## Conventions every task must follow

- Every new `.py` file starts with a one-line module docstring header of the form `"""core/static: <what it does>."""` (or `core/run:`, `core/report:`, …). `tests/test_layering_core.py::test_headers` enforces this. Test files use a plain one-line docstring.
- **Standard library only.** No `subprocess`/`os.system` anywhere outside `sentry/core/host.py`.
- Size limits: `sentry/core/run/*.py` ≤ 100 lines; `sentry/core/report/**/*.py` ≤ 340 lines; `sentry/core/static/*.py` ≤ 340 lines.
- `sentry/core/report/rules/*.py` must not call `open(`, `.write_text(`, `.write(`, `print(` or `Path(`.
- `sentry/core/report/{tracker,assemble,markdown}.py` must not import `core.report.rules` or `core.report.findings`.
- **Class and type names in every output are dotted Java names**: `Lcom/x/Foo;` → `com.x.Foo`, `[I` → `int[]`, `V` → `void`, `Z` → `boolean`, and so on.
- Existing golden files under `tests/fixtures/expected/` must stay **byte-identical**. Never regenerate them.
- Run the test suite from the repo root: `python3 -m unittest discover -s tests -t .`. Standalone commands use `PYTHONPATH=sentry`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton, ground-truth fixture and layering guards for the new code.

- [X] T001 Create the package `sentry/core/static/` with `__init__.py`. Give it the header `"""core/static: static analysis of an APK for JavaScript bridges (stdlib only, no processes)."""` and a stub `def discover_bridges(apk_path) -> dict: raise NotImplementedError`.
- [X] T002 [P] Create `tests/fixtures/static/ground_truth.json`, keyed by APK file name.
  - Write one entry per `Benchmark/*.apk`, of the form `{"registrations": [{"name": "Android", "class_name": <dotted>, "class_resolution": "exact", "methods": [<method names>]}]}`.
  - Values come from the sources in `Benchmark/*.zip` (research R9):
    - `strongUpdate.apk` and `strongUpdatecaseA.apk` → `com.example.strongupdate.BridgeClass`, `["showData"]`;
    - `JSUpdateCaseD.apk` → `com.example.jsUpdatecaseD.MainActivity`, `["getData"]`;
    - `JsUpdateCaseE/F/G.apk` → `com.example.jsUpdatecase{E,F,G}.MainActivity`, `["getData"]`;
    - `strongUpdatecaseB.apk` → `com.example.strongupdatecaseb.MainActivity`, `["getData"]`;
    - `strongUpdatecaseC.apk` → `com.example.strongupdatecaseC.MainActivity`, `["getData"]`.
  - Check each package and class name against `unzip -p <apk> AndroidManifest.xml` and the dex strings, not only the zip folder names. The zip files' inner folders are misnamed (for example, every `JsUpdateCase*` zip contains `StrongUpdateCaseB/`).
- [X] T003 [P] Extend `tests/test_layering_core.py`:
  - In `test_sizes`, add `assert_max_lines(self, iter_files(CORE / "static", [".py"]), 340)`.
  - Add `test_static_is_self_contained`: no file in `sentry/core/static/` matches `^\s*(from|import)\s+core\.(run|runners|benchmark)\b`, and the only `core.report` import allowed is `from core.report.rules.catalog import SENSITIVE_METHOD_RE`.
  - Add `test_report_does_not_import_static`: no file in `sentry/core/report/` matches `core\.static`.
  - `test_only_host_touches_processes` already covers `static/`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Low-level readers for APK, binary XML, DEX and Dalvik bytecode. All user stories depend on these.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [X] T004 [P] Implement `sentry/core/static/apk.py` (header `"""core/static: APK container access: ordered dex files and the binary manifest."""`):
  - `class Apk` wraps `zipfile.ZipFile(path)`.
  - `dex_names()` returns the zip members matching `^classes(\d*)\.dex$`, ordered `classes.dex`, `classes2.dex`, `classes3.dex`, … (numeric order).
  - `read(name) -> bytes`.
  - `manifest() -> bytes | None` reads `AndroidManifest.xml`.
  - `sha256()` streams the APK file in 1 MiB chunks.
  - Let `zipfile.BadZipFile` propagate; the callers turn it into `status: "failed"`.
- [X] T005 [P] Implement `sentry/core/static/axml.py` (header `"""core/static: minimal Android binary XML reader for package, minSdkVersion and targetSdkVersion."""`):
  - `def manifest_info(data: bytes) -> dict` returns `{"package": str|None, "min_sdk": int|None, "target_sdk": int|None}`.
  - Parsing steps:
    1. Read the chunk header `RES_XML_TYPE` (0x0003).
    2. Read the string pool `RES_STRING_POOL_TYPE` (0x0001), UTF-8 and UTF-16 flavours.
    3. Walk `RES_XML_START_ELEMENT_TYPE` (0x0102) chunks.
    4. For the `manifest` element, read attribute `package` (raw string).
    5. For `uses-sdk`, read `minSdkVersion` and `targetSdkVersion`. A typed value of type `TYPE_INT_DEC` (0x10) or `TYPE_INT_HEX` (0x11) gives an int. A string value is parsed with `int()` if numeric. A reference value or anything else gives `None`.
  - Match attribute names by their string-pool name; the resource-id map does not need to be resolved.
  - `target_sdk` falls back to `min_sdk` (research R4).
  - Must not raise on truncated input: return all-`None` instead.
- [X] T006 [P] Implement `sentry/core/static/dex.py` (header `"""core/static: DEX file reader: id tables, class defs and data, annotations, static values, code items."""`). Use `struct`, little-endian, and lazy access:
  - **Header**: magic `dex\n03[5-9]\0`. Offsets: `string_ids_size/off` at 0x38/0x3C, `type_ids` 0x40/0x44, `proto_ids` 0x48/0x4C, `field_ids` 0x50/0x54, `method_ids` 0x58/0x5C, `class_defs` 0x60/0x64.
  - **Primitives**: `uleb128`, `sleb128` and `uleb128p1` readers. A MUTF-8 decoder (handle `0xC0 0x80` → NUL and surrogate pairs, using `errors="surrogatepass"`, then re-encode), cached per index.
  - **Tables**: `string(i)`, `type_name(i)` (descriptor), `proto(i) -> (return_descriptor, [param_descriptors])`, `field(i) -> (class, type, name)`, `method(i) -> (class, name, proto_idx)`.
  - **String search**: `find_string(s) -> int | None` does a binary search over `string_ids`, which are sorted by code-point order of the MUTF-8 data. Compare decoded strings.
  - **Class defs**: `class_defs()` yields `ClassDef(descriptor, access_flags, superclass|None, interfaces[list], annotations_off, class_data_off, static_values_off)`.
  - **Class data**: `class_methods(cdef)` yields `EncodedMethod(method_idx, access_flags, code_off)` for direct and virtual methods. Method indexes are delta-encoded, and the delta resets between the direct and virtual lists.
  - **Static fields**: `static_fields(cdef)` yields field indexes in order.
  - **Static values**: `static_string_values(cdef) -> dict[field_idx, str]`. Decode the `encoded_array` at `static_values_off`, keeping only `VALUE_STRING` (0x17) entries. Skip every other `encoded_value` type correctly by size, including nested `VALUE_ARRAY` (0x1c) and `VALUE_ANNOTATION` (0x1d).
  - **Annotations**: `method_annotation_types(cdef) -> dict[method_idx, set[type_descriptor]]` from the `annotations_directory_item` (`class_annotations_off`, `fields_size`, `annotated_methods_size`, `annotated_parameters_size`, then field and method annotation lists). For each method, read the `annotation_set_item` → `annotation_off_item` → `annotation_item` (visibility byte, then `encoded_annotation` whose first `uleb128` is `type_idx`).
  - **Code items**: `code(code_off) -> CodeItem(registers_size, ins_size, insns: memoryview of uint16 code units as bytes, tries: list[(start, count, handler_off)], handlers: dict[handler_off, list[addr]])`. The `tries` array is 4-byte aligned after `insns` when `tries_size > 0` and `insns_size` is odd. Parse `encoded_catch_handler_list`, where a negative size means a catch-all is present.
  - **Utility**: `descriptor_to_java(desc) -> str` for dotted names, arrays and primitives, exported for the other modules.
- [X] T007 [P] Implement `sentry/core/static/insns.py` (header `"""core/static: Dalvik instruction widths and decoding of the opcodes the bridge analysis needs."""`):
  - A 256-entry width table in code units, built from the Dalvik format table:
    - 10x/11x/11n/12x = 1;
    - 20t/21c/21h/21s/21t/22b/22c/22s/22t/22x/23x = 2;
    - 30t/31c/31i/31t/32x/35c/3rc = 3;
    - 45cc/4rcc = 4;
    - 51l = 5.
    Unused opcodes = 1.
  - Payload pseudo-instructions start at an opcode-0x00 code unit with ident `0x0100` (packed-switch), `0x0200` (sparse-switch) or `0x0300` (fill-array-data). They are sized from their headers:
    - packed: `size*2 + 4`;
    - sparse: `size*4 + 2`;
    - array: `(size*width + 1)//2 + 4`.
  - `iter_insns(insns_bytes)` yields `(offset, opcode, units)`, skipping payloads.
  - `decode(offset, units) -> Insn(op, kind, regs, ref, branch_targets)` for:
    - `const-string` 0x1a (21c), `const-string/jumbo` 0x1b (31c);
    - `move-object` 0x07, `move-object/from16` 0x08, `move-object/16` 0x09;
    - `move-result-object` 0x0c;
    - `new-instance` 0x22, `check-cast` 0x1f;
    - `iget-object` 0x54, `sget-object` 0x62;
    - `invoke-virtual` 0x6e, `invoke-super` 0x6f, `invoke-direct` 0x70, `invoke-static` 0x71, `invoke-interface` 0x72 (35c: register list from the A|G, C|D, E|F nibbles; arg count A);
    - the `invoke-*/range` forms 0x74–0x78 (3rc);
    - `goto` 0x28/0x29/0x2a;
    - `if-*` 0x32–0x37 (22t) and 0x38–0x3d (21t);
    - `packed-switch` 0x2b and `sparse-switch` 0x2c (31t: payload offset → decode the targets);
    - `return*` 0x0e–0x11 and `throw` 0x27, both terminal.
  - For every other opcode, `decode` returns `kind="other"` with `writes` set to the destination register(s) for formats whose first register is a destination. That covers the const*, move*, unops, binops, *get*, new-array, array-length, instance-of, cmp* and similar families. For a wide destination (`-wide` opcodes) also list `vA+1`.
  - Export `TERMINAL`, `BRANCH` and `INVOKE` opcode sets.
- [X] T008 [P] Add `tests/test_static_insns.py`:
  - Assert the widths of a hand-assembled code-unit sequence: `const-string v0, #5` → 2; `invoke-virtual {v1, v2, v0}, meth@7` → 3; `const-wide v0, #…` → 5; `invoke-polymorphic` → 4.
  - Check that `iter_insns` skips a packed-switch and a fill-array-data payload placed after a `return-void`.
  - Check that `decode` gets the 35c register order right (`{vC, vD, vE, vF, vG}`) and handles 3rc ranges.
  - Decode switch targets.
- [X] T009 [P] Add `tests/test_static_readers.py`:
  - Build a minimal DEX in memory with a test helper that writes the header and the string, type, proto and method id tables with `struct`. Use it to check `find_string` binary search (present, absent, first, last), `descriptor_to_java` on `Lcom/a/B;`, `[I`, `[[Ljava/lang/String;` and `Z`, and the MUTF-8 NUL and surrogate cases.
  - Check `axml.manifest_info` on the real `AndroidManifest.xml` read from `Benchmark/strongUpdate.apk`: `package == "com.example.strongupdate"`, and `target_sdk` is an int ≥ 17.
  - Check that `axml.manifest_info(b"\x03\x00")` returns all-`None`.

**Checkpoint**: The readers and decoder pass their unit tests. User-story work can start.

---

## Phase 3: User Story 1 - See every bridge an APK can expose (Priority: P1) 🎯 MVP

**Goal**: With default options, `analyse.sh` scans the APK before the dynamic run and writes `target/static-bridges.json` (FR-004 to FR-011). The reports include a Static Bridge Inventory listing each bridge's name, class and exposed methods (FR-012, minus provenance), along with the discovery status (FR-014). A scan failure never stops the run (FR-015). The benchmark archive keeps the artifact (FR-017).

**Independent Test**: `PYTHONPATH=sentry python3 -m core.static Benchmark/strongUpdate.apk` lists `Android → com.example.strongupdate.BridgeClass → showData`, and `tests/test_static_benchmarks.py` passes for all 8 benchmark APKs. A report built with `--static-bridges` shows the inventory section.

### Tests for User Story 1

- [X] T010 [P] [US1] Add `tests/test_static_dataflow.py`. Test `dataflow.analyze_method(...)` (T012) using hand-assembled code units and a fake resolver object that maps string, type, field and method indexes to values. Cover:
  - (a) `const-string v0 "A"; new-instance v1 LBridge;; invoke-virtual {v2,v1,v0} addJI` → name `"A"`, `name_status: "resolved"`, `class_resolution: "exact"`;
  - (b) the name chosen through `if-eqz` branches as `"A"` or `"B"` → two registrations from one call site;
  - (c) the name from `invoke-static …; move-result-object v0` → `name_status: "unresolved"`, `name_source.kind == "method-result"`, and `ref` naming the callee;
  - (d) the name from `sget-object` of a field with a static string value → `"static-field"` and resolved;
  - (e) the object from `p0` (`this`) in an instance method → the declaring class with `declared-type` resolution;
  - (f) the object from a parameter typed `Ljava/lang/Object;` with two bridge-capable classes in the fake index → `ambiguous`, both listed in `candidate_classes`;
  - (g) a `move-object/from16` copy chain is preserved;
  - (h) more than 8 distinct strings reach the name register → `TOP` → unresolved;
  - (i) a register read at the entry of an exception handler is `TOP`;
  - (j) `removeJavascriptInterface(String)` is reported as a removal;
  - (k) `invoke-virtual/range` form.
- [X] T011 [P] [US1] Add `tests/test_static_discover.py`. Test `discover.link(...)` (T013) with a fake class index of plain dicts, with no DEX needed. Cover:
  - an exposed method inherited from an in-APK superclass is listed with `declared_in` set to the superclass;
  - an unannotated override in the subclass **hides** the annotated superclass method (research R3);
  - a non-public annotated method is not exposed;
  - with `target_sdk = 16`, all public methods are listed with `exposure: "public-pre-17"` and `all_public_methods_exposed is True`;
  - with `target_sdk = None`, the annotation rule applies;
  - `sensitive` is True for `getToken` and False for `showData` (FR-009);
  - a class with exposed methods but no registration appears in `bridge_classes` with `registered: false`;
  - output lists are sorted as data-model.md specifies.
- [X] T012 [P] [US1] Add `tests/test_static_benchmarks.py`. For every `Benchmark/*.apk`:
  - call `core.static.discover_bridges(path)` and assert `status == "completed"`;
  - assert that the set of `(name, class_name, class_resolution, sorted(method names))` over `registrations` equals the entry in `tests/fixtures/static/ground_truth.json` (SC-001, SC-002);
  - assert the wall-clock time is under 30 s per APK (SC-003). Use `time.monotonic()` and include the measured seconds in the failure message.
  - Also assert that `discover_bridges` on a 4096-byte truncated copy of `Benchmark/strongUpdate.apk` (written to a `tempfile` directory) raises. Assert that `python3 -m core.static <truncated>` (subprocess with `PYTHONPATH=sentry`) exits 2 and prints JSON with `status == "failed"` and a non-empty `error` (SC-005, contracts/cli-static.md).
- [X] T013 [P] [US1] Add `tests/test_report_static.py` and the fixtures `tests/fixtures/static/synthetic_inventory.json` and `tests/fixtures/static/synthetic_failed.json`, hand-written to the schema in contracts/static-artifact.md. Use the existing log `tests/fixtures/logs/synthetic/bridge.log`, run with `sentry/report.py` as in `tests/helpers.run_report`, but with `--static-bridges` appended. Assert:
  - (a) without `--static-bridges`, output equals `tests/fixtures/expected/synthetic__bridge/*` byte for byte (SC-004 guard);
  - (b) with `synthetic_inventory.json`, `report.json` has a `static_bridges` key with `status`, `target_sdk`, `all_public_methods_exposed`, `counts`, `bridges`, `unregistered_classes` and `removals`, and `report.md` contains `## Static Bridge Inventory`, placed after the Origin-to-Bridge Map section;
  - (c) with `synthetic_failed.json`, the Markdown says `Discovery status: failed — <error>`;
  - (d) a path that doesn't exist, or a file with `"schema": 2`, prints `Warning: ignoring static bridge artifact: …` and produces output identical to (a).
  - Compare (b) and (c) against new golden files in `tests/fixtures/expected_static/<case>/{report.json,report.md}`. Add a `--update` path through env `SENTRY_UPDATE_STATIC_GOLDENS=1`, which writes them. These goldens come from the **current** code, because the legacy oracle has no static support.

### Implementation for User Story 1

- [X] T014 [US1] Implement `sentry/core/static/dataflow.py` (header `"""core/static: per-method may-analysis of register values to resolve addJavascriptInterface arguments."""`). Follow research R5 exactly:
  - **Abstract values** are small frozen dataclasses or tuples: `Str(s)`, `New(T)`, `Param(i, T)`, `Field(ref, T)`, `Result(ref, T)`, `Cast(T, inner)`, `TOP`.
  - **State**: `dict[reg, frozenset]`, capped at 8 values per register, after which it becomes `{TOP}`.
  - **Entry state**: the incoming registers are the last `ins_size` registers of `registers_size`. For non-static methods, the first of them is `Param(0, declaring class)`; the rest come from the proto's parameter types, with wide `J`/`D` taking 2 registers.
  - **Worklist**: run over the instruction offsets from `insns.iter_insns`, joining states by union at branch targets and at fall-through. Handler addresses from `tries` start as all-`TOP`.
  - **Transfer**:
    - `const-string` → `Str`;
    - `sget-object` → `Str(value)` if the resolver knows a static string for the field, else `Field`;
    - `iget-object` → `Field`;
    - `move-result-object` → `Result` of the preceding invoke's method ref (track the last invoke on the path);
    - `new-instance` → `New`;
    - `check-cast` wraps the value in `Cast`;
    - `move-object*` copies;
    - every other write → `TOP`.
  - **Call-site detection**: at each invoke whose method ref the resolver flags as `addJavascriptInterface(Object,String)V` or `removeJavascriptInterface(String)V` (research R2), read the receiver, object and name registers from the arg list and emit a `CallSiteFact(offset, kind, name_values, object_values, method_ref_class)`.
  - The public function `analyze_method(code, method_info, resolver) -> list[CallSiteFact]` performs no I/O and no DEX parsing; all lookups go through the resolver.
- [X] T015 [US1] Implement `sentry/core/static/discover.py` (header `"""core/static: find exposed methods and bridge registrations across all dex files and link them."""`):
  - (1) **Class index**: build it across all DEX files in load order, keeping the first definition of each descriptor (the multidex rule). Each entry holds superclass, access flags, the methods with their access flags, protos and annotation types, and a per-DEX resolver adapter for dataflow.
  - (2) **Exposed by annotation**: methods whose annotation types include `Landroid/webkit/JavascriptInterface;`.
  - (3) **Candidate methods**: per DEX, use `find_string("addJavascriptInterface")` and `find_string("removeJavascriptInterface")`. Collect the `method_idx` values whose name matches, whose proto matches `(Ljava/lang/Object;Ljava/lang/String;)V` or `(Ljava/lang/String;)V`, and whose class is `Landroid/webkit/WebView;`, an in-index subclass of it, or not in the index (then `webview_receiver: "unverified"`). Skip the DEX file if none match. Decode a method's code only if its raw insns contain one of those indexes as `<H` bytes preceded by an invoke opcode byte (the pre-filter in research R2). Then call `dataflow.analyze_method`.
  - (4) **`link(facts, index, target_sdk)`**: turn the facts into `BridgeRegistration` and `BridgeRemoval` dicts with exactly the fields, enums and sort order in data-model.md:
    - `name` is null exactly when `name_status == "unresolved"`;
    - `class_resolution` is one of `"exact"`, `"declared-type"`, `"ambiguous"` or `"unknown"`;
    - `candidate_classes` is the list of bridge-capable classes assignable to the declared type, using the superclass and interface closure over the index;
    - `methods` is empty unless `exact` or `declared-type`.
    Compute the effective exposed set per research R3 and R4. Build `bridge_classes` with `registered` set as specified.
  - (5) **`sensitive`**: `bool(SENSITIVE_METHOD_RE.search(name))`, with the regex imported from `core.report.rules.catalog`.
  - (6) **Names**: convert all class and type names with `dex.descriptor_to_java`.
- [X] T016 [US1] Implement `discover_bridges(apk_path) -> dict` in `sentry/core/static/__init__.py`:
  - Open the `Apk`, read the manifest with `axml`, iterate the DEX files, and call `discover`.
  - Return the full `StaticDiscoveryResult` with `schema: 1`, `status: "completed"`, `error: None`, `apk {path, sha256, dex_files}`, `package`, `min_sdk`, `target_sdk`, `all_public_methods_exposed`, `registrations`, `removals`, `bridge_classes`, and `stats {classes, methods_scanned, seconds}`.
  - Raise on any error, leaving it to the caller to build the failed artifact.
  - Also add `failed_result(apk_path, exc, seconds) -> dict`. It builds the failed artifact with `error` set to `f"{type(exc).__name__}: {exc}"`, collapsed to one line and truncated to ≤ 200 characters (data-model.md), with empty lists and the other fields `None`, `False` or `[]`. Fill `apk.sha256` when the file is readable.
- [X] T017 [US1] Implement `sentry/core/static/__main__.py` exactly per contracts/cli-static.md:
  - The arguments are `<APK-FILE> [--out PATH]`.
  - A missing file prints `Error: file not found: <path>` and exits 1.
  - On a completed scan, write JSON with `indent=2, sort_keys=True` and a trailing newline to stdout, or to `--out`, creating its parent directories. With `--out`, also print the summary line `Static bridge discovery: <R> registration(s), <U> with unresolved names, <C> bridge class(es) -> <PATH>`. Exit 0.
  - On an exception, write `failed_result` the same way and exit 2.
- [X] T018 [US1] Add a `static_bridges` path (`target/static-bridges.json`) to `sentry/core/run/workspace.py`, and in `prepare()` call `self.static_bridges.unlink(missing_ok=True)` next to the existing report deletions.
- [X] T019 [US1] Create `sentry/core/run/discovery.py` (header `"""core/run: run static bridge discovery before the dynamic run; never fails the run."""`, ≤ 100 lines). `run_discovery(host, workspace) -> None` does the following:
  - call `core.static.discover_bridges(workspace.apk)`;
  - on success, write the artifact (indent 2, sorted keys, trailing newline) and `host.echo` the summary line from contracts/cli-analyse-option.md step 10, using the literal path `target/static-bridges.json`;
  - on `Exception`, write `failed_result(...)` and `host.echo(f"Warning: static bridge discovery failed: {error}")`;
  - not catch `KeyboardInterrupt` or `SystemExit` (research R6).
- [X] T020 [US1] Wire discovery into `AnalysisSession.run` in `sentry/core/run/session.py`. Inside the `with report_on_exit(...)` block, call `run_discovery(self.host, self.workspace)` before `runner.run(context)`, gated by a `discover` flag that defaults to `True`; US3 wires the flag to the CLI. Keep the file ≤ 100 lines.
- [X] T021 [US1] In `sentry/core/run/reporting.py::generate_report`, append `["--static-bridges", str(workspace.static_bridges)]` to the report CLI argv **only when** `workspace.static_bridges.is_file()`. The "Report skipped: no Sentry events were captured" path is unchanged, and the artifact is left in place.
- [X] T022 [US1] Add `--static-bridges PATH` (`dest="static_bridges"`, `type=Path`, `default=None`) to `sentry/core/report/cli.py` and load it there, the only place that does I/O:
  - accept the artifact only if it is a dict with `schema == 1`;
  - otherwise `print(f"Warning: ignoring static bridge artifact: {reason}")` (reasons: `not found`, `invalid JSON`, `unsupported schema <n>`) and treat it as absent;
  - pass the parsed dict, or `None`, to `Analyzer(set(args.trusted_origin), static=...)`;
  - leave the existing stdout summary line unchanged.
- [X] T023 [US1] Create `sentry/core/report/correlate.py` (header `"""core/report: join static bridge registrations with runtime-observed bridges (pure, no findings)."""`). For US1, `correlate(static, tracker) -> dict` returns the `static_bridges` section from contracts/report-static-section.md:
  - `status`, `error`, `target_sdk` and `all_public_methods_exposed`;
  - `counts` with `registrations`, `unresolved_names` and `bridge_classes` set; the provenance counts are 0 until US2;
  - `bridges`, one entry per static registration with `interfaceName`, `className`, `provenance: "static-only"`, `static` (the registration with `call_site.dex` and `call_site.offset` removed), `runtime_webviews: []` and `sensitive_methods`;
  - `unregistered_classes`, the `bridge_classes` with `registered == false`;
  - `removals`.
  When `status == "failed"`, the static lists are empty.
- [X] T024 [US1] Update `sentry/core/report/analyzer.py`:
  - `Analyzer.__init__(self, trusted_origins, static=None)` stores `static`;
  - `build_report` passes it to `assemble.build_report(..., static_section=correlate.correlate(static, self.tracker) if static is not None else None)`.
  Keep the existing signature behaviour when `static` is `None`.
- [X] T025 [US1] Update `sentry/core/report/assemble.py::build_report` to accept `static_section=None` and add `"static_bridges": static_section` **only when it is not `None`**. No other keys change, so existing goldens stay identical.
- [X] T026 [US1] Update `sentry/core/report/markdown.py`. When `report.get("static_bridges")` is present, append the `## Static Bridge Inventory` section **after** the Origin-to-Bridge Map section, exactly per contracts/report-static-section.md:
  - the status line (`completed`, or `failed — <error>`);
  - the target SDK line (`unknown` when null);
  - the registrations and bridge-classes line;
  - the coverage line;
  - the pre-17 warning blockquote only when `all_public_methods_exposed`;
  - one `### \`<name>\` → <class>  [<provenance>]` block per bridge with `Registered in`, `Class resolution`, `Exposed methods` (`name(params)` joined by `, `) and `Sensitive methods` (or `none`).
  Unresolved names render as `` `<unresolved: <kind> <ref>>` ``, and ambiguous classes as `one of: A, B`. The empty subsections "Bridge-capable classes with no discovered registration" and "Bridge removals" are left out. If adding this pushes `markdown.py` over 340 lines, move the section into a new `sentry/core/report/markdown_static.py` and call it from `markdown.py`.
- [X] T027 [US1] Update `sentry/core/benchmark/suite.py::archive`: add `("target/static-bridges.json", "static-bridges.json")` to the copy list, and add `"static-bridges.json"` to the `ARCHIVED` tuple so stale copies are removed (FR-017). Keep the file ≤ 160 lines.
- [X] T028 [US1] Generate `tests/fixtures/expected_static/` with `SENTRY_UPDATE_STATIC_GOLDENS=1 python3 -m unittest tests.test_report_static`. Review the generated `report.md` against contracts/report-static-section.md by hand, then run the full suite. The original `tests/fixtures/expected/` must be unchanged (`git status` shows no change there).

**Checkpoint**: US1 is fully usable. The scan runs by default, the artifact is written, the report shows the inventory, and failures are isolated. This is the MVP.

---

## Phase 4: User Story 2 - Compare static and runtime bridge findings (Priority: P2)

**Goal**: Each bridge in the inventory is labelled `static+runtime`, `static-only` or `runtime-only` (FR-012). Each static-only bridge gets an info-severity `WV-STATIC-BRIDGE-UNOBSERVED` finding that adds nothing to the risk score (FR-013).

**Independent Test**: Run the report on `tests/fixtures/logs/synthetic/bridge.log` with `tests/fixtures/static/synthetic_mixed.json`, an artifact containing one bridge that matches the log, one that doesn't, and none of the log's other bridges. The JSON shows all three provenance values, one `WV-STATIC-BRIDGE-UNOBSERVED` finding, and the same `risk_score` as without the option.

### Tests for User Story 2

- [X] T029 [P] [US2] Create `tests/fixtures/static/synthetic_mixed.json`:
  - read `tests/fixtures/logs/synthetic/bridge.log` to get the runtime `interfaceName` and `className` of its `BRIDGE_ADDED` events;
  - include one registration matching one of them;
  - include one registration with a name and class not in the log;
  - include one with `name_status: "unresolved"` whose `candidate_classes` contain a runtime class from the log.
  Then extend `tests/test_report_static.py` with a `synthetic__static_mixed` case asserting:
  - (a) the provenance set is `{"static+runtime", "static-only", "runtime-only"}` whenever the log has more than one runtime bridge; otherwise assert the two applicable values;
  - (b) the unresolved registration matches by class (research R8);
  - (c) exactly one `WV-STATIC-BRIDGE-UNOBSERVED` finding, with severity `info` and the evidence keys `interfaceName`, `className`, `nameStatus`, `classResolution`, `candidateClasses`, `callSite`, `methods` and `sensitiveMethods`;
  - (d) `summary.risk_score` equals the score of the run without `--static-bridges`;
  - (e) `counts.static_and_runtime`, `counts.static_only` and `counts.runtime_only` agree with `bridges`;
  - (f) the bridges are ordered static+runtime, then static-only, then runtime-only, then by `interfaceName` and `className`.
  Add a golden in `tests/fixtures/expected_static/synthetic__static_mixed/`.

### Implementation for User Story 2

- [X] T030 [US2] Extend `sentry/core/report/correlate.py`. Collect runtime bridges from `tracker.webviews[*]["bridges"]` (keyed by interface name, holding `className`) across all WebViews, and match them per the data-model.md BridgeCorrelation rule:
  - **Match condition**: names are equal (or the static name is unresolved), **and** classes are equal (or the static `class_name` is null and the runtime class is in `candidate_classes`).
  - **Merging**: matches across WebViews collapse into one entry with `runtime_webviews` sorted.
  - **Runtime-only**: unmatched runtime bridges become `runtime-only` entries with `static: null`.
  - **`sensitive_methods`**: add runtime method names from `state["bridge_methods"]` that match `SENSITIVE_METHOD_RE`. Import the regex from `core.report.rules.catalog`; this is allowed because correlate is not tracker, assemble or markdown.
  - Fill the three provenance counts and sort as specified.
  - When the artifact `status == "failed"`, emit only runtime-only entries.
- [X] T031 [US2] Create `sentry/core/report/rules/static_bridges.py` (header `"""core/report/rules: findings for JavaScript bridges found statically but never observed at runtime."""`). Add `detect_static_unobserved(section: dict, findings: FindingStore) -> None`, which adds one `WV-STATIC-BRIDGE-UNOBSERVED` finding (severity `"info"`) per `static-only` bridge:
  - title, description, recommendation and evidence keys exactly as in contracts/report-static-section.md;
  - `callSite` is `f"{call_site['class']}.{call_site['signature']}"`;
  - fingerprint `f"WV-STATIC-BRIDGE-UNOBSERVED:{name or '?'}:{class or '?'}"`.
  No I/O.
- [X] T032 [US2] In `sentry/core/report/analyzer.py::build_report`, after all events are observed and before `assemble`, compute `section = correlate.correlate(...)` once. When a static result is present, call `rules.static_bridges.detect_static_unobserved(section, self.findings)`, then pass `section` to `assemble`. Register nothing in the `DETECTORS` table: this rule runs once per report, not per event. Document that in a one-line comment in `sentry/core/report/rules/__init__.py` next to the imports, and import the module there so it is part of the rules package.
- [X] T033 [US2] In `sentry/core/report/markdown.py` (or `markdown_static.py`), render the `[provenance]` tag per bridge and the coverage line from `counts`. For `runtime-only` entries, render `Registered in: not found statically` and the runtime method names.
- [X] T034 [US2] Update `tests/test_report_golden.py::ALL_RULE_IDS` only if that test asserts the rule set from the catalog or findings source. If it checks only rule IDs that appear in the legacy goldens, leave it unchanged and assert the new rule ID in `tests/test_report_static.py` instead. Then regenerate `tests/fixtures/expected_static/` for the US1 cases if their content changed (provenance and counts) and review the diff.

**Checkpoint**: US1 and US2 both work. The report shows coverage gaps, and the risk score is unaffected by static-only data.

---

## Phase 5: User Story 3 - Turn discovery off (Priority: P3)

**Goal**: `--discover-bridge-interfaces[=<bool>]` and `--no-discover-bridge-interfaces` control the scan (default on). Invalid values fail early. With discovery off, the output is identical to today's (FR-001 to FR-003, FR-016, FR-018).

**Independent Test**: `./analyse.sh --discover-bridge-interfaces=maybe x.apk` exits 1 with the invalid-value error and leaves `target/` untouched. `./analyse.sh --no-discover-bridge-interfaces missing.apk` prints `File not found: missing.apk`. A session test with a fake runner and discovery off produces no `target/static-bridges.json` and no discovery line.

### Tests for User Story 3

- [X] T035 [P] [US3] Add `tests/test_static_discovery_run.py`. Use `tests/fakes.py` (the fake host and fake runner already used by `tests/test_runners.py` and `tests/test_local_simulation.py`; reuse their patterns) to run `AnalysisSession` in a temporary workspace with `Benchmark/strongUpdate.apk`. Assert:
  - (a) by default: `target/static-bridges.json` exists with `status: "completed"`, the summary line is echoed before the runner runs, and `generate_report` receives `--static-bridges` (check the report CLI argv through a patched `core.report.cli.main`);
  - (b) with `--no-discover-bridge-interfaces`: no artifact, no discovery line, and the echoed lines equal those of a run on the code before this feature (assert the exact list);
  - (c) with a corrupt APK: the warning line is printed, the artifact has `status: "failed"`, the runner is still called, and `run()` returns 0 (SC-005);
  - (d) a stale `target/static-bridges.json` from an earlier run is removed by `prepare()` even when discovery is off.
- [X] T036 [P] [US3] Add `tests/test_run_options.py` for `core.run.options.parse_args`:
  - with no option → `discover=True`;
  - bare flag → True;
  - `=true`/`=YES`/`=on`/`=1` → True;
  - `=false`/`=No`/`=off`/`=0` → False;
  - `--no-discover-bridge-interfaces` → False;
  - the last option wins;
  - the option before, between or after the positionals leaves `positionals == ["a.apk", "pkg"]`;
  - `--foo` is kept as a positional;
  - `=maybe` and `=` raise `OptionError` with the message `invalid value 'maybe' for --discover-bridge-interfaces (expected true or false)`.
- [X] T037 [P] [US3] Update `tests/test_cli_contract.py`:
  - in `test_no_args`, also assert the `Options: --[no-]discover-bridge-interfaces[=true|false]  static JavaScript bridge discovery (default: true)` line;
  - in `test_matches_legacy_output`, for the `no_args` scenario, compare `current.stdout` with `legacy.stdout` plus that line (contracts/cli-analyse-option.md, "Intentional deviations"), and keep byte equality for the other scenarios;
  - add `test_invalid_discovery_value`: `["--discover-bridge-interfaces=maybe", "README.md", "pkg"]` → exit 1, stdout contains `Error: invalid value 'maybe' for --discover-bridge-interfaces (expected true or false)`, and `target/.env` is unchanged (same pattern as `test_bad_runner_has_no_side_effects`).

### Implementation for User Story 3

- [X] T038 [US3] Create `sentry/core/run/options.py` (header `"""core/run: command-line options for analyse.sh; positional arguments pass through untouched."""`, ≤ 100 lines). It provides `class OptionError(ValueError)` and `parse_args(argv) -> tuple[list[str], bool]`, implementing research R7 exactly:
  - match `--discover-bridge-interfaces`, `--discover-bridge-interfaces=<v>` and `--no-discover-bridge-interfaces`;
  - the truthy set is `{"true", "yes", "on", "1"}` and the falsy set is `{"false", "no", "off", "0"}`, compared case-insensitively;
  - the last option wins;
  - everything else, including other `--x` arguments, is a positional, in order.
  Also export `USAGE_OPTIONS = "Options: --[no-]discover-bridge-interfaces[=true|false]  static JavaScript bridge discovery (default: true)"`.
- [X] T039 [US3] Update `sentry/core/run/session.py`:
  - in `run()`, right after the banner echo and before the `has_kvm` and `require_commands` calls, call `parse_args`;
  - on `OptionError`, call `self.host.die(f"Error: {exc}")` (exit 1, workspace untouched);
  - pass the positionals to `validate_apk` and `resolve_package`, and the boolean to the T020 gate;
  - make the usage error print `Usage: {prog} <apk> [<apk-package>]` followed by `USAGE_OPTIONS` on the next line, using two `echo` calls or one `die` with an embedded newline, whichever matches how `host.die` prints.
  Keep the file ≤ 100 lines; move helpers to `options.py` if needed.
- [X] T040 [US3] Check FR-016 by hand: run `python3 -m unittest tests.test_static_discovery_run tests.test_cli_contract tests.test_run_options` and the full suite. Confirm that the `tests/fixtures/expected/` goldens are untouched.

**Checkpoint**: All three user stories work on their own.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation (FR-018), architecture notes and end-to-end validation.

- [X] T041 [P] Update `README.md`:
  - add a "Static bridge discovery" section after "Outputs" covering the default-on behaviour, `--no-discover-bridge-interfaces` and `--discover-bridge-interfaces=false`, the new `target/static-bridges.json` output, the new report section and the `WV-STATIC-BRIDGE-UNOBSERVED` info finding;
  - document the standalone `PYTHONPATH=sentry python3 -m core.static <apk> [--out PATH]`;
  - add `target/static-bridges.json` to the Outputs list;
  - note the intra-procedural limits (unresolved names, dynamically loaded code is out of scope).
- [X] T042 [P] Update `sentry/core/README.md`:
  - add a `static/` row to the sub-area table;
  - add rows to "Where does my change go?" for "Static bridge discovery (DEX parsing, call-site resolution)" → `static/`, and "analyse.sh options" → `run/options.py`;
  - add to Rules: "`static/` runs no processes and imports nothing from `run/`, `runners/` or `benchmark/`; its only `report/` import is `rules/catalog.SENSITIVE_METHOD_RE`. `report/` never imports `static/`; the artifact file is the contract.";
  - add `static/` ≤ 340 lines to the size limits.
- [X] T043 [P] Update the `AnalysisSession` step list in the `run/` row of `sentry/core/README.md` to read: validate options → validate → resolve package → choose runner → preflight → prepare workspace → **static discovery** → run → report on exit.
- [X] T044 Run every scenario in `specs/002-static-bridge-discovery/quickstart.md`, 0 to 4 and 7. Scenarios 5 and 6 need a device or emulator; run them if one is available, and otherwise record them as not run. Record the measured scan time for each benchmark APK in the T044 commit message or a short note at the end of quickstart.md.
- [X] T045 Mark `specs/002-static-bridge-discovery/checklists/requirements.md` and the spec's Status as implemented once the full suite passes. Write a short traceability note at the end of `plan.md` mapping FR-001 to FR-018 and SC-001 to SC-006 to tasks and tests.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: needs T001. T004 to T009 are all [P] and independent of each other.
- **US1 (Phase 3)**: needs Phase 2. This is the MVP.
- **US2 (Phase 4)**: needs US1's report plumbing (T022 to T026), because correlation extends `correlate.py`. It does not need the scanner: it can be built against the synthetic artifacts as soon as T022 to T026 exist.
- **US3 (Phase 5)**: needs T019 and T020 (the discovery gate). It is independent of US2.
- **Polish (Phase 6)**: after the stories you intend to ship.

### Within US1

```
T010, T011, T012, T013 (tests, parallel)
T014 dataflow ──▶ T015 discover ──▶ T016 discover_bridges ──▶ T017 __main__
                                                    └──▶ T018 workspace ──▶ T019 run/discovery ──▶ T020 session ──▶ T021 reporting
T022 cli ──▶ T023 correlate ──▶ T024 analyzer ──▶ T025 assemble ──▶ T026 markdown ──▶ T028 goldens
T027 benchmark archive (independent)
```

T022 to T026 (report side) can run in parallel with T014 to T017 (scanner side): they share only the artifact contract.

### Within US2

T029 ──▶ T030 ──▶ T031 ──▶ T032 ──▶ T033 ──▶ T034

### Within US3

T035, T036 and T037 in parallel ──▶ T038 ──▶ T039 ──▶ T040

### Parallel Opportunities

- Phase 2: T004, T005, T006, T007, T008 and T009 are six separate files.
- US1: the four test files T010 to T013. The scanner chain T014 to T017 runs alongside the report chain T022 to T026. T027 can run any time.
- US2 and US3 can be built in parallel once US1's T019, T020 and T022 to T026 are done.
- Polish: T041, T042 and T043.

---

## Parallel Example: User Story 1

```bash
# Tests first, all independent files:
Task: "T010 tests/test_static_dataflow.py"
Task: "T011 tests/test_static_discover.py"
Task: "T012 tests/test_static_benchmarks.py"
Task: "T013 tests/test_report_static.py + fixtures"

# Then two independent chains:
Task: "Scanner chain T014 → T015 → T016 → T017 (sentry/core/static/)"
Task: "Report chain T022 → T023 → T024 → T025 → T026 (sentry/core/report/)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 and Phase 2: the readers, unit-tested.
2. Phase 3: the scanner passes `test_static_benchmarks` (SC-001 to SC-003), the run integration writes the artifact, and the report shows the inventory.
3. **Stop and validate**: quickstart scenarios 0 to 3 and 7. Discovery is always on at this point. That's acceptable for the MVP because failure is isolated, but US3 is needed before release.

### Incremental Delivery

1. MVP (US1): the static inventory.
2. US2: the coverage comparison and the info finding.
3. US3: the off switch, usage text and contract test update.
4. Polish: the docs and the end-to-end quickstart.

### Risk notes

- **DEX parsing correctness** (T006, T007) carries the most risk. T008 and T009 plus the 8 real benchmark APKs in T012 are the safety net. If a benchmark fails, check the opcode width table first.
- **Performance** (SC-003) depends on the T015 pre-filter. If T012's timing fails, profile `class_methods` iteration over the 9 MB `classes.dex` before optimising anything else.

---

## Notes

- [P] tasks touch different files and have no dependency on an unfinished task.
- The [Story] label maps a task to its user story for traceability.
- Commit after each task or logical group. Run the full suite before every commit.
- Never regenerate `tests/fixtures/expected/`; only `tests/fixtures/expected_static/` is produced from the current code.
