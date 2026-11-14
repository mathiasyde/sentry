"""core/static: APK container access: ordered dex files and the binary manifest."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

DEX_NAME_RE = re.compile(r"^classes(\d*)\.dex$")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Apk:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)

    def dex_names(self) -> list[str]:
        """classes.dex, classes2.dex, classes3.dex, ... in multidex load order."""
        names = [(DEX_NAME_RE.match(name), name) for name in self.zip.namelist()]
        found = [(int(match.group(1) or 1), name) for match, name in names if match]
        return [name for _, name in sorted(found)]

    def read(self, name: str) -> bytes:
        return self.zip.read(name)

    def manifest(self) -> bytes | None:
        try:
            return self.zip.read("AndroidManifest.xml")
        except KeyError:
            return None

    def sha256(self) -> str:
        return file_sha256(self.path)

    def close(self) -> None:
        self.zip.close()
