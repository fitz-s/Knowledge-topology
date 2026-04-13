"""P7 session writeback worker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge_topology.ids import is_valid_id
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


def _string_list(summary: dict[str, Any], field: str) -> list[str]:
    value = summary.get(field, [])
    if not isinstance(value, list):
        raise WritebackError(f"{field} must be a list of non-empty strings")
    normalized: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise WritebackError(f"{field}[{index}] must be a non-empty string")
        normalized.append(item.strip())
    return normalized


def load_summary(summary_path: str | Path) -> tuple[str, str, list[str], list[str]]:
    path = Path(summary_path)
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WritebackError(f"summary JSON is invalid: {exc}") from exc
    if not isinstance(summary, dict):
        raise WritebackError("summary JSON must be an object")
    source_id = summary.get("source_id")
    digest_id = summary.get("digest_id")
    if not isinstance(source_id, str) or not is_valid_id(source_id, prefix="src"):
        raise WritebackError("source_id must use src_ opaque ID")
    if not isinstance(digest_id, str) or not is_valid_id(digest_id, prefix="dg"):
        raise WritebackError("digest_id must use dg_ opaque ID")
    return source_id, digest_id, _string_list(summary, "decisions"), _string_list(summary, "invariants")


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
    source_id, digest_id, decisions, invariants = load_summary(summary_path)
    changes: list[dict[str, Any]] = []
    for statement in decisions:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": str(statement),
            "source_id": source_id,
            "digest_id": digest_id,
            "type": "decision",
        })
    for statement in invariants:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": str(statement),
            "source_id": source_id,
            "digest_id": digest_id,
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
        evidence_refs=[digest_id, source_id],
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
