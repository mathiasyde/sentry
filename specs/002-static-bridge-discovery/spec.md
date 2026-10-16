# Feature Specification: Static JavaScript Bridge Discovery

**Feature Branch**: `002-static-bridge-discovery`

**Created**: 2026-10-16

**Status**: Implemented (2026-10-16)

**Input**: User description: "I want you to implement a static analysis that will look for the functions which are annotated with addJavaScriptInterface and the fetch the bridge object name from the apk file. This will be enabled with --discover-bridge-interfaces option. the default value is true"

## Overview

Sentry finds JavaScript bridges only at run time, when the app actually calls `addJavascriptInterface` while being exercised. A bridge that sits on a code path the run never reaches is missing from the report. This feature adds a static pass over the APK, run before the dynamic run. It finds:

- the native methods exposed to web content (those marked with the `@JavascriptInterface` annotation),
- the classes that declare them,
- the `addJavascriptInterface` registration sites, with the JavaScript-visible bridge object name used at each.

The pass is controlled by a new `--discover-bridge-interfaces` option and is on by default.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See every bridge an APK can expose, including ones the run never triggered (Priority: P1)

A security analyst runs `./analyse.sh app.apk` as usual. Before the dynamic run starts, Sentry inspects the APK. When the reports are written, they include a list of the JavaScript bridges the app can register. Each entry gives the bridge object name visible to JavaScript (for example `Android` in `window.Android.getToken()`), the native class behind it, and its exposed methods. The analyst no longer has to decompile the APK by hand to check for bridges the run missed.

**Why this priority**: This is the core value: bridges show up whether or not the dynamic run reached them. It is useful on its own, without the comparison in Story 2.

**Independent Test**: Run the analysis on a benchmark APK with a known bridge (for example `Benchmark/JsUpdateCaseF.apk`). Check that the reports list the bridge name, class and exposed methods, even if no Sentry events were captured at run time.

**Acceptance Scenarios**:

1. **Given** an APK that registers a bridge object under a literal name, **When** the analyst runs the analysis with default options, **Then** the reports list that name, the class that implements it, and every method of that class marked as exposed to JavaScript.
2. **Given** an APK with several bridge registrations across different screens, **When** the analysis runs, **Then** every registration is listed, including ones in code the dynamic run never executes.
3. **Given** an APK with no bridge registrations and no exposed methods, **When** the analysis runs, **Then** the reports say that static discovery ran and found no bridges. "Discovery found nothing" must read differently from "discovery did not run".
4. **Given** an exposed method whose name suggests sensitive capability (token, file, location, etc.), **When** it is discovered statically, **Then** it is flagged as sensitive, using the same rule as runtime-observed bridge methods.

---

### User Story 2 - Compare static and runtime bridge findings (Priority: P2)

The analyst reads the report and sees, for each statically discovered bridge, whether the dynamic run also saw it registered. Bridges found only statically are marked "not observed at runtime". This shows the analyst where coverage is missing and where to drive the app further. Bridges seen only at run time (for example, ones loaded from code the static pass could not see) are marked too.

**Why this priority**: The comparison makes the static results actionable and measures how much of the attack surface the run covered. It depends on Story 1.

**Independent Test**: Run an APK where one bridge is registered at startup and another only after a user action that the run does not perform. Check that the first is marked "observed at runtime" and the second "static only".

**Acceptance Scenarios**:

1. **Given** a bridge found both statically and at run time under the same name and class, **When** the report is generated, **Then** it appears once, marked as confirmed by both sources.
2. **Given** a bridge found statically but never registered during the run, **When** the report is generated, **Then** it is listed and marked "static only".
3. **Given** a bridge registered at run time that the static pass did not find, **When** the report is generated, **Then** it is listed and marked "runtime only".

---

### User Story 3 - Turn discovery off (Priority: P3)

The analyst who wants a faster run, or a run that matches earlier output exactly, passes the option with a false value (for example `--discover-bridge-interfaces=false` or `--no-discover-bridge-interfaces`). Sentry then skips the static pass. The run and its reports match what Sentry produced before this feature.

**Why this priority**: Discovery is on by default, so turning it off is a secondary control. It still matters for reproducibility and speed.

**Independent Test**: Run the same APK with discovery disabled. Check that no static bridge section or static artifact is produced, and that the rest of the report matches the output from before this feature.

**Acceptance Scenarios**:

