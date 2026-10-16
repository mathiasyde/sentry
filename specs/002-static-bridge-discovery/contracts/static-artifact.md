# Contract: `target/static-bridges.json`

The field definitions are in [data-model.md](../data-model.md). This file fixes the on-disk shape. Producer: `core.static`. Consumer: `core.report.cli --static-bridges`.

- Encoding: UTF-8 JSON, `indent=2`, `sort_keys=True`, trailing newline.
- `schema: 1`. Consumers must reject any other value with a warning: the report then omits the static section and prints `Warning: ignoring static bridge artifact: unsupported schema <n>`.
- A consumer must tolerate extra keys.

## Example (completed; matches `Benchmark/strongUpdate.apk`)

```json
{
  "all_public_methods_exposed": false,
  "apk": {"dex_files": ["classes.dex", "classes2.dex", "classes3.dex"], "path": "target/app.apk", "sha256": "…"},
  "bridge_classes": [
    {
      "class_name": "com.example.strongupdate.BridgeClass",
      "methods": [
        {"declared_in": "com.example.strongupdate.BridgeClass", "exposure": "annotation",
         "name": "showData", "params": [], "returns": "void", "sensitive": false}
      ],
      "registered": true,
      "superclass": "java.lang.Object"
    }
  ],
  "error": null,
  "min_sdk": 24,
  "package": "com.example.strongupdate",
  "registrations": [
    {
      "call_site": {"class": "com.example.strongupdate.MainActivity", "dex": "classes3.dex",
                    "method": "loadWeb", "offset": 0, "signature": "loadWeb()"},
      "candidate_classes": ["com.example.strongupdate.BridgeClass"],
      "class_name": "com.example.strongupdate.BridgeClass",
      "class_resolution": "exact",
      "methods": ["…same as bridge_classes[0].methods…"],
      "name": "Android",
      "name_source": {"kind": "const-string", "ref": null},
      "name_status": "resolved",
      "webview_receiver": "verified"
    }
  ],
  "removals": [],
  "schema": 1,
  "stats": {"classes": 0, "methods_scanned": 0, "seconds": 0.0},
  "status": "completed",
  "target_sdk": 34
}
```

The SDK numbers, offsets and stats above are illustrative. The ground-truth test asserts only names, classes, method names and resolution kinds.

## Example (failed)

```json
{"all_public_methods_exposed": false, "apk": {"dex_files": [], "path": "target/app.apk", "sha256": "…"},
 "bridge_classes": [], "error": "BadZipFile: File is not a zip file", "min_sdk": null, "package": null,
 "registrations": [], "removals": [], "schema": 1, "stats": {"classes": 0, "methods_scanned": 0, "seconds": 0.01},
 "status": "failed", "target_sdk": null}
```
