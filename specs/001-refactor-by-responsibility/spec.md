# Feature Specification: Refactor Sentry by Responsibility

**Feature Branch**: `001-refactor-by-responsibility`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "I want to refactor the project by responsibilities. The idea is that there are three types of activities here: browser-related instrumentation, native-related instrumentation, and core functionality."

## Context

Sentry analyzes hybrid Android apps: it runs an APK on an instrumented device, captures WebView and JavaScript-bridge events, and turns them into a security report. Its work falls into three kinds of activity, which today are interleaved:

1. **Browser-related instrumentation**: observation that runs *inside the web content* of a WebView. This covers the page-side observer installed in each page (its namespace and event buffer), wrappers around bridge calls in the page, taint tracking of values in page storage and network calls, and the probe that collects buffered page events.
2. **Native-related instrumentation**: observation that runs *in the app process* by intercepting Android platform APIs. This covers WebView creation and navigation, WebView settings, WebView/WebChrome client callbacks, JavaScript bridge registration and native bridge method calls, JavaScript evaluation, permission requests and responses, and environment access (`getenv`). It is also the part that delivers browser-side scripts into WebViews and periodically retrieves their buffered events.
3. **Core functionality**: everything that is not instrumentation. This covers the shared event vocabulary (the contract that both instrumentation layers emit and the reporting side consumes), how events are emitted and sanitized, orchestrating an analysis run (input handling, package discovery, workspace, runner selection), preparing the runner environments (container and local device), triggering reports, the report pipeline (event loading, URL/origin classification, state tracking, detection rules and risk scoring, JSON and Markdown rendering), and the benchmark runner.

Today, browser-side scripts are kept as text inside the same unit as the native hooks. The event vocabulary is defined inside the native hook unit. Orchestration, runners, and reporting are each packed into single large units, and some helper logic is copied between scripts. This refactor gives each of the three categories its own clearly bounded home, with clear sub-areas inside each one, **without changing what Sentry does or produces**.

## User Scenarios & Testing *(mandatory)*

The "users" of this change are (a) researchers who run Sentry on APKs and benchmarks, and (b) maintainers who extend Sentry with new browser-side observation, new native hooks, new detection rules, or new report formats.

### User Story 1 - Analysis results are unchanged after the refactor (Priority: P1)

A researcher runs Sentry on an APK exactly as before, with the same command, arguments and environment variables. They get the same outputs in the same locations, with the same content.

**Why this priority**: Sentry is a research instrument, so benchmark results and reports must stay comparable across versions. A refactor that changes results is a regression, however much cleaner the structure becomes.

**Independent Test**: Take a set of previously captured raw event logs, including benchmark runs. Generate reports from them with the pre-refactor and post-refactor versions, then compare the outputs. Separately, run one benchmark APK end-to-end in each supported runner mode and confirm the outputs match.

**Acceptance Scenarios**:

1. **Given** a raw event log captured before the refactor, **When** the report is regenerated after the refactor, **Then** the machine-readable report has identical content (risk score, findings, evidence, WebView inventory, sensitive data flows, origin-to-bridge map) and the human-readable report has identical text.
2. **Given** a benchmark APK and a working emulator, **When** the researcher runs the analysis entry point with the same arguments as before, **Then** the raw event stream, the human-readable report, and the machine-readable report are written to the same paths as before.
3. **Given** the analysis entry point is called without a package name and the package-inspection tool is available, **When** the analysis runs, **Then** the package name is discovered with the same result for every APK for which the old tool returned a single, correct package name.
4. **Given** an analysis run captures no events, **When** the run ends, **Then** report generation is skipped with the same message as before.

---

### User Story 2 - Maintainer changes browser-side observation without touching native hooks (Priority: P2)

A maintainer wants to observe a new in-page behavior, for example a new storage or network API used by page scripts. They make the change only in the browser-instrumentation area. The native layer keeps delivering the browser-side observer and collecting its events without modification.

**Why this priority**: Browser-side observation is currently embedded as text inside the native hook unit, so it is hard to read, review, or change on its own.

