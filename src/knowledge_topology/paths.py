"""Topology path resolution and initialization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


QUEUE_KINDS = ("ingest", "digest", "reconcile", "apply", "compile", "audit", "writeback")
QUEUE_STATES = ("pending", "leased", "done", "failed")
REGISTRY_FILES = ("nodes.jsonl", "claims.jsonl", "edges.jsonl", "aliases.jsonl", "file_refs.jsonl")


class PathSafetyError(ValueError):
    """Raised when a path would escape or violate the topology root."""


@dataclass(frozen=True)
class TopologyPaths:
    root: Path

    @classmethod
    def from_root(cls, root: str | Path, *, allow_fixture_topology: bool = False) -> "TopologyPaths":
        resolved = Path(root).expanduser().resolve()
        if ".topology" in resolved.parts and not allow_fixture_topology:
            raise PathSafetyError("production topology root must not be a nested .topology directory")
        return cls(resolved)

    def resolve(self, relative: str | Path, *, allow_fixture_topology: bool = False) -> Path:
        rel = Path(relative)
        if rel.is_absolute():
            raise PathSafetyError("absolute paths are not allowed inside topology root")
        if ".topology" in rel.parts and not allow_fixture_topology:
            raise PathSafetyError("nested production .topology paths are not allowed")
        target = (self.root / rel).resolve()
        if target != self.root and self.root not in target.parents:
            raise PathSafetyError(f"path escapes topology root: {relative}")
        return target

    def ensure_dir(self, relative: str | Path) -> Path:
        path = self.resolve(relative)
        path.mkdir(parents=True, exist_ok=True)
        return path


def expected_directories() -> list[str]:
    dirs = [
        "raw/packets",
        "raw/excerpts",
        "raw/local_blobs",
        "digests/by_source",
        "canonical/nodes",
        "canonical/syntheses",
        "canonical/registry",
        "mutations/pending",
        "mutations/approved",
        "mutations/applied",
        "mutations/rejected",
        "ops/events",
        "ops/gaps",
        "ops/escalations",
        "ops/reports",
        "ops/leases",
        "projections/builders",
        "projections/tasks",
        "projections/openclaw",
        "prompts",
        "tests/fixtures",
    ]
    for kind in QUEUE_KINDS:
        for state in QUEUE_STATES:
            dirs.append(f"ops/queue/{kind}/{state}")
    return dirs


def initialize_topology(root: str | Path) -> list[Path]:
    paths = TopologyPaths.from_root(root)
    created_or_existing = [paths.ensure_dir(directory) for directory in expected_directories()]
    registry_dir = paths.ensure_dir("canonical/registry")
    for filename in REGISTRY_FILES:
        (registry_dir / filename).touch(exist_ok=True)
    return created_or_existing
