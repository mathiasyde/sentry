"""core/run: run static bridge discovery before the dynamic run; never fails the run."""

from __future__ import annotations

import json
import time

from core.host import Host
from core.run.workspace import Workspace
from core.static import discover_bridges, failed_result, summary_line

ARTIFACT_LABEL = "target/static-bridges.json"


def run_discovery(host: Host, workspace: Workspace) -> None:
    """Scan target/app.apk and write the artifact. Errors become a 'failed' artifact and a warning.

    KeyboardInterrupt and SystemExit are not caught, so Ctrl-C and SIGTERM keep their exit codes.
    """
    started = time.monotonic()
    try:
        result = discover_bridges(workspace.apk)
        message = summary_line(result, ARTIFACT_LABEL)
    except Exception as exc:
        result = failed_result(workspace.apk, exc, time.monotonic() - started)
        message = f"Warning: static bridge discovery failed: {result['error']}"
    workspace.static_bridges.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    host.echo(message)