**Independent Test**: Look at the browser-instrumentation area and confirm that it holds all in-page observation logic (observer installation, bridge-call wrapping, taint tracking, probe collection) as standalone, readable content. Run a benchmark end-to-end and confirm the in-page events (probe results, taint flows) match a pre-refactor run.

**Acceptance Scenarios**:

1. **Given** the refactored structure, **When** a maintainer looks for the code that runs inside web pages, **Then** they find all of it in the browser-instrumentation area and none of it in the native-instrumentation area.
2. **Given** a change confined to the browser-instrumentation area, **When** an analysis runs, **Then** the native layer delivers the updated browser-side observer without any change to native code.

---

### User Story 3 - Maintainer changes one native hook family in one place (Priority: P2)

A maintainer wants to change how one family of Android APIs is intercepted, for example permission requests or JavaScript bridge registration. They find a dedicated home for that family inside the native-instrumentation area and change only that home. Shared event emission and sanitization come from core.

**Why this priority**: The native hook unit is the largest and hardest to navigate. Separating it by intercepted API family makes hook changes safer.

**Independent Test**: Confirm that each intercepted API family has one identifiable home in the native-instrumentation area. The families are WebView lifecycle and navigation, settings, client callbacks, JavaScript bridge, JavaScript evaluation and probe delivery, permissions, and environment access. Run an end-to-end benchmark and confirm the emitted event stream matches a pre-refactor stream for the same app.

**Acceptance Scenarios**:

1. **Given** the refactored native instrumentation, **When** a maintainer looks for the code that intercepts permission requests, **Then** they find it in one dedicated place, separate from bridge, navigation, and settings hooks.
2. **Given** an instrumented run of a benchmark app, **When** its event stream is compared with a pre-refactor run of the same app, **Then** the same event types are emitted with the same fields. Timestamps, random namespaces and runtime-generated identifiers may differ.

---

### User Story 4 - Maintainer extends core functionality without touching instrumentation (Priority: P3)

A maintainer adds a new detection rule, changes report formatting, or changes how the local or container runner prepares the device. All of these changes stay inside the core area, in the matching sub-area, and neither instrumentation layer changes.

**Why this priority**: Detection rules and runner changes are frequent. Keeping them apart from instrumentation stops reporting or orchestration changes from breaking event capture.

**Independent Test**: Add a sample detection rule confined to the detection sub-area of core. Regenerate a report from a recorded event log and confirm that the finding appears in both report formats and that no instrumentation file changed.

**Acceptance Scenarios**:

1. **Given** the refactored structure, **When** a maintainer adds a new finding rule, **Then** the change is confined to core's detection sub-area (plus its tests).
2. **Given** a new finding produced by that rule, **When** reports are generated, **Then** the finding appears in both the machine-readable and the human-readable report without changes to the rendering sub-area.
3. **Given** the analysis entry point, **When** a maintainer reads it, **Then** the orchestration flow (validate input → prepare workspace → run selected runner → generate report) is expressed separately from each runner's device-preparation steps.
4. **Given** the benchmark runner and the analysis entry point, **When** either one needs to locate the package-inspection tool, **Then** both use one shared implementation.

---

### Edge Cases

- **Malformed lines in raw event logs:** the count of skipped lines and the resulting report must stay the same.
- **Unknown event types in raw event logs:** they must keep being handled exactly as before.
- **Interrupted runs (user interrupt or termination signal):** the report must still be generated on exit, with the same exit codes as before.
- **Missing prerequisites (no container support, no visible device, missing instrumentation server, missing package-inspection tool):** the same error messages and exit behavior must be kept.
- **A page that loads before the browser-side observer is delivered, or that replaces it:** the delivery and re-delivery behavior (on page start, page finish and navigation) must stay the same.
- **A failed probe:** probe failures must keep producing the same probe-error events.
- **The browser-side observer's per-run random namespace:** this must be kept so that page scripts cannot predict it.
- **Loading the instrumentation:** the container runner loads it from inside its image, and the local runner loads it from the host. If the instrumentation is split into several parts, both runners must load the complete set in the same order and produce the same behavior.
- **Documented commands and environment variables (runner mode, device serial, instrumentation device id, instrumentation server path, boot timeout, benchmark settings):** these must keep their names, defaults, and meaning.

