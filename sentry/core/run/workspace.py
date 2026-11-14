"""core/run: the per-run workspace: target/ (APK, event log, JSON report, static bridges, agent, .env) and logs/ (copies, Markdown)."""

from __future__ import annotations

import shutil
from pathlib import Path


class Workspace:
    def __init__(self, root: Path = Path(".")) -> None:
        self.target = root / "target"
        self.logs = root / "logs"
        self.apk = self.target / "app.apk"
        self.output_log = self.target / "output.log"
        self.logs_output = self.logs / "output.log"
        self.report_json = self.target / "report.json"
        self.report_md = self.logs / "report.md"
        self.env_file = self.target / ".env"
        self.agent = self.target / "agent.js"
        self.static_bridges = self.target / "static-bridges.json"
        self.intent_profile = self.target / "intent-data-profile.json"

    @property
    def capture_files(self) -> list[Path]:
        """Where the raw event stream is written (both copies)."""
        return [self.output_log, self.logs_output]

    def prepare(self, apk_input: str, package: str, verbose: bool = False) -> None:
        self.target.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        shutil.copy(apk_input, self.apk)
        self.output_log.touch()
        self.report_json.unlink(missing_ok=True)
        self.report_md.unlink(missing_ok=True)
        self.static_bridges.unlink(missing_ok=True)
        self.intent_profile.unlink(missing_ok=True)
        # SENTRY_VERBOSE rides along in .env so the Docker runner's containers (which only see this
        # file, not the CLI argv) can pick it up too - core.runners.container.entry reads it back.
        self.env_file.write_text(f"APP_PACKAGE={package}\nSENTRY_VERBOSE={'true' if verbose else 'false'}\n", encoding="utf-8")
