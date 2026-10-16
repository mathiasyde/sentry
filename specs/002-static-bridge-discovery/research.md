# Research: Static JavaScript Bridge Discovery

Each entry gives the decision, why it was made, and what else was considered.

## R1. Analysis engine: stdlib DEX reader vs. library vs. external tool

- **Decision**: Write a small, stdlib-only reader for the parts of the DEX format and Android binary XML that the analysis needs. It lives in `sentry/core/static/`.
- **Rationale**:
  - The host currently needs only `python3`, `adb` and `frida`, with no pip packages (Docker installs only `frida-tools`, inside the container).
  - Only `host.py` may start processes, which rules out any tool that runs as a subprocess.
  - The analysis needs a limited slice of the format: the id tables, class defs and class data, annotation directories, static values, and code items with an opcode width table. That is roughly 700 lines across 4 modules, all unit-testable without a device.
- **Alternatives considered**:
  - *Androguard*. Mature, and handles the parsing and instruction decoding. But it is the first host pip dependency, with a heavy transitive set (lxml, networkx, loguru, …) and Python 3.14 compatibility risk. It also does no call-site argument resolution, so we would still write the dataflow.
  - *jadx / baksmali*. Need a JVM, a subprocess, and parsing of decompiled text. That is fragile, and slow on 9 MB DEX files.
  - *`aapt dump xmltree` for the manifest*. `aapt` is optional when the package name is given, so we can't rely on it. Our own AXML reader is about 100 lines.

## R2. Which code counts as a bridge registration

- **Decision**: A call site is any `invoke-virtual`, `invoke-virtual/range`, `invoke-super` or `invoke-direct` whose method reference has:
  - the name `addJavascriptInterface`,
  - the prototype `(Ljava/lang/Object;Ljava/lang/String;)V`,
  - a declaring class that is `Landroid/webkit/WebView;` or a subclass of it known in the APK.

  A reference whose declaring class is unknown (not in the APK and not WebView) is accepted when its name and prototype match, and is flagged `webview_receiver: "unverified"`. Calls to `removeJavascriptInterface(String)` are collected the same way, as removal sites.
- **Rationale**: Apps often call through their own `WebView` subclass (`Lcom/x/MyWebView;->addJavascriptInterface`). Matching only the framework class would miss these.
- **Fast path**: `string_ids` are sorted, so finding `"addJavascriptInterface"` is a binary search. If the name is absent from a DEX file, that file's bytecode is never scanned. Where it is present, a method's instructions are decoded only if its raw code bytes contain one of the target `method_idx` values as a 16-bit little-endian value (a cheap `bytes.find` pre-filter).

## R3. Exposed methods and inheritance

- **Decision**:
  - A method is *exposed by annotation* when its method annotation set holds a `Landroid/webkit/JavascriptInterface;` annotation (any visibility; `RUNTIME` in practice).
  - For a registered class C, the exposed set is computed like `Class.getMethods()` filtered by `isAnnotationPresent`. Walk C, then its superclasses that are defined in the APK. For each name and prototype, the most-derived **public** declaration decides. An override without the annotation hides an annotated superclass method.
  - Interface methods are ignored, because annotations on interface methods are not inherited by implementations.
- **Rationale**: This matches what WebView actually exposes at run time, so static and runtime method lists agree.

## R4. Pre-API-17 rule

- **Decision**: Read `targetSdkVersion` from the binary manifest (falling back to `minSdkVersion`, then "unknown").
  - When the value is below 17, every **public** method of each registered class and its in-APK superclasses is reported, with `exposure: "public-pre-17"`. The result also carries `all_public_methods_exposed: true`, and the report notes that `java.lang.Object` methods such as `getClass()` are reachable too.
  - When the value is unknown, the API-17+ rule applies and `target_sdk: null` is recorded.
- **Rationale**: Before API 17, WebView exposes all public methods (CVE-2012-6636). A target given as a resource reference is rare, and guessing it would be worse than saying it is unknown.

## R5. Resolving the name and object arguments (dataflow)

