# Contract: static bridges in the report

## Report CLI

```
python3 -m core.report <log> [--json P] [--markdown P] [--trusted-origin O ...] [--static-bridges PATH]
```

- `--static-bridges` is optional. When it is absent, the JSON and Markdown output and stdout are **byte-identical** to today's (SC-004).
- If PATH is unreadable, is not JSON, or has an unsupported `schema`, print `Warning: ignoring static bridge artifact: <reason>` to stdout and continue as if the option were absent.
- The stdout summary line is unchanged.

## JSON: new top-level key `static_bridges` (present only with the option)

```json
"static_bridges": {
  "status": "completed",
  "error": null,
  "target_sdk": 34,
  "all_public_methods_exposed": false,
  "counts": {"registrations": 1, "unresolved_names": 0, "bridge_classes": 1,
             "static_and_runtime": 1, "static_only": 0, "runtime_only": 0},
  "bridges": [ /* BridgeCorrelation entries, data-model.md */ ],
  "unregistered_classes": [ /* BridgeCapableClass with registered == false */ ],
  "removals": [ /* BridgeRemoval */ ]
}
```

When the artifact's `status == "failed"`, `bridges` holds only `runtime-only` entries, `unregistered_classes` and `removals` are empty, and `error` is copied over.

`summary` is **not** changed. Static-only findings are `info` (0 points), so `risk_score` and `finding_count` move only through the new findings, and `severity_counts.info` goes up by one per static-only bridge.

## Finding: `WV-STATIC-BRIDGE-UNOBSERVED`

- Severity: `info`.
- One finding per static-only correlation entry. Fingerprint: `WV-STATIC-BRIDGE-UNOBSERVED:<interfaceName or "?">:<className or "?">`.
- Title: `JavaScript bridge found in the APK but not observed at runtime`
- Description: `Static analysis found an addJavascriptInterface registration that the dynamic run never executed. The bridge is still part of the app's attack surface.`
- Recommendation: `Exercise the code path that registers this bridge (see call site) and review its exposed methods, especially those flagged sensitive.`
- Evidence: `{"interfaceName", "className", "nameStatus", "classResolution", "candidateClasses", "callSite": "<class>.<signature>", "methods": [names], "sensitiveMethods": [names]}`

There is no finding for `static+runtime` entries, because the existing runtime rules already cover them. There is also no finding for `runtime-only` entries or for unregistered classes; they appear only in the inventory.

## Markdown: new section, placed after "Origin-to-Bridge Map" (present only with the option)

```
## Static Bridge Inventory

- Discovery status: completed            (or: failed — <error>)
- Target SDK: 34                          (or: unknown)
- Registrations: 1 (0 with unresolved names); bridge classes: 1
- Coverage: 1 static and runtime, 0 static only, 0 runtime only

> Target SDK is below 17: every public method of a registered object, including java.lang.Object methods such as getClass(), is reachable from JavaScript.   (only when applicable)

### `Android` → com.example.strongupdate.BridgeClass  [static+runtime]

- Registered in: com.example.strongupdate.MainActivity.loadWeb()
- Class resolution: exact
- Exposed methods: showData()
- Sensitive methods: none

### Bridge-capable classes with no discovered registration
- com.example.Foo: bar(java.lang.String), getToken() [sensitive]

### Bridge removals
- `Android` in com.example.X.onDestroy()
```

- Unresolved names render as `` `<unresolved: method-result com.x.Cfg.bridgeName()>` ``.
- Ambiguous classes render as `one of: A, B`.
- Subsections with nothing in them are left out.
