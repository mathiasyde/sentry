# Contract: the report generator CLI and its outputs

## Invocation (unchanged, FR-005)

```text
python3 sentry/report.py LOG_FILE [--json PATH] [--markdown PATH] [--trusted-origin ORIGIN]...
```

| Option | Default | Meaning |
|---|---|---|
| `LOG_FILE` | (required) | Raw event log |
| `--json` | `target/report.json` | Machine-readable report path. Parent directories are created. |
| `--markdown` | `logs/report.md` | Human-readable report path. Parent directories are created. |
| `--trusted-origin` | `[]` | Can be repeated. Each value is normalized with `normalize_trusted_origin`. |

- **stdout on success**: `Generated report: <json> and <md> (<n> findings, risk score <s>/100)`
- **Exit code**: 0

After the refactor, `sentry/report.py` is a launcher with no logic. It puts `sentry/` on `sys.path` and calls `core.report.cli.main()`. `python3 -m core.report` run from `sentry/` is an additional, optional entry point.

## JSON output

- It is written with `json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"`.
- It must be **byte-identical** to the legacy output for the same input.

```text
summary:
  risk_score            int 0..100
  event_count           int
  skipped_line_count    int
  finding_count         int
  severity_counts       {critical, high, medium, low, info: int}
  webview_count         int
  trusted_origins       sorted [str]
findings: [ {rule_id, severity, title, description, recommendation, evidence: [≤20]} ]   # sorted (see data-model)
webviews:
  <webViewId>:
    urls, origins, settings, bridges,
    bridge_exposure_count, bridge_method_count, bridge_call_count,
    taint_source_count, taint_flow_count, taint_flows,
    permission_event_count, js_event_count
origin_bridge_map:
  <webViewId>:
    <origin>: {trusted, remote, page_urls: [...], bridges: {<iface>: {interfaceName, className, attachedPageUrl, attachedOrigin, methods, calls}}}
```

## Markdown output

It is produced by `core/report/markdown.py` and must be byte-identical to the legacy `markdown_report()` output.

## Module responsibilities and allowed I/O

| Module | May do file I/O | May create findings |
|---|---|---|
| `cli.py` | yes (read the log through `loader`, write outputs) | no |
| `loader.py` | read only | no |
| `tracker.py`, `assemble.py`, `markdown.py`, `values.py`, `urls.py` | no | no |
| `rules/*`, `findings.py` | no | yes (`rules` through `FindingStore.add`) |
| `analyzer.py` | no | no (it only dispatches) |

## Extension point

To add a detection rule:

1. Add a detector function to the matching `rules/<family>.py`, or add a new module.
2. Register it for its event type(s) in `rules/__init__.py`.
3. If it needs constants, put them in `rules/catalog.py`.

No other module changes (SC-006).
