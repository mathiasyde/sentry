"""core/static intent_data_profile: manifest activity/intent-filter parsing and key resolution."""

from __future__ import annotations

import struct
import sys
import unittest

from tests.helpers import REPO_ROOT, SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.static.axml import activities  # noqa: E402
from core.static.dex import DexFile  # noqa: E402
from core.static.intent_data_profile import (  # noqa: E402
    BUNDLE_GET, EXTRA, QUERY, IntentResolver, build_intent_profiles, resolve_class,
)

RES_XML_TYPE = 0x0003
RES_STRING_POOL_TYPE = 0x0001
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_END_ELEMENT_TYPE = 0x0103
TYPE_STRING = 0x03
TYPE_INT_BOOLEAN = 0x12
NO_INDEX = 0xFFFFFFFF


# --- a minimal binary AXML document, built by hand from the chunk formats core/static/axml.py reads ---


def string_pool(strings: list[str]) -> bytes:
    data, offsets = b"", []
    for s in strings:
        raw = s.encode("utf-8")
        offsets.append(len(data))
        data += bytes([len(s)]) + bytes([len(raw)]) + raw + b"\x00"
    header_size = 28
    ids = struct.pack(f"<{len(strings)}I", *offsets)
    strings_start = header_size + len(ids)
    body = ids + data
    body += b"\x00" * ((-len(body)) % 4)
    chunk_size = header_size + len(body)
    header = struct.pack("<HHIIIIII", RES_STRING_POOL_TYPE, header_size, chunk_size, len(strings), 0, 0x100, strings_start, 0)
    return header + body


def start_elem(name_idx: int, attrs: list[tuple[int, int, int, int]]) -> bytes:
    attr_ext = struct.pack("<IIHHHHHH", NO_INDEX, name_idx, 20, 20, len(attrs), 0, 0, 0)
    attr_bytes = b"".join(struct.pack("<IIIHBBI", NO_INDEX, n, r, 0, 0, t, v) for n, t, r, v in attrs)
    body = struct.pack("<II", 0, NO_INDEX) + attr_ext + attr_bytes
    return struct.pack("<HHI", RES_XML_START_ELEMENT_TYPE, 16, 8 + len(body)) + body


def end_elem() -> bytes:
    body = struct.pack("<IIII", 0, NO_INDEX, NO_INDEX, NO_INDEX)
    return struct.pack("<HHI", RES_XML_END_ELEMENT_TYPE, 16, 8 + len(body)) + body


def build_manifest() -> bytes:
    strings = [
        "manifest", "application", "activity", "intent-filter", "action", "category", "data",
        "name", "exported", "scheme", "host", "pathPrefix",
        "com.example.Foo", "android.intent.action.VIEW",
        "android.intent.category.DEFAULT", "android.intent.category.BROWSABLE",
        "myapp", "open", "/item",
    ]
    idx = {s: i for i, s in enumerate(strings)}
    body = (
        start_elem(idx["manifest"], [])
        + start_elem(idx["application"], [])
        + start_elem(idx["activity"], [(idx["name"], TYPE_STRING, idx["com.example.Foo"], 0), (idx["exported"], TYPE_INT_BOOLEAN, NO_INDEX, 1)])
        + start_elem(idx["intent-filter"], [])
        + start_elem(idx["action"], [(idx["name"], TYPE_STRING, idx["android.intent.action.VIEW"], 0)])
        + end_elem()
        + start_elem(idx["category"], [(idx["name"], TYPE_STRING, idx["android.intent.category.DEFAULT"], 0)])
        + end_elem()
        + start_elem(idx["category"], [(idx["name"], TYPE_STRING, idx["android.intent.category.BROWSABLE"], 0)])
        + end_elem()
        + start_elem(idx["data"], [(idx["scheme"], TYPE_STRING, idx["myapp"], 0), (idx["host"], TYPE_STRING, idx["open"], 0), (idx["pathPrefix"], TYPE_STRING, idx["/item"], 0)])
        + end_elem()
        + end_elem()  # /intent-filter
        + end_elem()  # /activity
        + end_elem()  # /application
        + end_elem()  # /manifest
    )
    doc = string_pool(strings) + body
    return struct.pack("<HHI", RES_XML_TYPE, 8, 8 + len(doc)) + doc


