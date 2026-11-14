"""Test doubles: a recording Host, and fake adb/frida executables for end-to-end runs without a device."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.host import Host, Result

FAKE_ADB = """#!/bin/sh
echo "adb $*" >> "$SENTRY_FAKE_CALLS"
[ "$1" = "-s" ] && shift 2
case "$1" in
  get-state) echo device ;;
  install) echo "Success" ;;
  shell)
    case "$2" in
      getprop) echo 1 ;;
    esac
    ;;
esac
exit 0
"""

FAKE_FRIDA = """#!/bin/sh
echo "frida $*" >> "$SENTRY_FAKE_CALLS"
cat "$SENTRY_FAKE_EVENTS"
if [ -n "${SENTRY_FAKE_HANG:-}" ]; then
  echo "frida-ready" >> "$SENTRY_FAKE_CALLS"
  while :; do sleep 1; done
fi
"""


def install_fake_tools(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (("adb", FAKE_ADB), ("frida", FAKE_FRIDA)):
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)


class FakeHost(Host):
    """Records every command instead of running it; responses come from a callable."""

    def __init__(
        self,
        env: dict[str, str] | None = None,
        commands: set[str] = frozenset({"python3", "docker", "adb", "frida", "timeout"}),
        linux: bool = True,
        kvm: bool = True,
        respond: Callable[[list[str]], Result] | None = None,
    ) -> None:
        super().__init__(env or {"PATH": "/fake"})
        self.commands = set(commands)
        self.linux = linux
        self.kvm = kvm
        self.respond = respond or (lambda cmd: Result(0))
        self.calls: list[tuple] = []

    def which(self, name: str) -> str | None:
        return f"/fake/{name}" if name in self.commands else None

    def is_linux(self) -> bool:
        return self.linux

    def has_kvm(self) -> bool:
        return self.kvm

    def run(self, cmd, **kwargs) -> Result:
        self.calls.append(("run", list(cmd), {k: v for k, v in kwargs.items() if v not in (None, False)}))
        return self.respond(list(cmd))

    def tee(self, cmd, files) -> None:
        self.calls.append(("tee", list(cmd), [str(f) for f in files]))

    def sleep(self, seconds: float) -> None:
        self.calls.append(("sleep", seconds))

    def commands_run(self) -> list[list[str]]:
        return [call[1] for call in self.calls if call[0] in ("run", "tee")]
