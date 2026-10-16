"""core/static: static analysis of an APK for JavaScript bridges (stdlib only, no processes).

discover_bridges() returns the payload of target/static-bridges.json (schema 1). It raises on failure;
callers turn the exception into a "failed" artifact with failed_result().
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.static.apk import Apk, file_sha256
from core.static.axml import manifest_info
from core.static.dex import DexFile
from core.static.discover import PRE_17, discover

SCHEMA = 1
ERROR_LIMIT = 200


def discover_bridges(apk_path: str | Path) -> dict[str, Any]:
    started = time.monotonic()
    apk = Apk(apk_path)
    try:
        manifest = manifest_info(apk.manifest())
        names = apk.dex_names()
        dexes = [DexFile(apk.read(name), name) for name in names]
        linked, stats = discover(dexes, manifest["target_sdk"])
        sha256 = apk.sha256()
    finally:
        apk.close()
    target_sdk = manifest["target_sdk"]
    return {
        "schema": SCHEMA,
        "status": "completed",
        "error": None,
        "apk": {"path": str(apk_path), "sha256": sha256, "dex_files": names},
        "package": manifest["package"],
        "min_sdk": manifest["min_sdk"],
        "target_sdk": target_sdk,
        "all_public_methods_exposed": target_sdk is not None and target_sdk < PRE_17,
        **linked,
        "stats": {**stats, "seconds": round(time.monotonic() - started, 2)},
    }


def failed_result(apk_path: str | Path, exc: BaseException, seconds: float = 0.0) -> dict[str, Any]:
    error = " ".join(f"{type(exc).__name__}: {exc}".split())[:ERROR_LIMIT]
    try:
        sha256 = file_sha256(apk_path)
    except OSError:
        sha256 = None
    return {
        "schema": SCHEMA,
        "status": "failed",
        "error": error,
        "apk": {"path": str(apk_path), "sha256": sha256, "dex_files": []},
        "package": None,
        "min_sdk": None,
        "target_sdk": None,
        "all_public_methods_exposed": False,
        "registrations": [],
        "removals": [],
        "bridge_classes": [],
        "stats": {"classes": 0, "methods_scanned": 0, "seconds": round(seconds, 2)},
    }


def summary_line(result: dict[str, Any], path: str) -> str:
    registrations = result["registrations"]
    unresolved = sum(1 for r in registrations if r["name_status"] == "unresolved")
    return (
        f"Static bridge discovery: {len(registrations)} registration(s), {unresolved} with unresolved names, "
        f"{len(result['bridge_classes'])} bridge class(es) -> {path}"
    )