1. **Given** no discovery option on the command line, **When** the analysis runs, **Then** static discovery runs.
2. **Given** `--discover-bridge-interfaces` with no value or with a true value, **When** the analysis runs, **Then** static discovery runs.
3. **Given** discovery explicitly disabled, **When** the analysis runs, **Then** static discovery does not run and the reports contain no static bridge section.
4. **Given** an unrecognised value for the option (for example `--discover-bridge-interfaces=maybe`), **When** the analysis starts, **Then** it exits with a clear error naming the accepted values, before any device or emulator work begins.

---

### Edge Cases

- **Name not a literal**: The bridge name is built at run time (concatenation, a value read from resources, config or the network). The registration is still listed, with its class if known, and the name is marked "unresolved". Whatever is known about how the name is built is also given.
- **Class not resolvable**: The object passed to the registration call cannot be resolved to a single class (an interface type, a factory result, several possible classes). Every candidate class with exposed methods is listed, and the link is marked "ambiguous".
- **Exposed methods without a registration**: A class has exposed methods but no registration site was found. It is listed as a "bridge-capable class with no discovered registration".
- **Inheritance**: Exposed methods inherited from a superclass are listed under the subclass that is registered.
- **Old target API**: The app targets an Android API level older than 17. On those levels, every public method of a registered object is reachable from JavaScript, annotated or not. The report states that all public methods are exposed and lists them.
- **Obfuscation**: Class and method names are obfuscated. Names are reported as they appear in the APK. Bridge names given as literals are not obfuscated, so they are still recovered.
- **Multiple dex files and libraries**: The app is split across several dex files, or the registration sits in a bundled third-party library. All of them are analysed.
- **Unreadable APK**: The APK is malformed, encrypted or packed, or the static pass fails for some other reason. The failure is recorded and a warning is printed, and the dynamic run continues as usual. Static discovery never stops a run that would otherwise succeed.
- **Bridge removal**: The same name is registered more than once, or removed with `removeJavascriptInterface`. Each registration site is listed. Removal sites are listed with the name they remove.
- **No events captured**: The run captures no events. The existing rule skips the report in that case. Static results are still saved to their own artifact so the work is not lost.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The analysis command MUST accept a `--discover-bridge-interfaces` option that turns static bridge discovery on or off. It MUST be on when the option is absent.
- **FR-002**: The option MUST accept an explicit true value (bare flag, `=true`) and an explicit false value (`=false`, or the negated `--no-discover-bridge-interfaces`). Any other value MUST end the run with an error message that lists the accepted forms.
- **FR-003**: The existing positional usage (`<apk> [<apk-package>]`) MUST keep working unchanged. The option MUST be accepted before or after the positional arguments.
- **FR-004**: When enabled, static discovery MUST run on the input APK before the dynamic run starts. It MUST NOT need a device, emulator or instrumentation.
- **FR-005**: Static discovery MUST find every method in the APK's code that carries the JavaScript-interface annotation, recording its declaring class, method name and parameter types.
- **FR-006**: Static discovery MUST find every `addJavascriptInterface` call site. For each it MUST record the bridge object name, the class of the object passed (where it can be resolved), and the class and method that contain the call.
- **FR-007**: When the bridge name at a call site is a compile-time constant (directly, or through a local, field or constant propagated within the calling method), discovery MUST report the literal name. Otherwise it MUST mark the name "unresolved".
- **FR-008**: Discovery MUST link each registration to the exposed methods of the registered class, including inherited ones, so that each discovered bridge reads as "name → class → exposed methods".
- **FR-009**: Exposed methods MUST be flagged sensitive or not with the same naming rule Sentry already uses for runtime bridge methods, so static and runtime findings agree.
- **FR-010**: When the app's target API level is below 17, discovery MUST report that all public methods of each registered class are reachable, and list them.
- **FR-011**: Static discovery results MUST be written to a machine-readable artifact in the run workspace, next to the existing outputs. This MUST happen whether or not runtime events are captured.
- **FR-012**: When a report is generated, both report formats (machine-readable and human-readable) MUST include a static bridge inventory section. Each entry MUST be marked "static and runtime", "static only" or "runtime only" by matching on bridge name and class.
- **FR-013**: Statically discovered bridges that the run never observed MUST appear as findings in the report. They MUST be clearly told apart from runtime-confirmed exposure findings, so that existing risk scores are not inflated without runtime evidence.
- **FR-014**: The report MUST say whether static discovery was enabled and whether it completed, failed (with a short reason) or was disabled.
- **FR-015**: A failure in static discovery MUST NOT change the run's exit status or stop the dynamic run. A one-line warning MUST be printed.
- **FR-016**: With discovery disabled, the run's console output, workspace contents and reports MUST be identical to Sentry's behaviour before this feature.
- **FR-017**: The benchmark runner MUST inherit the default (discovery on) through the analysis command. Its per-APK result archive MUST include the static discovery artifact when one is produced.
- **FR-018**: The option MUST be documented in the command's usage text and in the README.
- **FR-019**: When static discovery completes, every exposed method it found MUST be instrumented when the dynamic run starts, before any `addJavascriptInterface` call. This covers methods of registered classes and of bridge-capable classes with no discovered registration. Calls to these methods MUST be logged as bridge calls even when the registration itself is never observed.
- **FR-020**: Pre-instrumentation MUST NOT hook framework classes (`java.*`, `javax.*`, `android.*`, `dalvik.*`, `kotlin.*`). The pre-API-17 exposure of `java.lang.Object` methods is reported, never hooked.
- **FR-021**: A method instrumented both statically and at registration time MUST be hooked once. When the registration is observed, the event stream MUST be identical to a run without pre-instrumentation.
- **FR-022**: Pre-instrumentation MUST work with both runners. With discovery disabled or failed, no method is pre-instrumented, and a missing or unreadable artifact MUST NOT stop the agent from being built.
- **FR-023**: In the report, a logged call to a statically discovered bridge MUST count as runtime evidence (`static+runtime`), even without a registration event.

