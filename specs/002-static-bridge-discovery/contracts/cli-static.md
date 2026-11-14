# Contract: `python3 -m core.static` (standalone scanner)

Used by tests, by the quickstart, and for ad-hoc analysis without a device. Run it with `PYTHONPATH=sentry`.

```
python3 -m core.static <APK-FILE> [--out PATH]
```

- Without `--out`: write the artifact JSON to stdout (2-space indent, sorted keys, trailing newline).
- With `--out PATH`: write to PATH (creating parent directories) and print the one-line summary from [cli-analyse-option.md](cli-analyse-option.md) step 10, with PATH in place of `target/static-bridges.json`.
- Exit codes:
  - `0` when `status == "completed"`;
  - `2` when `status == "failed"` (the artifact is still written);
  - `1` for usage errors, such as a missing argument or a file that doesn't exist (`Error: file not found: <path>`).

The Python API `core.static.discover_bridges(apk_path: str | Path) -> dict` returns the same payload. It raises on failure; the **caller** (`run/discovery.py`, `__main__`) turns that into `status: "failed"`.