class Activities(unittest.TestCase):
    def test_nested_intent_filter_and_data(self) -> None:
        (activity,) = activities(build_manifest())
        self.assertEqual(activity["class"], "com.example.Foo")
        self.assertIs(activity["exported"], True)
        (filt,) = activity["intent_filters"]
        self.assertEqual(filt["actions"], ["android.intent.action.VIEW"])
        self.assertEqual(filt["categories"], ["android.intent.category.DEFAULT", "android.intent.category.BROWSABLE"])
        self.assertEqual(filt["data"], [{"scheme": "myapp", "host": "open", "pathPrefix": "/item"}])

    def test_truncated_or_missing_manifest_is_empty(self) -> None:
        self.assertEqual(activities(b"\x03\x00"), [])
        self.assertEqual(activities(None), [])


class ResolveClass(unittest.TestCase):
    def test_package_relative_and_bare_and_absolute_names(self) -> None:
        self.assertEqual(resolve_class(".MainActivity", "com.example.app"), "com.example.app.MainActivity")
        self.assertEqual(resolve_class("MainActivity", "com.example.app"), "com.example.app.MainActivity")
        self.assertEqual(resolve_class("com.other.MainActivity", "com.example.app"), "com.other.MainActivity")
        self.assertIsNone(resolve_class(None, "com.example.app"))


# --- a minimal real DEX: just enough id tables to exercise IntentResolver's method filter ---


def mutf8(s: str) -> bytes:
    raw = s.encode("utf-8")
    return bytes([len(raw)]) + raw + b"\x00"


def build_dex() -> bytes:
    strings = [
        "Landroid/content/Intent;", "Ljava/lang/String;", "Landroid/net/Uri;", "Landroid/os/Bundle;",
        "Lcom/x/Other;", "getStringExtra", "getQueryParameter", "getString", "unrelatedMethod",
    ]
    header = bytearray(0x70)
    header[0:8] = b"dex\n035\x00"

    # Physical layout, in file order: header, string_ids, type_ids, params, proto_ids, method_ids, string_data.
    string_ids_off = 0x70
    type_ids_off = string_ids_off + 4 * len(strings)
    type_ids = struct.pack("<5I", *range(5))  # types 0..4 map 1:1 to the first five strings

    params_off = type_ids_off + len(type_ids)
    params = struct.pack("<IH", 1, 1)  # one param: type index 1 (Ljava/lang/String;)

    proto_ids_off = params_off + len(params)
    proto_ids = struct.pack("<III", 1, 1, params_off)  # shorty (unused), return String, params

    method_ids_off = proto_ids_off + len(proto_ids)
    methods = [
        (0, 0, 5),  # Intent.getStringExtra(String) -> EXTRA
        (2, 0, 6),  # Uri.getQueryParameter(String) -> QUERY
        (3, 0, 7),  # Bundle.getString(String) -> BUNDLE_GET
        (4, 0, 5),  # Other.getStringExtra(String) -> not a target (wrong class)
        (0, 0, 8),  # Intent.unrelatedMethod(String) -> not a target (wrong name)
    ]
    method_ids = b"".join(struct.pack("<HHI", cls, proto, name) for cls, proto, name in methods)

    string_data_off = method_ids_off + len(method_ids)
    string_ids, string_data = b"", b""
    for s in strings:
        string_ids += struct.pack("<I", string_data_off + len(string_data))
        string_data += mutf8(s)

    struct.pack_into(
        "<12I", header, 0x38,
        len(strings), string_ids_off,
        5, type_ids_off,
        1, proto_ids_off,
        0, 0,
        len(methods), method_ids_off,
        0, 0,
    )
    return bytes(header) + string_ids + type_ids + params + proto_ids + method_ids + string_data


class IntentResolverTargets(unittest.TestCase):
    def test_recognizes_key_accessors_by_exact_class_and_name(self) -> None:
        dex = DexFile(build_dex())
        resolver = IntentResolver(dex, index=None)  # static_string() is never reached in this test
        self.assertEqual(resolver.targets, {0: EXTRA, 1: QUERY, 2: BUNDLE_GET})


class EndToEnd(unittest.TestCase):
    def test_strong_update_benchmark(self) -> None:
        result = build_intent_profiles(REPO_ROOT / "Benchmark" / "strongUpdate.apk")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["package"], "com.example.strongupdate")
        (activity,) = result["activities"]
        self.assertEqual(activity["class_name"], "com.example.strongupdate.MainActivity")
        self.assertTrue(activity["exported"])
        self.assertTrue(activity["exported_declared"])
        self.assertEqual(len(activity["intent_filters"]), 1)
        self.assertEqual(activity["intent_keys"], [])  # the benchmark app never reads back Intent/Uri data


if __name__ == "__main__":
    unittest.main()
