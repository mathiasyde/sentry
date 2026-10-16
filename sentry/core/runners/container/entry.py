"""core/runners/container: entry point of the sentry container; spawns the app with the prebuilt agent."""

from __future__ import annotations

from pathlib import Path

from core.agent import build_agent
from core.host import Host

ENV_FILE = Path("/sentry/target/.env")
AGENT = "/sentry/build/agent.js"
STATIC_BRIDGES = Path("/sentry/target/static-bridges.json")
STATIC_AGENT = Path("/sentry/target/agent.js")


def load_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def agent_path(static_bridges: Path = STATIC_BRIDGES, out: Path = STATIC_AGENT) -> str:
    """Rebuild the agent with the run's statically discovered bridges; fall back to the prebuilt one.

    Prints nothing: this container's stdout is the event stream.
    """
    if not static_bridges.is_file():
        return AGENT
    args = ["--root", "/sentry", "--out", str(out), "--static-bridges", str(static_bridges)]
    return str(out) if build_agent.main(args) == 0 else AGENT


def main(host: Host | None = None, env_file: Path = ENV_FILE) -> int:
    host = host or Host()
    host.env.update(load_env(env_file))

    host.run_checked(["adb", "connect", "emulator:5555"])
    host.run_checked(["adb", "forward", "tcp:27042", "tcp:27042"])  # frida-server port
    host.run_checked(["adb", "reverse", "tcp:5173", "tcp:5173"])  # web server
    return host.run(["frida", "-H", "127.0.0.1:27042", "-f", host.env["APP_PACKAGE"], "-l", agent_path()]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
