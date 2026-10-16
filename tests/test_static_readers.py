"""core/static DEX and binary-manifest readers."""

from __future__ import annotations

import struct
import sys
import unittest

from tests.helpers import REPO_ROOT, SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.static.apk import Apk  # noqa: E402
from core.static.axml import manifest_info  # noqa: E402
from core.static.dex import DexFile, decode_mutf8, descriptor_to_java  # noqa: E402


def mini_dex(strings: list[bytes]) -> bytes:
    """A dex with only a header and a string table (enough for the string lookups)."""
    header = bytearray(0x70)
    header[0:8] = b"dex\n035\x00"
    ids_off = 0x70
    data_off = ids_off + 4 * len(strings)
    ids, data = b"", b""
    for raw in strings:
        ids += struct.pack("<I", data_off + len(data))
        data += bytes([len(raw)]) + raw + b"\x00"
    struct.pack_into("<II", header, 0x38, len(strings), ids_off)
    return bytes(header) + ids + data


class DexStrings(unittest.TestCase):
    def setUp(self) -> None:
        self.words = sorted(["Landroid/webkit/WebView;", "addJavascriptInterface", "alpha", "zeta", "Z"])
        self.dex = DexFile(mini_dex([w.encode() for w in self.words]))

    def test_find_string(self) -> None:
        for i, word in enumerate(self.words):
            self.assertEqual(self.dex.find_string(word), i)
        self.assertIsNone(self.dex.find_string("removeJavascriptInterface"))
        self.assertIsNone(self.dex.find_string(""))

    def test_rejects_non_dex(self) -> None:
        with self.assertRaises(ValueError):
            DexFile(b"PK\x03\x04" + bytes(200))

    def test_mutf8(self) -> None:
        self.assertEqual(decode_mutf8(b"a\xc0\x80b"), "a\x00b")
        self.assertEqual(decode_mutf8(b"\xed\xa0\xbd\xed\xb8\x80"), "\U0001F600")

    def test_descriptor_to_java(self) -> None:
        self.assertEqual(descriptor_to_java("Lcom/a/B;"), "com.a.B")
        self.assertEqual(descriptor_to_java("[I"), "int[]")
        self.assertEqual(descriptor_to_java("[[Ljava/lang/String;"), "java.lang.String[][]")
        self.assertEqual(descriptor_to_java("Z"), "boolean")


class Manifest(unittest.TestCase):
    def test_benchmark_manifest(self) -> None:
        apk = Apk(REPO_ROOT / "Benchmark" / "strongUpdate.apk")
        info = manifest_info(apk.manifest())
        apk.close()
        self.assertEqual(info["package"], "com.example.strongupdate")
        self.assertIsInstance(info["target_sdk"], int)
        self.assertGreaterEqual(info["target_sdk"], 17)

    def test_truncated_manifest(self) -> None:
        self.assertEqual(manifest_info(b"\x03\x00"), {"package": None, "min_sdk": None, "target_sdk": None})
        self.assertEqual(manifest_info(None), {"package": None, "min_sdk": None, "target_sdk": None})


if __name__ == "__main__":
    unittest.main()
