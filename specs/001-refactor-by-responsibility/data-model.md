# Data Model: Refactor Sentry by Responsibility

This is a structural refactor, so the data model has two parts:

- the **runtime data** that flows between the areas, which must stay unchanged;
- the **structural entities** that the refactor adds: areas, modules and the bundle manifest.

## Runtime data (unchanged contracts)

### Raw event
One JSON object per line on the agent's stdout. `report.loader.load_events` takes everything from the first `{` on each line onward.

| Field | Type | Notes |
|---|---|---|
| `type` | string | Must be a value from the [event vocabulary](./contracts/event-vocabulary.md). If it is missing, the line counts as skipped. |
| `timestamp` | ISO-8601 string | Set by `core/agent/emitter.js` `log()`. For `js.probe` events, the page-side timestamp is used. |
| `data` | object | The payload for that type. It goes through `sanitize()` before it is printed. |

**Validation rules (report side)**: blank lines are ignored. A line counts in `skipped_line_count` when it has no `{`, is invalid JSON, is not an object, or has no `type`. Event types the report does not know are accepted, but no observer handles them.

**Emission ordering**: the agent queues events and flushes once per poll tick (1000 ms). Each flush is sorted by `timestamp`. This ordering is kept exactly.

### Page event (browser-internal)
These are buffered in `window[<namespace>].events`, which keeps at most 500 entries. The probe drains them.

| Field | Type |
|---|---|
| `timestamp` | ISO string |
| `name` | string, the intercepted API (for example `fetch` or `localStorage.setItem`) |
| `arguments` | array, copied to depth 2 with at most 20 items |
| `taints` / `bridge` | optional taint metadata |

The native side wraps each page event into a `js.probe` raw event (see [browser-scripts.md](./contracts/browser-scripts.md)).

### Taint
A record `{ id: "taint-<ms>-<n>", source, valuePreview }`. The browser keeps at most 200 of them, keyed by a 512-character fingerprint.

### WebView record (report side, `tracker.py`)
This is keyed by `str(webViewId or "unknown")`. Fields:
- `urls`, `origins`, `settings`, `bridges`;
- `bridge_exposures`, `bridge_methods`, `bridge_calls`;
- `taint_sources`, `taint_flows`;
- `permissions`, `js_events`.

The report rendering uses these fields exactly as today.

### Finding (`findings.py`)
A record `{ rule_id, severity, title, description, recommendation, evidence[] }`.

- **Deduplication**: the key is `fingerprint`, or `rule_id:json(evidence, sort_keys)` when no fingerprint is given.
- **Evidence**: at most 20 items per finding, kept in insertion order and passed through `compact()`.
- **Sort order**: severity first (descending), then `rule_id`, then `title`. Ties keep their insertion order.
- **Risk score**: `min(100, Σ SEVERITY_SCORE[severity])`, where critical = 40, high = 20, medium = 10, low = 3 and info = 0.
- **Rule ids**: these are the 22 rule ids emitted across `rules/*`. Most are written inline in the detectors; `rules/catalog.py` holds only the settings table and the shared constants.
  - `WV-BRIDGE-CALLED-BY-REMOTE-CONTENT`, `WV-CLEARTEXT-URL`, `WV-CONTENT-ACCESS`, `WV-FILE-ACCESS`
  - `WV-FILE-FROM-FILE`, `WV-FILE-URL-LOADED`, `WV-GEOLOCATION-ENABLED`, `WV-INLINE-CONTENT`
  - `WV-JS-BRIDGE-EXPOSED`, `WV-JS-CLEARTEXT-NETWORK`, `WV-JS-ENABLED`, `WV-JS-EVAL`
  - `WV-JS-EVALUATED`, `WV-JS-POPUPS`, `WV-MIXED-CONTENT`, `WV-PROBE-ERROR`
  - `WV-SAFE-BROWSING-DISABLED`, `WV-SENSITIVE-BRIDGE-METHOD`, `WV-TAINTED-BRIDGE-DATA-TO-JS-SINK`
  - `WV-UNIVERSAL-FILE-ACCESS`, `WV-WEB-PERMISSION-GRANTED`, `WV-WEB-PERMISSION-REQUEST`

  The golden coverage guard requires every one of them to appear in at least one expected report.

### Report
`{ summary, findings, webviews, origin_bridge_map }`. The full shape is in [contracts/cli-report.md](./contracts/cli-report.md).

## Structural entities (new)

### Area
| Area | Runs where | May depend on | Must not depend on |
|---|---|---|---|
| `browser` | Inside WebView page JS | nothing | `native`, `core`, `Java.*`, the event vocabulary |
| `native` | Frida agent in the app process | `browser` (as embedded sources), `core/agent` runtime, `EVENT_TYPE` | page-side code inline (`window.*`, `document.*`) |
| `core` | Host, container and the agent runtime | `core` only. Only `core/agent` embeds the other areas, as bundle inputs. | `core/report` must not depend on `browser` or `native` |

### Sub-area (module)
A file or package inside an area. Each one must:
- start with a responsibility header comment (FR-015);
- stay within its line budget (SC-007): browser and native files ≤ 430 lines, `core/report` modules ≤ 340, shell scripts ≤ 72.

### Native hook family
Each family is a module that exports `install<Family>Hooks(ctx)`. Lifecycle has two installers, `installWebViewConstructionHooks` and `installWebViewLoadHooks`, so the legacy order is kept. The clients module also exports the `createClientHookers(ctx)` factory. `ctx` is one flat object: the Java class handles, `log`, and the members returned by `createRegistry()`, `createDelivery(ctx)` and `createClientHookers(ctx)`. Each module destructures what it needs.

| Family | Module | Events emitted |
|---|---|---|
| WebView lifecycle & navigation | `webview_lifecycle.js` | `webview.created`, `webview.added`, `url.loaded` |
| Settings | `webview_settings.js` | `webview.settings.changed` |
| Client callbacks | `webview_clients.js` | `webview.client.set`, `webview.chrome_client.set`, `webview.page.loaded`, `url.loaded` |
| JavaScript bridge | `javascript_bridge.js` | `bridge.added`, `bridge.method.added`, `bridge.method.called`, `js.probe.error` |
| JS evaluation & delivery | `javascript_evaluation.js`, `browser_delivery.js` | `js.evaluated`, `js.probe`, `js.probe.error` |
| Permissions | `permissions.js` | `permission.requested`, `permission.grant.called`, `permission.deny.called` |
| Environment | `environment.js` | none (it only rewrites `System.getenv("URL")`) |

Chrome-client permission callbacks are installed when `setWebChromeClient` is seen. `webview_clients.js` calls `hookChromeClientPermissions(ctx, ChromeClientClass, className)` from `permissions.js`, so the permission logic stays in one place.

### Bundle manifest
`core/agent/manifest.json` is an ordered list of entries. Each entry is one of:
- `{"kind": "vocabulary"}`
- `{"kind": "browser", "name": "observer", "files": ["browser/observer/00_namespace.js", ...]}` (or a single `file`)
- `{"kind": "source", "file": "core/agent/sanitize.js"}`

Rules:
- `native/main.js` is the last WebView source. Only `native/environment.js` comes after it, because it registers its own `Java.perform` second, as the legacy two-script load did.
- Each browser entry `name` becomes a key in `BROWSER_SOURCES`.
- Duplicate top-level declarations across sources make the build fail.

State transitions: none. Every entity is either static structure or the per-run data described above.
