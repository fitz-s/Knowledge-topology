"""Canonical registry readers."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from knowledge_topology.paths import TopologyPaths
from knowledge_topology.ids import is_valid_id


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
        try:
            payload = json.loads(line)
        except JSONDecodeError as exc:
            raise RegistryError(f"{file_path}:{line_number} invalid JSONL: {exc.msg}") from exc
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
        ids = set()
        for row in self.nodes():
            node_id = row.get("id")
            if not isinstance(node_id, str) or not is_valid_id(node_id, prefix="nd"):
                raise RegistryError(f"registry node id must be an nd_ opaque ID: {node_id}")
            ids.add(node_id)
        return ids