- **Decision**: A forward may-analysis over the instructions of each candidate method, using a worklist over basic-block boundaries.
  - **State**: each register maps to a set of abstract values, capped at 8 entries. Above the cap the register becomes `TOP`, meaning unknown.
  - **Abstract values**:
    - `Str(s)` from `const-string` or `const-string/jumbo`, or from `sget-object` of a field whose class's `static_values` holds a string.
    - `New(T)` from `new-instance`.
    - `Param(i, T)` for incoming registers, with `p0 = this` of the declaring class for instance methods.
    - `Field(ref, T)` from `iget-object` or `sget-object` without a known constant.
    - `Result(ref, T)` from `move-result-object`.
    - `Cast(T, v)` from `check-cast`, which narrows the declared type.
    - `TOP` for anything else.
  - **Transfer**: `move-object*` copies values, any other write sets `TOP`, and wide writes clobber two registers.
  - **Control flow**:
    - Edges come from fall-through, `goto*`, `if-*`, and packed and sparse switches (payloads decoded).
    - Exception handler entries start with all registers `TOP`. This is conservative, and the handler's own code still defines what it uses.
    - `return*` and `throw` end a block.
- **Name outcome per call site**:
  - All values are `Str` → one registration per distinct string, with `name_status: "resolved"`.
  - Any other value → `name_status: "unresolved"`, plus `name_source` describing the producer (for example `{"kind": "method-result", "ref": "Lcom/x/Cfg;->bridgeName()Ljava/lang/String;"}`, or `"parameter"`, `"field"`, `"unknown"`).
- **Object outcome per call site**:
  - All values are `New(T)` → `class_resolution: "exact"`.
  - Otherwise take the declared, narrowed or param type T and list every bridge-capable class assignable to T. One candidate → `"declared-type"`, several → `"ambiguous"`, none → `"unknown"`.
- **Rationale**: Last-write-wins linear scanning gives wrong answers when a name is chosen across branches. The may-sets report every possible name and never guess. The cap and `TOP` keep the analysis bounded.
- **Alternatives considered**:
  - *Linear last-definition scan*: simpler, but unsound across branches.
  - *Inter-procedural constant propagation*: out of scope per the spec. Its absence shows up as `unresolved` with a `name_source` hint.

## R6. Where the scan runs, and failure isolation

- **Decision**: In-process on the host, in `AnalysisSession` after `workspace.prepare()` (so the APK is in `target/app.apk`) and before `runner.run()`, inside `report_on_exit`.
  - `run/discovery.py` wraps the scan in `try/except Exception`.
  - On error it writes an artifact with `status: "failed"` and a one-line `error`, prints `Warning: static bridge discovery failed: <reason>`, and continues.
  - `KeyboardInterrupt` and `SystemExit` are not caught, so Ctrl-C keeps exiting with 130.
- **Rationale**: It works the same for the Docker and local runners with no image change, and it meets FR-004, FR-011 and FR-015.

## R7. Option grammar

- **Decision**:
  - Accepted anywhere among the arguments: `--discover-bridge-interfaces`, `--discover-bridge-interfaces=<v>` and `--no-discover-bridge-interfaces`.
  - `<v>` is matched case-insensitively against `true|yes|on|1` and `false|no|off|0`.
  - The last occurrence wins.
  - Any other argument is passed through untouched as a positional, so `--foo` still gives `File not found: --foo` as it does today.
  - The space-separated form (`--discover-bridge-interfaces false`) is **not** supported: `false` would be taken as the APK path. The bare flag always means true.
  - A bad value prints `Error: invalid value '<v>' for --discover-bridge-interfaces (expected true or false)` and exits 1, before any workspace or device work.
- **Rationale**: This is the usual GNU long-option form, and it can't be confused with positional arguments.

## R8. How the report uses static results

- **Decision**:
  - The report CLI reads `--static-bridges PATH`.
  - `report/correlate.py` joins static registrations with the tracker's runtime bridges on `(interface name, class name)`. Runtime class names are dotted, so static descriptors are converted to dotted form. Unresolved names fall back to matching on class alone.
  - Provenance values are `static+runtime`, `static-only` and `runtime-only`.
  - New finding `WV-STATIC-BRIDGE-UNOBSERVED`, severity **info**, worth 0 points: one per static-only registration, with the evidence noting sensitive methods.
  - Bridge-capable classes with no registration appear only in the inventory, not as findings.
