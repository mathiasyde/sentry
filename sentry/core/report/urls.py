"""core/report: URL and origin classification."""

from __future__ import annotations

from urllib.parse import urlparse


def url_origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        return None
    if parsed.scheme in {"file", "data", "about", "javascript"}:
        return parsed.scheme + ":"
    if not parsed.netloc:
        return parsed.scheme + ":"
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_trusted_origin(origin: str) -> str:
    return url_origin(origin) or origin.rstrip("/")


def is_remote_url(url: str | None) -> bool:
    return bool(url and urlparse(url).scheme in {"http", "https"})


def is_cleartext_url(url: str | None) -> bool:
    return bool(url and urlparse(url).scheme == "http")


def is_local_file_url(url: str | None) -> bool:
    return bool(url and urlparse(url).scheme == "file")


def is_data_url(url: str | None) -> bool:
    return bool(url and urlparse(url).scheme == "data")


def is_trusted(url: str | None, trusted_origins: set[str]) -> bool:
    if not trusted_origins:
        return False
    origin = url_origin(url)
    return bool(origin and origin in trusted_origins)
