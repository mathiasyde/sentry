"""core/runners: runner strategies (Docker, local) and the factory that picks one from SENTRY_RUNNER."""

from __future__ import annotations

from core.host import Host
from core.runners.base import RunContext, Runner
from core.runners.docker import DockerRunner
from core.runners.local import LocalRunner

RUNNERS: dict[str, type[Runner]] = {
    "docker": DockerRunner,
    "local": LocalRunner,
}


def select_runner(name: str, host: Host, kvm_available: bool) -> Runner:
    if name == "auto":
        name = "docker" if host.is_linux() and kvm_available else "local"
    if name not in RUNNERS:
        host.die(f"Error: invalid SENTRY_RUNNER '{name}' (expected auto, docker, or local)")
    return RUNNERS[name]()


__all__ = ["RUNNERS", "RunContext", "Runner", "select_runner"]
