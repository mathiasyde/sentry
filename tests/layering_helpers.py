"""Helpers shared by the per-area layering and size tests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

AREA_WORDS = ("browser", "native", "core")


def iter_files(area_dir: Path, suffixes: Iterable[str]) -> list[Path]:
    suffixes = tuple(suffixes)
    return sorted(
        path
        for path in Path(area_dir).rglob("*")
        if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts
    )


def line_count(path: Path) -> int:
    return len(Path(path).read_text(encoding="utf-8").splitlines())


def code_lines(path: Path) -> list[tuple[int, str]]:
    """Lines that are not pure comments (// or #)."""
    result = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        result.append((number, line))
    return result


def assert_no_pattern(testcase, files: Iterable[Path], regex: str, why: str) -> None:
    pattern = re.compile(regex)
    for path in files:
        for number, line in code_lines(path):
            if pattern.search(line):
                testcase.fail(f"{path}:{number}: {why}: {line.strip()}")


def assert_has_header(testcase, path: Path) -> None:
    lines = [line for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    first = lines[0].strip() if lines else ""
    is_comment = first.startswith(("//", "#", '"""', "/*"))
    mentions_area = any(word in first for word in AREA_WORDS)
    testcase.assertTrue(
        is_comment and mentions_area,
        f"{path}: first line must be a responsibility header naming browser/native/core, got {first!r}",
    )


def assert_max_lines(testcase, files: Iterable[Path], limit: int) -> None:
    for path in files:
        count = line_count(path)
        testcase.assertLessEqual(count, limit, f"{path} has {count} lines (limit {limit})")
