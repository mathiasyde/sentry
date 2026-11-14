# Data Model: Static JavaScript Bridge Discovery

All entities are plain dicts that can be serialised to JSON. The on-disk form is specified in [contracts/static-artifact.md](contracts/static-artifact.md). Class and type names are **dotted Java names** (`com.example.Foo`, `java.lang.String`, `int[]`), so they compare directly with the runtime `className` from `native/javascript_bridge.js`.

## StaticDiscoveryResult (artifact root)

| Field | Type | Rules |
|---|---|---|
| `schema` | int | `1` |
| `status` | `"completed"` \| `"failed"` | `"disabled"` is never written. When the option is off, no artifact exists (FR-016). |
| `error` | string \| null | Set only when `status == "failed"`. One line, ≤ 200 characters. |
| `apk` | object | `{ "path": str, "sha256": str \| null, "dex_files": [str] }`. `sha256` is null only when a failed run could not read the file. `dex_files` is in load order (`classes.dex`, `classes2.dex`, …). |
| `package` | string \| null | From the manifest. |
| `min_sdk`, `target_sdk` | int \| null | From the manifest. `target_sdk` falls back to `min_sdk`; null when unknown (R4). |
| `all_public_methods_exposed` | bool | `target_sdk is not null and target_sdk < 17` |
| `registrations` | [BridgeRegistration] | Sorted by (`name` or `""`, `class_name` or `""`, call site). |
| `removals` | [BridgeRemoval] | |
| `bridge_classes` | [BridgeCapableClass] | Every class with ≥ 1 exposed method, registered or not. Sorted by name. |
| `stats` | object | `{ "classes": int, "methods_scanned": int, "seconds": float }`. Diagnostic only; the report never renders it, so goldens stay stable. |

On failure, `registrations`, `removals` and `bridge_classes` are empty lists. The other fields are filled in as far as the scan got.

## BridgeRegistration

One per (call site × distinct resolved name). If a call site's name is unresolved, it gets exactly one entry.

| Field | Type | Rules |
|---|---|---|
| `name` | string \| null | Null exactly when `name_status == "unresolved"` |
| `name_status` | `"resolved"` \| `"unresolved"` | |
| `name_source` | NameSource | How the name argument was produced |
| `class_name` | string \| null | The single resolved class. Null when the class is ambiguous or unknown. |
| `class_resolution` | `"exact"` \| `"declared-type"` \| `"ambiguous"` \| `"unknown"` | R5 |
| `candidate_classes` | [string] | `[class_name]` when it resolved to one class. Otherwise every bridge-capable class assignable to the declared type. |
| `methods` | [ExposedMethod] | Exposed methods of `class_name`. Empty unless the class resolution is `exact` or `declared-type`. |
| `call_site` | CallSite | |
| `webview_receiver` | `"verified"` \| `"unverified"` | R2 |

**NameSource**: `{ "kind": "const-string" | "static-field" | "parameter" | "field" | "method-result" | "unknown", "ref": string | null }`. `ref` is a readable member reference such as `com.x.Cfg.bridgeName()`, `com.x.Cfg.NAME` or `param#1`.

**CallSite**: `{ "class": string, "method": string, "signature": string, "dex": string, "offset": int }`, for example `{"class": "com.example.strongupdate.MainActivity", "method": "loadWeb", "signature": "loadWeb()", "dex": "classes3.dex", "offset": 42}`. `offset` is the code-unit offset of the `invoke` instruction.

## BridgeRemoval

`{ "name": string | null, "name_status": …, "name_source": NameSource, "call_site": CallSite }`

## BridgeCapableClass

| Field | Type | Rules |
|---|---|---|
| `class_name` | string | |
| `superclass` | string \| null | |
| `methods` | [ExposedMethod] | Effective exposed set (R3; R4 when pre-17) |
| `registered` | bool | True if any registration lists it as `class_name` or among its `candidate_classes` |

## ExposedMethod

| Field | Type | Rules |
|---|---|---|
| `name` | string | |
| `params` | [string] | Dotted parameter types, matching the runtime `args` list |
| `returns` | string | |
| `declared_in` | string | The class that declares it; differs from the registered class when the method is inherited |
| `exposure` | `"annotation"` \| `"public-pre-17"` | |
| `sensitive` | bool | `SENSITIVE_METHOD_RE.search(name)` (FR-009) |

## BridgeCorrelation (report only; built by `report/correlate.py`)

| Field | Type | Rules |
|---|---|---|
| `interfaceName` | string \| null | |
| `className` | string \| null | |
| `provenance` | `"static+runtime"` \| `"static-only"` \| `"runtime-only"` | |
| `static` | object \| null | The registration, minus `call_site.offset` and `dex`, to keep output readable |
| `registered_in` | [string] | `<class>.<signature>` of every static call site collapsed into this entry (empty for runtime-only) |
| `runtime_webviews` | [string] | WebView ids where the bridge was seen at run time |
| `runtime_methods` | [string] | Method names reported by the runtime `bridge.method.added` events for this bridge |
| `sensitive_methods` | [string] | Union of static sensitive method names and runtime method names matching the pattern |

**Matching rule (R8)**:
- A static registration S matches a runtime bridge R (an `interfaceName`, `className` pair from any WebView in the tracker) when the names are equal (or S's name is unresolved) **and** the classes are equal (or S has no `class_name` and R's class is in `candidate_classes`).
- One S can match several R entries in different WebViews; they are collapsed into one correlation entry.
- A runtime bridge that matches no S becomes `runtime-only`.
- Output is sorted by (`provenance` order: static+runtime, static-only, runtime-only), then `interfaceName`, then `className`.

## State transitions

Discovery status per run:

```
option off ─────────────────────────────▶ (no artifact; report has no static section)
option on ──▶ scanning ──ok──▶ completed ─▶ artifact written ─▶ report section (if events)
                     └──exception──▶ failed ─▶ artifact {status: failed, error} + console warning
```

Ctrl-C or SIGTERM during the scan is not caught (exit 130 or 143, as today). The artifact is then absent, and the report step runs as usual.
