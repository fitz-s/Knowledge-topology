"""P7 doctor checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knowledge_topology.paths import TopologyPaths
from knowledge_topology.storage.registry import read_jsonl


@dataclass(frozen=True)
class DoctorResult:
    ok: bool
    messages: list[str]


def stale_anchors(root: str | Path, *, subject_repo_id: str, subject_head_sha: str) -> DoctorResult:
    paths = TopologyPaths.from_root(root)
    messages: list[str] = []
    for row in read_jsonl(paths.resolve("canonical/registry/file_refs.jsonl")):
        if row.get("repo_id") != subject_repo_id:
            continue
        if row.get("commit_sha") != subject_head_sha:
            messages.append(f"{row.get('path')}: stale anchor {row.get('commit_sha')} != {subject_head_sha}")
    return DoctorResult(ok=not messages, messages=messages)
