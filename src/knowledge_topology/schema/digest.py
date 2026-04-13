"""Digest schema and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from knowledge_topology.ids import is_valid_id


DIGEST_DEPTHS = {"deep", "standard", "scan"}
EDGE_TYPES = {
    "SUPPORTS",
    "CONTRADICTS",
    "NARROWS",
    "SUPERSEDES",
    "RELATED_TO",
    "EXAMPLE_OF",
    "IMPLEMENTS",
    "DEPENDS_ON",
    "INVARIANT_FOR",
    "DIVERGES_FROM",
    "READS",
    "WRITES",
    "TESTS",
    "LOCATED_IN",
}
FLAG_VALUES = {"yes", "partial", "no"}
REQUIRED_FIDELITY_FLAGS = {
    "reasoning_chain_preserved",
    "boundary_conditions_preserved",
    "alternative_interpretations_preserved",
    "hidden_assumptions_extracted",
    "evidence_strength_graded",
}
REQUIRED_CANDIDATE_EDGE_FIELDS = {"target_id", "edge_type", "confidence", "note"}


class DigestError(ValueError):
    """Raised when digest output violates the schema contract."""


@dataclass(frozen=True)
class Digest:
    schema_version: str
    id: str
    source_id: str
    digest_depth: str
    passes_completed: list[int]
    author_claims: list[Any] = field(default_factory=list)
    direct_evidence: list[Any] = field(default_factory=list)
    model_inferences: list[Any] = field(default_factory=list)
    boundary_conditions: list[Any] = field(default_factory=list)
    alternative_interpretations: list[Any] = field(default_factory=list)
    contested_points: list[Any] = field(default_factory=list)
    unresolved_ambiguity: list[Any] = field(default_factory=list)
    open_questions: list[Any] = field(default_factory=list)
    candidate_edges: list[dict[str, Any]] = field(default_factory=list)
    fidelity_flags: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Digest":
        required = [
            "schema_version",
            "id",
            "source_id",
            "digest_depth",
            "passes_completed",
            "author_claims",
            "direct_evidence",
            "model_inferences",
            "boundary_conditions",
            "alternative_interpretations",
            "contested_points",
            "unresolved_ambiguity",
            "open_questions",
            "candidate_edges",
            "fidelity_flags",
        ]
        missing = [field_name for field_name in required if field_name not in payload]
        if missing:
            raise DigestError(f"missing digest fields: {', '.join(missing)}")
        digest = cls(**{field_name: payload[field_name] for field_name in required})
        digest.validate()
        return digest

    def validate(self) -> None:
        if self.schema_version != "1.0":
            raise DigestError("unsupported digest schema_version")
        if not is_valid_id(self.id, prefix="dg"):
            raise DigestError("digest id must use dg_ opaque ID")
        if not is_valid_id(self.source_id, prefix="src"):
            raise DigestError("source_id must use src_ opaque ID")
        if self.digest_depth not in DIGEST_DEPTHS:
            raise DigestError(f"unknown digest_depth: {self.digest_depth}")
        if not self.passes_completed or not all(pass_number in {1, 2, 3, 4} for pass_number in self.passes_completed):
            raise DigestError("passes_completed must contain pass numbers 1-4")
        for name in [
            "author_claims",
            "direct_evidence",
            "model_inferences",
            "boundary_conditions",
            "alternative_interpretations",
            "contested_points",
            "unresolved_ambiguity",
            "open_questions",
            "candidate_edges",
        ]:
            if not isinstance(getattr(self, name), list):
                raise DigestError(f"{name} must be a list")
        missing_flags = REQUIRED_FIDELITY_FLAGS - set(self.fidelity_flags)
        if missing_flags:
            raise DigestError(f"missing fidelity flags: {', '.join(sorted(missing_flags))}")
        for key, value in self.fidelity_flags.items():
            if value not in FLAG_VALUES:
                raise DigestError(f"invalid fidelity flag {key}: {value}")
        for edge in self.candidate_edges:
            if not isinstance(edge, dict):
                raise DigestError("candidate_edges entries must be objects")
            missing = REQUIRED_CANDIDATE_EDGE_FIELDS - set(edge)
            if missing:
                raise DigestError(f"candidate edge missing fields: {', '.join(sorted(missing))}")
            edge_type = edge["edge_type"]
            if edge_type not in EDGE_TYPES:
                raise DigestError(f"invalid candidate edge_type: {edge_type}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "source_id": self.source_id,
            "digest_depth": self.digest_depth,
            "passes_completed": self.passes_completed,
            "author_claims": self.author_claims,
            "direct_evidence": self.direct_evidence,
            "model_inferences": self.model_inferences,
            "boundary_conditions": self.boundary_conditions,
            "alternative_interpretations": self.alternative_interpretations,
            "contested_points": self.contested_points,
            "unresolved_ambiguity": self.unresolved_ambiguity,
            "open_questions": self.open_questions,
            "candidate_edges": self.candidate_edges,
            "fidelity_flags": self.fidelity_flags,
        }
