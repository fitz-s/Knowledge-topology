"""P7 session writeback worker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge_topology.ids import new_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.mutation_pack import MutationPack
from knowledge_topology.workers.compose_builder import deterministic_reltest_id
from knowledge_topology.storage.transaction import atomic_write_text


class WritebackError(ValueError):
    """Raised when writeback input is invalid."""


def _require(value: str, field: str) -> None:
    if not value.strip():
        raise WritebackError(f"{field} is required")


def writeback_session(
    root: str | Path,
    *,
    summary_path: str | Path,
    subject_repo_id: str,
    subject_head_sha: str,
    base_canonical_rev: str,
    current_canonical_rev: str,
    current_subject_head_sha: str,
) -> tuple[Path, Path]:
    for field, value in {
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "base_canonical_rev": base_canonical_rev,
        "current_canonical_rev": current_canonical_rev,
        "current_subject_head_sha": current_subject_head_sha,
    }.items():
        _require(value, field)
    if base_canonical_rev != current_canonical_rev:
        raise WritebackError("base_canonical_rev is stale")
    if subject_head_sha != current_subject_head_sha:
        raise WritebackError("subject_head_sha is stale")
    paths = TopologyPaths.from_root(root)
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    decisions = summary.get("decisions", [])
    invariants = summary.get("invariants", [])
    changes: list[dict[str, Any]] = []
    for statement in decisions:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": str(statement),
            "source_id": summary["source_id"],
            "digest_id": summary["digest_id"],
            "type": "decision",
        })
    for statement in invariants:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": str(statement),
            "source_id": summary["source_id"],
            "digest_id": summary["digest_id"],
            "type": "invariant",
        })
    if not changes:
        raise WritebackError("writeback summary must include decisions or invariants")
    pack = MutationPack(
        schema_version="1.0",
        id=new_id("mut"),
        proposal_type="digest_reconcile",
        proposed_by="writeback",
        base_canonical_rev=base_canonical_rev,
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        changes=changes,
        evidence_refs=[summary["digest_id"], summary["source_id"]],
        requires_human=False,
        human_gate_class=None,
        merge_confidence="medium",
        metadata={"writeback_summary": str(summary_path)},
    )
    mutation_path = paths.resolve(f"mutations/pending/{pack.id}.json")
    atomic_write_text(mutation_path, json.dumps(pack.to_dict(), indent=2, sort_keys=True) + "\n")
    delta_dir = paths.ensure_dir(f".tmp/writeback/{pack.id}")
    reltest_path = delta_dir / "relationship-tests.yaml"
    reltest_lines = []
    for change in changes:
        if change.get("type") == "invariant":
            reltest_lines.extend([
                "- schema_version: 1.0",
                f"  id: {deterministic_reltest_id(change['node_id'])}",
                f"  invariant_node_id: {change['node_id']}",
                f"  property: {json.dumps(change['reason'])}",
                f"  evidence_refs: {json.dumps(pack.evidence_refs)}",
                "  suggested_test_shape: unit",
                "  failure_if: [\"invariant is violated\"]",
                "  status: draft",
            ])
    atomic_write_text(reltest_path, ("\n".join(reltest_lines) + "\n") if reltest_lines else "[]\n")
    return mutation_path, reltest_path
