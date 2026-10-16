"""core/static: minimal Android binary XML reader for package, minSdkVersion and targetSdkVersion."""

from __future__ import annotations

import struct

RES_STRING_POOL_TYPE = 0x0001
RES_XML_TYPE = 0x0003
RES_XML_START_ELEMENT_TYPE = 0x0102
UTF8_FLAG = 0x100
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
NO_INDEX = 0xFFFFFFFF


def string_pool(data: bytes, offset: int) -> list[str]:
    header_size, chunk_size = struct.unpack_from("<HI", data, offset + 2)
    count, _styles, flags, strings_start, _ = struct.unpack_from("<IIIII", data, offset + 8)
    utf8 = bool(flags & UTF8_FLAG)
    base = offset + strings_start
    strings = []
    for i in range(count):
        (rel,) = struct.unpack_from("<I", data, offset + header_size + 4 * i)
        strings.append(read_pool_string(data, base + rel, utf8))
    return strings


def read_length(data: bytes, pos: int, utf8: bool) -> tuple[int, int]:
    if utf8:
        length = data[pos]
        if length & 0x80:
            return ((length & 0x7F) << 8) | data[pos + 1], pos + 2
        return length, pos + 1
    (length,) = struct.unpack_from("<H", data, pos)
    if length & 0x8000:
        (low,) = struct.unpack_from("<H", data, pos + 2)
        return ((length & 0x7FFF) << 16) | low, pos + 4
    return length, pos + 2


def read_pool_string(data: bytes, pos: int, utf8: bool) -> str:
    if utf8:
        _chars, pos = read_length(data, pos, True)
        size, pos = read_length(data, pos, True)
        return data[pos : pos + size].decode("utf-8", errors="replace")
    size, pos = read_length(data, pos, False)
    return data[pos : pos + 2 * size].decode("utf-16-le", errors="replace")


def attribute_int(strings: list[str], raw_idx: int, value_type: int, value: int) -> int | None:
    if value_type in (TYPE_INT_DEC, TYPE_INT_HEX):
        return value
    text = strings[raw_idx] if raw_idx != NO_INDEX and raw_idx < len(strings) else None
    if value_type == TYPE_STRING and text is not None and text.strip().isdigit():
        return int(text.strip())
    return None


def manifest_info(data: bytes | None) -> dict:
    info: dict = {"package": None, "min_sdk": None, "target_sdk": None}
    try:
        parse_into(data or b"", info)
    except (struct.error, IndexError, ValueError):
        pass
    if info["target_sdk"] is None:
        info["target_sdk"] = info["min_sdk"]
    return info


def parse_into(data: bytes, info: dict) -> None:
    (chunk_type, header_size) = struct.unpack_from("<HH", data, 0)
    if chunk_type != RES_XML_TYPE:
        return
    strings: list[str] = []
    pos = header_size
    while pos + 8 <= len(data):
        chunk_type, header_size, chunk_size = struct.unpack_from("<HHI", data, pos)
        if chunk_size <= 0:
            return
        if chunk_type == RES_STRING_POOL_TYPE:
            strings = string_pool(data, pos)
        elif chunk_type == RES_XML_START_ELEMENT_TYPE:
            read_element(data, pos, header_size, strings, info)
        pos += chunk_size


def read_element(data: bytes, pos: int, header_size: int, strings: list[str], info: dict) -> None:
    _ns, name_idx = struct.unpack_from("<II", data, pos + header_size)
    attr_start, attr_size, attr_count = struct.unpack_from("<HHH", data, pos + header_size + 8)
    element = strings[name_idx] if name_idx < len(strings) else ""
    if element not in ("manifest", "uses-sdk"):
        return
    base = pos + header_size + attr_start
    for i in range(attr_count):
        a = base + i * attr_size
        _ns, attr_name, raw, _size, _res0, value_type, value = struct.unpack_from("<IIIHBBI", data, a)
        name = strings[attr_name] if attr_name < len(strings) else ""
        if element == "manifest" and name == "package" and raw != NO_INDEX:
            info["package"] = strings[raw]
        elif element == "uses-sdk" and name == "minSdkVersion":
            info["min_sdk"] = attribute_int(strings, raw, value_type, value)
        elif element == "uses-sdk" and name == "targetSdkVersion":
            info["target_sdk"] = attribute_int(strings, raw, value_type, value)
