"""P4 conservative reconcile worker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge_topology.ids import new_id
from knowledge_topology.ids import is_valid_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.digest import Digest
from knowledge_topology.schema.loader import load_json
from knowledge_topology.schema.mutation_pack import MutationPack
from knowledge_topology.storage.registry import Registry
from knowledge_topology.storage.transaction import atomic_write_text


class ReconcileError(ValueError):
    """Raised when reconcile cannot safely produce a proposal."""


def _require_nonblank(value: str, field: str) -> None:
    if not value.strip():
        raise ReconcileError(f"{field} is required")


def claim_statement(claim: Any) -> str:
    if isinstance(claim, dict):
        for key in ("statement", "text", "claim"):
            value = claim.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(claim, str) and claim.strip():
        return claim.strip()
    return json.dumps(claim, sort_keys=True)


def human_gate_for_edges(edges: list[dict[str, Any]]) -> tuple[bool, str | None]:
    edge_types = {edge.get("edge_type") for edge in edges}
    if "SUPERSEDES" in edge_types:
        return True, "supersede_delete"
    if "CONTRADICTS" in edge_types:
        return True, "high_impact_contradiction"
    return False, None


def reconcile_digest(
    root: str | Path,
    *,
    digest_json: str | Path,
    subject_repo_id: str,
    subject_head_sha: str,
    base_canonical_rev: str,
    proposed_by: str = "reconciler",
) -> Path:
    for field, value in {
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "base_canonical_rev": base_canonical_rev,
        "proposed_by": proposed_by,
    }.items():
        _require_nonblank(value, field)

    paths = TopologyPaths.from_root(root)
    digest = Digest.from_dict(load_json(digest_json))
    source_packet = paths.resolve(f"raw/packets/{digest.source_id}/packet.json")
    if not source_packet.exists():
        raise ReconcileError(f"source packet not found for digest: {digest.source_id}")

    known_nodes = Registry(root).known_node_ids()
    changes: list[dict[str, Any]] = []
    for claim in digest.author_claims:
        claim_id = new_id("clm")
        changes.append({
            "op": "create_claim",
            "claim_id": claim_id,
            "statement": claim_statement(claim),
            "source_ids": [digest.source_id],
            "digest_id": digest.id,
            "status": "draft",
        })

    for edge in digest.candidate_edges:
        target_id = edge["target_id"]
        confidence = edge["confidence"]
        if target_id != "NEW" and not is_valid_id(target_id, prefix="nd"):
            raise ReconcileError(f"candidate edge target_id must be NEW or an nd_ opaque topology ID: {target_id}")
        if target_id == "NEW":
            changes.append({
                "op": "propose_node",
                "node_id": new_id("nd"),
                "reason": edge["note"],
                "source_id": digest.source_id,
                "digest_id": digest.id,
            })
        elif target_id in known_nodes and confidence in {"high", "medium"}:
            changes.append({
                "op": "add_edge",
                "edge_id": new_id("edg"),
                "from_id": digest.source_id,
                "to_id": target_id,
                "edge_type": edge["edge_type"],
                "confidence": confidence,
                "note": edge["note"],
                "basis_digest_id": digest.id,
            })
        else:
            changes.append({
                "op": "open_gap",
                "gap_id": new_id("gap"),
                "target_id": target_id,
                "reason": "unknown target or insufficient confidence",
                "candidate_edge": edge,
                "digest_id": digest.id,
            })

    requires_human, gate_class = human_gate_for_edges(digest.candidate_edges)
    merge_confidence = "low" if any(change["op"] == "open_gap" for change in changes) else "medium"
    pack = MutationPack(
        schema_version="1.0",
        id=new_id("mut"),
        proposal_type="digest_reconcile",
        proposed_by=proposed_by,
        base_canonical_rev=base_canonical_rev,
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        changes=changes,
        evidence_refs=[digest.id, digest.source_id],
        requires_human=requires_human,
        human_gate_class=gate_class,
        merge_confidence=merge_confidence,
        metadata={"digest_id": digest.id, "source_id": digest.source_id},
    )
    output = paths.resolve(f"mutations/pending/{pack.id}.json")
    atomic_write_text(output, json.dumps(pack.to_dict(), indent=2, sort_keys=True) + "\n")
    return output
