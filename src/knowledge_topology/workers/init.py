"""Topology initialization worker."""

from __future__ import annotations

from pathlib import Path

from knowledge_topology.paths import initialize_topology


def init_topology(root: str | Path) -> list[Path]:
    return initialize_topology(root)
