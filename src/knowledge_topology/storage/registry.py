"""Canonical registry readers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge_topology.paths import TopologyPaths


class RegistryError(ValueError):
    """Raised when registry data is invalid."""


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    file_path = Path(path)
    if not file_path.exists():
        return rows
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RegistryError(f"{file_path}:{line_number} must be a JSON object")
        rows.append(payload)
    return rows


class Registry:
    """Read-only view of canonical registry files."""

    def __init__(self, root: str | Path):
        self.paths = TopologyPaths.from_root(root)

    def nodes(self) -> list[dict[str, Any]]:
        return read_jsonl(self.paths.resolve("canonical/registry/nodes.jsonl"))

    def known_node_ids(self) -> set[str]:
        return {row["id"] for row in self.nodes() if isinstance(row.get("id"), str)}
