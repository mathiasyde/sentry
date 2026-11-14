"""core/runners: Docker Compose runner: emulator, frida-server and sentry containers on a Linux/KVM host."""

from __future__ import annotations

from pathlib import Path

from core.host import require_commands
from core.runners.base import RunContext, Runner


class DockerRunner(Runner):
    name = "docker"

    def preflight(self, context: RunContext) -> None:
        if not Path("docker-compose.yml").is_file():
            context.host.die("Error: docker-compose.yml not found")

    def run(self, context: RunContext) -> None:
        host = context.host
        require_commands(host, "docker")

        if not context.kvm_available:
            host.die(
                "Error: Docker emulator mode requires /dev/kvm.",
                "Use SENTRY_RUNNER=local with a running Android emulator on macOS or hosts without KVM.",
            )

        host.run(["docker", "compose", "down"])
        host.run(["docker", "compose", "up", "-d", "emulator", "run-frida-server", "sentry"])
        host.tee(["docker", "logs", "-f", "sentry"], context.workspace.capture_files)
