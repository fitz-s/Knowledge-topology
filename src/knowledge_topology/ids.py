"""Opaque durable ID helpers."""

from __future__ import annotations

import secrets
import time


CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

VALID_PREFIXES = {
    "src",
    "dg",
    "mut",
    "job",
    "evt",
    "gap",
    "clm",
    "edg",
    "nd",
    "syn",
    "esc",
    "reltest",
}


def _encode_crockford(value: int, length: int) -> str:
    if value < 0:
        raise ValueError("value must be non-negative")
    chars = []
    for _ in range(length):
        chars.append(CROCKFORD32[value & 31])
        value >>= 5
    if value:
        raise ValueError("value does not fit requested length")
    return "".join(reversed(chars))


def new_id(prefix: str, *, timestamp_ms: int | None = None, random_bytes: bytes | None = None) -> str:
    """Return an immutable opaque ID with a ULID-compatible suffix."""

    if prefix not in VALID_PREFIXES:
        raise ValueError(f"unknown id prefix: {prefix}")
    timestamp = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    random_part = secrets.token_bytes(10) if random_bytes is None else random_bytes
    if len(random_part) != 10:
        raise ValueError("random_bytes must be exactly 10 bytes")
    ulid = _encode_crockford(timestamp, 10) + _encode_crockford(int.from_bytes(random_part, "big"), 16)
    return f"{prefix}_{ulid}"


def is_valid_id(value: str, *, prefix: str | None = None) -> bool:
    """Return whether a string looks like a topology opaque ID."""

    if "_" not in value:
        return False
    found_prefix, suffix = value.split("_", 1)
    if prefix is not None and found_prefix != prefix:
        return False
    if found_prefix not in VALID_PREFIXES:
        return False
    return len(suffix) == 26 and all(ch in CROCKFORD32 for ch in suffix)