### Key Entities

- **Exposed Method**: A native method reachable from JavaScript. Attributes: declaring class, method name, parameter types, return type, sensitivity flag, and whether it is exposed by annotation or by the pre-API-17 rule.
- **Bridge-capable Class**: A class that declares or inherits one or more exposed methods. Attributes: class name, list of exposed methods, and whether any registration refers to it.
- **Bridge Registration**: One `addJavascriptInterface` call site. Attributes: bridge name (literal or "unresolved"), registered class or candidate classes (with resolution status), and the containing class and method.
- **Static Discovery Result**: The output of one static pass over one APK. Attributes: APK identity, status (completed / failed / disabled), failure reason, target API level, list of registrations, list of bridge-capable classes.
- **Bridge Correlation**: The report-level join of static registrations and runtime bridge events. Attributes: bridge name, class, provenance (static and runtime / static only / runtime only).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every APK in the `Benchmark/` directory, static discovery reports 100% of the bridge names and exposed methods present in its source, checked against a hand-made ground-truth list.
- **SC-002**: For bridges registered with a literal name, the recovered name matches the name visible to JavaScript in 100% of benchmark cases.
- **SC-003**: Static discovery adds no more than 30 seconds to an analysis run for an APK of up to 50 MB.
- **SC-004**: With discovery disabled, reports produced from the existing test fixtures are byte-for-byte identical to the current expected outputs.
- **SC-005**: When static discovery is forced to fail (for example on a corrupted APK copy), the run still finishes its dynamic stage and exits with the same status it would have had without the feature.
- **SC-006**: An analyst can tell from the report alone, without opening the APK, which bridges the dynamic run did not reach.

## Assumptions

- "Functions annotated with addJavaScriptInterface" means methods carrying the `@JavascriptInterface` annotation, together with the `addJavascriptInterface(object, name)` calls that register them. That pair is what gives the bridge object name.
- The static pass works on the compiled APK alone (bytecode and manifest). It does not need source code, a device or network access. Code loaded at run time (downloaded dex, reflection-built names, native code) is out of scope. Such bridges show up only as "runtime only" through the existing dynamic hooks.
- Name resolution covers constants within the calling method and string constants held in fields. Following values across methods or through resources is best-effort, and anything not resolved is reported as "unresolved", not guessed.
- Static results also guide the runtime hooks: see FR-019 to FR-023 (added 2026-10-16 at the project owner's request).
- Static-only bridges are reported as findings at a lower confidence than runtime-confirmed ones. The exact severity mapping is settled during planning, within the rules of FR-013.
- The extra tooling the static pass needs is acceptable as a new dependency for both the local and the Docker runners. It is made available the same way the existing tools are (on `PATH`, or bundled in the Docker image).
- The negated form `--no-discover-bridge-interfaces` follows common command-line convention for turning off an option that is on by default.