## Requirements *(mandatory)*

### Functional Requirements

**Behavior preservation**

- **FR-001**: The analysis entry point MUST keep its current name, location, arguments, environment variables, defaults, error messages, and exit codes. *Exception:* finding the package-inspection tool and reading the package name are merged into one shared helper (FR-014). This may only turn lookups that used to fail, or that returned a garbled name, into correct ones.
- **FR-002**: All output artifacts (raw event stream, human-readable report, machine-readable report, and their copies) MUST be written to the same paths, with the same content structure as before the refactor.
- **FR-003**: For any given raw event log, the generated reports MUST have identical content before and after the refactor.
- **FR-004**: Together, the two instrumentation layers MUST emit the same set of event types, with the same fields and meaning, as before the refactor.
- **FR-005**: The report generator MUST still be runnable on its own with its current command-line options.
- **FR-006**: The benchmark runner MUST keep its current interface, environment variables, and result layout.

**Three-category structure**

- **FR-007**: The project MUST be organized into three top-level responsibility areas: **browser instrumentation**, **native instrumentation**, and **core**. Every piece of analysis-toolchain logic MUST belong to exactly one of them. Each area MUST be a directory with exactly these names: `browser/`, `native/`, and `core/`. The three directories MUST be siblings under the toolchain directory (`sentry/`). The analysis entry point (`analyse.sh`) stays at the repository root as required by FR-001, as a thin launcher that hands off to `core/`.
- **FR-008**: The **browser instrumentation** area MUST contain all logic that runs inside WebView web content, and only that logic. It MUST be kept as standalone content in its own right, not as text embedded inside native hook code. Its sub-areas are:
  - installing the in-page observer, its namespace and its event buffer
  - wrapping bridge calls in the page
  - taint tracking of page storage and network calls
  - collecting buffered events for the probe
- **FR-009**: The **native instrumentation** area MUST contain all logic that intercepts Android platform APIs in the app process, and only that logic. Each intercepted API family MUST have its own sub-area:
  - WebView lifecycle and navigation
  - WebView settings
  - WebView/WebChrome client callbacks
  - JavaScript bridge registration and native bridge method calls
  - JavaScript evaluation, plus delivery of browser-side scripts and probe polling
  - permission requests and responses
  - environment access
- **FR-010**: The **core** area MUST contain everything else, with these sub-areas:
  - the shared event vocabulary
  - emitting events and sanitizing values
  - orchestration of an analysis run (input validation, package-name discovery, workspace preparation, runner selection, report triggering)
  - runner environments, with container and local as separate sub-areas
  - the report pipeline (event loading; URL/origin classification; state tracking; detection rules and risk scoring; machine-readable report assembly; human-readable rendering; command-line handling)
  - the benchmark runner
  - shared tooling helpers
- **FR-011**: The event vocabulary MUST be defined once in core. Every component that emits or consumes vocabulary events MUST use that single definition: native instrumentation, the core agent runtime and the report pipeline. Browser instrumentation emits its own page events, which native code wraps into vocabulary events, so browser code MUST NOT reference the vocabulary directly.
- **FR-012**: Allowed dependencies MUST be one-directional:
  - Browser instrumentation MUST NOT depend on native instrumentation.
  - Native instrumentation MAY deliver browser instrumentation and MAY use core's event vocabulary and emission.
  - The core report pipeline MUST NOT depend on either instrumentation layer except through the event vocabulary.
- **FR-013**: Within core, rendering MUST NOT perform detection, and detection MUST NOT read files or write output.
- **FR-014**: Logic that is currently copied across scripts, including locating the package-inspection tool, MUST exist in exactly one shared place in core, used by every caller.
- **FR-015**: Each area and sub-area MUST start with a short statement of its responsibility, so maintainers can tell which of the three categories a change belongs to.

