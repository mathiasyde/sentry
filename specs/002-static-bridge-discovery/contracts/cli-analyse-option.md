# Contract: `analyse.sh` bridge-discovery option

This extends [001 cli-analyse.md](../../001-refactor-by-responsibility/contracts/cli-analyse.md). Everything there still holds, apart from the deviations listed at the end.

## Synopsis

```
./analyse.sh [--discover-bridge-interfaces[=<bool>] | --no-discover-bridge-interfaces] <APK-FILE> [<APK-PACKAGE>]
```

- The option may appear anywhere among the arguments. Every other argument keeps its position-based meaning, in order.
- `<bool>`: `true|yes|on|1` or `false|no|off|0`, case-insensitive.
- The bare `--discover-bridge-interfaces` means true. The default, with no option, is **true**.
- Repeated options: the last one wins.
- `--discover-bridge-interfaces false` (separated by a space) is **not** a valid way to give a value: `false` would be read as the APK path.
- Unknown `--…` arguments are not intercepted. They stay positionals, exactly as today.

## Step order (changes in **bold**)

1. Print `Sentry - version alpha` and an empty line.
2. **Parse the option. On an invalid value, print `Error: invalid value '<v>' for --discover-bridge-interfaces (expected true or false)` and exit 1.** No workspace or device work has happened at this point.
3. Usage check, as before. **The usage message is now two lines:**
   ```
   Usage: analyse.sh <apk> [<apk-package>]
   Options: --[no-]discover-bridge-interfaces[=true|false]  static JavaScript bridge discovery (default: true)
   ```
4. to 8. Unchanged: file check, package resolution, runner selection, preflight, and workspace preparation. **`prepare()` also deletes `target/static-bridges.json`.**
9. Report-on-exit is armed (unchanged).
10. **If discovery is enabled:** scan `target/app.apk` and write `target/static-bridges.json`. Then print exactly one of:
    - `Static bridge discovery: <R> registration(s), <U> with unresolved names, <C> bridge class(es) -> target/static-bridges.json`
    - `Warning: static bridge discovery failed: <reason>` (the artifact is still written, with `status: "failed"`)
11. Run the selected runner (unchanged).
12. Report generation (unchanged), **with `--static-bridges target/static-bridges.json` added when that file exists.** When no events were captured, the report is skipped as before and the artifact stays in place.

## Exit status

- Discovery never changes the exit status (FR-015).
- Invalid option value → 1.

## Benchmark runner

`scripts/run-benchmarks-linux.sh` passes no option, so discovery runs. The per-APK archive gains `static-bridges.json` when the file exists. The rest of the archive layout is unchanged.

## Intentional deviations from 001

| Behaviour | Before | After |
|---|---|---|
| No-args usage output | one `Usage:` line | the same `Usage:` line plus one `Options:` line |
| `--discover-bridge-interfaces=<bad>` | `File not found: --discover-bridge-interfaces=<bad>` | the invalid-value error above |
| Console during a run | — | one static discovery line (when enabled) |

`tests/test_cli_contract.py::test_matches_legacy_output` is updated to compare `no_args` stdout against the legacy output **plus** the `Options:` line. The other legacy scenarios still match byte for byte.
