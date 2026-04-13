"""Digest model output adapter boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, Any


class DigestModelAdapter(Protocol):
    """Loads a model-produced digest payload without applying business rules."""

    def load_output(self) -> dict[str, Any]:
        """Return raw digest JSON payload."""


class JsonFileDigestAdapter:
    """Digest adapter for already-produced JSON fixture/model output."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_output(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("digest model output must be a JSON object")
        return payload
