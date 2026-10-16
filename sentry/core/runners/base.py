"""core/runners: the Runner strategy interface and the context every runner receives."""

from __future__ import annotations

from dataclasses import dataclass

from core.host import Host
from core.run.workspace import Workspace


@dataclass
class RunContext:
    host: Host
    workspace: Workspace
    apk: str
    package: str
    kvm_available: bool


class Runner:
    """A way to run the app under Frida and stream the agent's events into the workspace."""

    name = "runner"

    def preflight(self, context: RunContext) -> None:
        """Checks that must pass before the workspace is prepared (no report is generated if they fail)."""

    def run(self, context: RunContext) -> None:
        raise NotImplementedError
