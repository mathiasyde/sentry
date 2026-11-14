"""core/run: command-line options for analyse.sh; positional arguments pass through untouched."""

from __future__ import annotations

OPTION = "--discover-bridge-interfaces"
NEGATED = "--no-discover-bridge-interfaces"
VERBOSE_OPTION = "--verbose"
VERBOSE_NEGATED = "--no-verbose"
TRUE_VALUES = {"true", "yes", "on", "1"}
FALSE_VALUES = {"false", "no", "off", "0"}
USAGE_OPTIONS = (
    "Options: --[no-]discover-bridge-interfaces[=true|false]  static JavaScript bridge discovery (default: true)\n"
    "         --[no-]verbose[=true|false]                     verbose static-analysis logging (default: false)"
)


class OptionError(ValueError):
    pass


def parse_bool(option: str, value: str) -> bool:
    lowered = value.lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise OptionError(f"invalid value '{value}' for {option} (expected true or false)")


def parse_args(argv: list[str]) -> tuple[list[str], bool, bool]:
    """(positional arguments in order, whether static bridge discovery is on, whether verbose logging is on).

    The last occurrence of each option wins.
    """
    positionals: list[str] = []
    discover = True
    verbose = False
    for arg in argv:
        if arg == OPTION:
            discover = True
        elif arg == NEGATED:
            discover = False
        elif arg.startswith(OPTION + "="):
            discover = parse_bool(OPTION, arg[len(OPTION) + 1 :])
        elif arg == VERBOSE_OPTION:
            verbose = True
        elif arg == VERBOSE_NEGATED:
            verbose = False
        elif arg.startswith(VERBOSE_OPTION + "="):
            verbose = parse_bool(VERBOSE_OPTION, arg[len(VERBOSE_OPTION) + 1 :])
        else:
            positionals.append(arg)
    return positionals, discover, verbose