- **Rationale**: FR-013 says static-only results must not raise the risk score without runtime evidence. Info severity keeps the score unchanged while still listing the finding.
- **Byte-identity**: The `static_bridges` key and the Markdown section exist only when the option is passed. This keeps every existing golden fixture unchanged (SC-004).

## R9. Ground truth for SC-001 and SC-002

- **Decision**: Commit `tests/fixtures/static/ground_truth.json`, built by hand from the sources in `Benchmark/*.zip`. Every one of the eight APKs registers `"Android"`:
  - `strongUpdate` and `strongUpdatecaseA` → `com.example.strongupdate.BridgeClass` with `showData()`;
  - the other six → their `MainActivity`, with `getData()`. The object is a fresh `new MainActivity()`, not `this`.

  In all eight sources the object comes from `new X()`, so every benchmark expects `class_resolution: "exact"`. The test asserts exact name, class and method sets, and a time budget.

  The benchmarks never exercise `Param(0)`/`this`, unresolved names, ambiguous classes, branches or pre-17 targets. Those paths are covered by `test_static_dataflow.py` and `test_static_discover.py`, using hand-assembled code units and a fake class index.
- **Rationale**: These APKs are already in the repo, are real multidex builds with AndroidX (a realistic size), and come with their sources.

## R10. Performance

- **Decision**:
  - Parse lazily: read a string only when it is looked up, and parse class data for every class but decode instructions only for methods that pass the R2 pre-filter.
  - Build the class index (descriptor → class def, superclass) once across all DEX files.
  - Budget: under 10 s per benchmark APK. The `test_static_benchmarks` time assertion is set loosely, at 30 s.
- **Rationale**: Instruction decoding dominates the cost, and the pre-filter cuts it to a handful of methods.

## R11. Sensitivity flag

- **Decision**: `static/discover.py` imports `SENSITIVE_METHOD_RE` from `core/report/rules/catalog.py`, the same pattern the report's runtime rule uses.
- **Rationale**: One source of truth for FR-009. It is the only dependency from `static/` into `report/`, and the reverse dependency is forbidden by a layering test.

## R12. Instrumenting discovered bridges (added 2026-10-16)

- **Decision**: The agent bundler takes `--static-bridges <artifact>` and embeds `const STATIC_BRIDGES = Object.freeze([...])`.
  - Each entry is one method target: `{className, method, args, interfaceName}`.
  - `className` is the **declaring** class.
  - `args` uses `Class.getName()` form (`[B`, `[Ljava.lang.String;`), as Frida overloads and the runtime signatures expect.
  - `interfaceName` is set only when exactly one resolved name maps to the class.

  `native/static_bridges.js` hooks every target when the agent loads, through the same call hook `javascript_bridge.js` uses (`ctx.hookBridgeCall`), so the two paths share one dedupe table. Classes that aren't loadable yet (lazily loaded, or behind another class loader) are retried on each polling tick, up to 60 ticks. Each attempt tries `Java.use`, then every loader from `Java.enumerateClassLoadersSync()`.
- **Delivery**:
  - The local runner passes the artifact when it builds the agent for each run.
  - The `sentry` container rebuilds the agent into `/sentry/target/agent.js` when the artifact is present, and falls back to the prebuilt `/sentry/build/agent.js` if the build fails. It prints nothing, because its stdout is the event stream.
- **Events**: no new event type, because the vocabulary must stay equal to the legacy agent's. Successful pre-hooks are silent. Failures reuse `js.probe.error` with `source: "bridge.static.hook"`. Calls use the existing `bridge.method.called`. When the registration was never seen, `webViewId` is null and the report files the call under WebView `unknown`.
- **Alternatives considered**:
  - *Frida `-P` parameters*: needs an RPC `init` handshake and works differently in the Docker entry.
  - *Hooking `ClassLoader.loadClass`*: catches every class load, but costs a hook on a very hot path.
  - *A new event type for "pre-hooked"*: would break the legacy event-vocabulary contract.
