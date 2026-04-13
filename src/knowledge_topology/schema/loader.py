"""Schema fixture loading helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SchemaLoadError(ValueError):
    """Raised when a JSON fixture does not satisfy the minimum schema contract."""


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SchemaLoadError("schema payload must be a JSON object")
    return payload


def require_fields(payload: dict[str, Any], fields: list[str] | tuple[str, ...]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise SchemaLoadError(f"missing required fields: {', '.join(missing)}")