**Verification**

- **FR-016**: The project MUST include an automated regression check. It regenerates reports from a stored set of reference event logs and fails if the output differs from the stored reference reports.
- **FR-017**: The reference set MUST cover every benchmark case shipped in the repository, plus at least one empty or malformed log.
- **FR-018**: The project documentation MUST be updated to describe the three-category layout and to say where each kind of change belongs. The user-facing usage instructions MUST stay valid with no changes to the commands.

### Key Entities

- **Raw event**: one observation emitted by either instrumentation layer during a run, with a type, timestamp, associated WebView and payload. It is the contract between instrumentation and core reporting.
- **Event vocabulary**: the authoritative list of event types and their fields, owned by core.
- **Browser-side observer**: the in-page logic delivered into each WebView, which buffers page-level observations until the probe collects them.
- **Native hook family**: a group of intercepted Android platform APIs that emit related events.
- **WebView record**: the accumulated state of one observed WebView: URLs visited, settings, registered bridges and origins.
- **Finding**: a detected security issue with a severity, a description and the events that support it.
- **Report**: the overall result of a run, made of the risk score, findings, WebView inventory, sensitive data flows and origin-to-bridge map. It is produced in both a machine-readable and a human-readable form.
- **Reference log / reference report pair**: a stored raw event log together with its expected reports, used to prove that behavior is preserved.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of reference event logs (all shipped benchmark cases plus edge cases) produce reports identical to their pre-refactor references.
- **SC-002**: End-to-end runs of at least one benchmark APK produce the same findings and the same risk score as before the refactor. This applies in local mode, and also in container mode where a KVM host is available.
- **SC-003**: Every usage command documented in the README works unchanged after the refactor.
- **SC-004**: 100% of analysis-toolchain logic is assigned to exactly one of the three categories (browser instrumentation, native instrumentation, core), with no logic split across or duplicated between them.
- **SC-005**: A maintainer who doesn't know the codebase can use the documentation to name the right category and sub-area for each of these tasks in under 2 minutes per task:
  - add in-page taint tracking for a new API
  - change permission interception
  - add a detection rule
  - change local device setup
- **SC-006**: Each of these sample changes requires edits in exactly one sub-area, excluding tests:
  - a new browser-side observation
  - a change to a native hook family
  - a new detection rule
- **SC-007**: No sub-area exceeds roughly one-third of the size of the original unit it was carved from, so each sub-area can be read in one sitting. This applies to the WebView hooks, the report generator, the analysis entry point and the benchmark runner. After the orchestration moved to Python (research R11), its modules are limited to 100 lines (`run/`, `runners/`) and 160 lines (`benchmark/suite.py`, `host.py`).

## Assumptions

- The categories are defined by where the logic runs:
  - "Browser-related" means logic that runs inside the web content of a WebView.
  - "Native-related" means logic that intercepts Android platform APIs in the app process. This includes the WebView/WebSettings/client/bridge/permission APIs, not only low-level system calls.
  - "Core" means everything that runs on the analyst's side, plus the shared event contract.
- The scope is the analysis toolchain: the analysis entry point, the container and runner setup, the instrumentation, the report generator and the benchmark runner. The demo Android app (`android/`) and the demo web content (`web/`) are out of scope, except for any wiring needed to keep them working.
- This is a pure structural refactor. It adds no new detection rules, report fields, observed APIs or runner modes, and it does not change scoring.
- The benchmark APKs and binary assets under `Benchmark/` are not modified.
- Reference event logs can be captured from current-version runs, or taken from existing logs, before the restructuring starts, so that there are "before" outputs to compare against.
- Timestamps, random namespaces and runtime-generated identifiers in live event streams vary between runs, so they are left out when comparing live runs. The stored reference logs are deterministic.
- The existing toolchain languages and runtime dependencies are kept, and users running analyses need no new runtime dependencies.
- Verifying container mode needs a Linux host with KVM. When none is available, local-mode runs and the reference-log regression checks are enough evidence.
