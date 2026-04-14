"""Mutation pack schema and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from knowledge_topology.ids import is_valid_id


PROPOSAL_TYPES = {"digest_reconcile", "session_writeback"}
MERGE_CONFIDENCE = {"high", "medium", "low"}
HUMAN_GATE_CLASSES = {
    "source_ambiguity",
    "high_impact_contradiction",
    "fitz_belief",
    "operator_directive",
    "supersede_delete",
    "cross_scope_upgrade",
    "weak_evidence_merge",
}
CHANGE_OPS = {"create_claim", "add_edge", "open_gap", "propose_node"}


class MutationPackError(ValueError):
    """Raised when a mutation pack violates the contract."""


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _require(change: dict[str, Any], fields: set[str]) -> None:
    missing = fields - set(change)
    if missing:
        raise MutationPackError(f"{change.get('op')} missing fields: {', '.join(sorted(missing))}")


def _require_id(value: Any, prefix: str, field: str) -> None:
    if not isinstance(value, str) or not is_valid_id(value, prefix=prefix):
        raise MutationPackError(f"{field} must use {prefix}_ opaque ID")


@dataclass(frozen=True)
class MutationPack:
    schema_version: str
    id: str
    proposal_type: str
    proposed_by: str
    base_canonical_rev: str
    subject_repo_id: str
    subject_head_sha: str
    changes: list[dict[str, Any]]
    evidence_refs: list[str]
    requires_human: bool
    human_gate_class: str | None
    merge_confidence: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.schema_version != "1.0":
            raise MutationPackError("unsupported mutation pack schema_version")
        if not is_valid_id(self.id, prefix="mut"):
            raise MutationPackError("mutation pack id must use mut_ opaque ID")
        if self.proposal_type not in PROPOSAL_TYPES:
            raise MutationPackError(f"unknown proposal_type: {self.proposal_type}")
        for field_name in ["proposed_by", "base_canonical_rev", "subject_repo_id", "subject_head_sha"]:
            if _blank(getattr(self, field_name)):
                raise MutationPackError(f"{field_name} is required")
        if not self.changes:
            raise MutationPackError("changes are required")
        if not self.evidence_refs:
            raise MutationPackError("evidence_refs are required")
        if self.merge_confidence not in MERGE_CONFIDENCE:
            raise MutationPackError(f"unknown merge_confidence: {self.merge_confidence}")
        if self.requires_human:
            if self.human_gate_class not in HUMAN_GATE_CLASSES:
                raise MutationPackError("requires_human mutation packs need a valid human_gate_class")
        elif self.human_gate_class is not None:
            raise MutationPackError("human_gate_class must be null when requires_human is false")
        for change in self.changes:
            op = change.get("op")
            if op not in CHANGE_OPS:
                raise MutationPackError(f"unknown mutation change op: {op}")
            if op == "create_claim":
                _require(change, {"claim_id", "statement", "source_ids", "digest_id", "status"})
                _require_id(change["claim_id"], "clm", "claim_id")
                _require_id(change["digest_id"], "dg", "digest_id")
                for source_id in change["source_ids"]:
                    _require_id(source_id, "src", "source_id")
            elif op == "add_edge":
                _require(change, {"edge_id", "from_id", "to_id", "edge_type", "confidence", "note", "basis_digest_id"})
                _require_id(change["edge_id"], "edg", "edge_id")
                _require_id(change["from_id"], "src", "from_id")
                _require_id(change["to_id"], "nd", "to_id")
                _require_id(change["basis_digest_id"], "dg", "basis_digest_id")
            elif op == "open_gap":
                _require(change, {"gap_id", "target_id", "reason", "candidate_edge", "digest_id"})
                _require_id(change["gap_id"], "gap", "gap_id")
                _require_id(change["digest_id"], "dg", "digest_id")
                target_id = change["target_id"]
                if target_id != "NEW":
                    _require_id(target_id, "nd", "target_id")
            elif op == "propose_node":
                _require(change, {"node_id", "reason", "source_id", "digest_id"})
                _require_id(change["node_id"], "nd", "node_id")
                _require_id(change["source_id"], "src", "source_id")
                _require_id(change["digest_id"], "dg", "digest_id")
        for evidence_ref in self.evidence_refs:
            if not isinstance(evidence_ref, str) or "_" not in evidence_ref:
                raise MutationPackError("evidence_refs must contain opaque IDs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "proposal_type": self.proposal_type,
            "proposed_by": self.proposed_by,
            "base_canonical_rev": self.base_canonical_rev,
            "subject_repo_id": self.subject_repo_id,
            "subject_head_sha": self.subject_head_sha,
            "changes": self.changes,
            "evidence_refs": self.evidence_refs,
            "requires_human": self.requires_human,
            "human_gate_class": self.human_gate_class,
            "merge_confidence": self.merge_confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MutationPack":
        required = [
            "schema_version",
            "id",
            "proposal_type",
            "proposed_by",
            "base_canonical_rev",
            "subject_repo_id",
            "subject_head_sha",
            "changes",
            "evidence_refs",
            "requires_human",
            "human_gate_class",
            "merge_confidence",
        ]
        missing = [field_name for field_name in required if field_name not in payload]
        if missing:
            raise MutationPackError(f"missing mutation pack fields: {', '.join(missing)}")
        pack = cls(**{field_name: payload[field_name] for field_name in required}, metadata=payload.get("metadata", {}))
        pack.validate()
        return pack
