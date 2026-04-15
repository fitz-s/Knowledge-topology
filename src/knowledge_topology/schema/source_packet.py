"""Source packet model and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from knowledge_topology.ids import is_valid_id


SOURCE_TYPES = {"local_draft", "github_artifact", "article_html", "pdf_arxiv", "video_platform"}
CONTENT_STATUSES = {"complete", "partial", "blocked", "paywalled", "missing"}
CONTENT_MODES = {"public_text", "excerpt_only", "local_blob"}
REDISTRIBUTABLE_VALUES = {"yes", "no", "unknown"}
INGEST_DEPTHS = {"deep", "standard", "scan"}


class SourcePacketError(ValueError):
    """Raised when a source packet violates the schema contract."""


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


@dataclass(frozen=True)
class SourceArtifact:
    kind: str
    path: str | None = None
    hash_sha256: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in {
            "kind": self.kind,
            "path": self.path,
            "hash_sha256": self.hash_sha256,
            "note": self.note,
        }.items() if value is not None}


@dataclass(frozen=True)
class FetchChainEntry:
    method: str
    status: str
    note: str

    def to_dict(self) -> dict[str, str]:
        return {"method": self.method, "status": self.status, "note": self.note}


@dataclass(frozen=True)
class LocalBlobRef:
    hash_sha256: str
    storage_hint: str
    byte_length: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"hash_sha256": self.hash_sha256, "storage_hint": self.storage_hint}
        if self.byte_length is not None:
            payload["byte_length"] = self.byte_length
        return payload


@dataclass(frozen=True)
class SourcePacket:
    schema_version: str
    id: str
    source_type: str
    original_url: str | None
    canonical_url: str | None
    retrieved_at: str
    curator_note: str
    ingest_depth: str
    authority: str
    trust_scope: str
    content_status: str
    content_mode: str
    redistributable: str
    hash_original: str | None
    hash_normalized: str | None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    fetch_chain: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        if self.schema_version != "1.0":
            raise SourcePacketError("unsupported source packet schema_version")
        if not is_valid_id(self.id, prefix="src"):
            raise SourcePacketError("source packet id must use src_ opaque ID")
        if self.source_type not in SOURCE_TYPES:
            raise SourcePacketError(f"unknown source_type: {self.source_type}")
        if self.content_status not in CONTENT_STATUSES:
            raise SourcePacketError(f"unknown content_status: {self.content_status}")
        if self.content_mode not in CONTENT_MODES:
            raise SourcePacketError(f"unknown content_mode: {self.content_mode}")
        if self.redistributable not in REDISTRIBUTABLE_VALUES:
            raise SourcePacketError(f"unknown redistributable value: {self.redistributable}")
        if self.ingest_depth not in INGEST_DEPTHS:
            raise SourcePacketError(f"unknown ingest_depth: {self.ingest_depth}")
        if _blank(self.original_url):
            raise SourcePacketError("original_url is required")
        if _blank(self.retrieved_at):
            raise SourcePacketError("retrieved_at is required")
        if _blank(self.curator_note):
            raise SourcePacketError("curator_note is required")
        if _blank(self.authority):
            raise SourcePacketError("authority is required")
        if _blank(self.trust_scope):
            raise SourcePacketError("trust_scope is required")
        if self.content_mode == "public_text" and self.redistributable != "yes":
            raise SourcePacketError("public_text requires redistributable=yes")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "source_type": self.source_type,
            "original_url": self.original_url,
            "canonical_url": self.canonical_url,
            "retrieved_at": self.retrieved_at,
            "curator_note": self.curator_note,
            "ingest_depth": self.ingest_depth,
            "authority": self.authority,
            "trust_scope": self.trust_scope,
            "content_status": self.content_status,
            "content_mode": self.content_mode,
            "redistributable": self.redistributable,
            "hash_original": self.hash_original,
            "hash_normalized": self.hash_normalized,
            "artifacts": self.artifacts,
            "fetch_chain": self.fetch_chain,
        }
