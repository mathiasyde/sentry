"""core/run: profile Intent/URI data for WebView-touching activities; never fails or warns the run.

Unlike static bridge discovery (core/run/discovery.py), a failure here stays silent even in the
artifact's own error field: this is exploratory, best-effort static analysis layered on top of the
bridge scan, not something the user needs to be told to go fix. The artifact still records
"failed" and why, for anyone who goes looking, but nothing is echoed unless verbose logging asked
for the successful summary too.
"""

from __future__ import annotations

import json

from core.host import Host
from core.run.workspace import Workspace
from core.static.intent_data_profile import build_intent_profiles, failed_result, summary_line

ARTIFACT_LABEL = "target/intent-data-profile.json"


def run_intent_profile(host: Host, workspace: Workspace, verbose: bool) -> None:
    """Scan target/app.apk and write the artifact. Errors are fixed silently: no warning either way.

    KeyboardInterrupt and SystemExit are not caught, so Ctrl-C and SIGTERM keep their exit codes.
    """
    try:
        result = build_intent_profiles(workspace.apk)
        message = summary_line(result, ARTIFACT_LABEL) if verbose else None
    except Exception as exc:
        result = failed_result(workspace.apk, exc)
        message = None
    workspace.intent_profile.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if message:
        host.echo(message)
