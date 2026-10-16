"""core/run: command-line options for analyse.sh; positional arguments pass through untouched."""

from __future__ import annotations

OPTION = "--discover-bridge-interfaces"
NEGATED = "--no-discover-bridge-interfaces"
TRUE_VALUES = {"true", "yes", "on", "1"}
FALSE_VALUES = {"false", "no", "off", "0"}
USAGE_OPTIONS = "Options: --[no-]discover-bridge-interfaces[=true|false]  static JavaScript bridge discovery (default: true)"


class OptionError(ValueError):
    pass


def parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise OptionError(f"invalid value '{value}' for {OPTION} (expected true or false)")


def parse_args(argv: list[str]) -> tuple[list[str], bool]:
    """(positional arguments in order, whether static bridge discovery is on). The last option wins."""
    positionals: list[str] = []
    discover = True
    for arg in argv:
        if arg == OPTION:
            discover = True
        elif arg == NEGATED:
            discover = False
        elif arg.startswith(OPTION + "="):
            discover = parse_bool(arg[len(OPTION) + 1 :])
        else:
            positionals.append(arg)
    return positionals, discover
