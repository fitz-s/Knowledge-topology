"""P2 source packet and fetch worker."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from knowledge_topology.ids import new_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.source_packet import FetchChainEntry, SourceArtifact, SourcePacket
from knowledge_topology.storage.spool import create_job
from knowledge_topology.storage.transaction import atomic_write_text


class FetchError(ValueError):
    """Raised when a source cannot be represented safely."""


@dataclass(frozen=True)
class IngestResult:
    packet_id: str
    packet_path: Path
    digest_job_path: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_source(value: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        if "github.com" in host:
            return "github_artifact"
        if "arxiv.org" in host or path.endswith(".pdf"):
            return "pdf_arxiv"
        return "article_html"
    suffix = Path(value).suffix.lower()
    if suffix == ".pdf":
        return "pdf_arxiv"
    return "local_draft"


def default_content_mode(source_type: str, redistributable: str) -> str:
    if source_type == "local_draft" and redistributable == "yes":
        return "public_text"
    if source_type == "pdf_arxiv":
        return "excerpt_only"
    return "excerpt_only"


def canonicalize_source(value: str, source_type: str) -> tuple[str | None, str | None]:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return value, value
    return str(Path(value).expanduser()), None


def _safe_excerpt(text: str, limit: int = 800) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def build_source_packet(
    value: str,
    *,
    note: str,
    depth: str,
    redistributable: str = "unknown",
    content_mode: str | None = None,
    source_type: str | None = None,
) -> tuple[SourcePacket, dict[str, str]]:
    resolved_type = classify_source(value, source_type)
    mode = content_mode or default_content_mode(resolved_type, redistributable)
    original_url, canonical_url = canonicalize_source(value, resolved_type)
    packet_id = new_id("src")
    artifacts: list[dict[str, str]] = []
    fetch_chain = [FetchChainEntry(method="metadata_only", status="partial", note="P2 does not perform network fetch").to_dict()]
    hash_original: str | None = None
    hash_normalized: str | None = None
    files: dict[str, str] = {}
    content_status = "partial"

    if resolved_type == "local_draft":
        path = Path(value).expanduser()
        if not path.exists() or not path.is_file():
            raise FetchError(f"local draft not found: {value}")
        text = path.read_text(encoding="utf-8")
        hash_original = sha256_text(text)
        if mode == "public_text":
            hash_normalized = sha256_text(text)
            files["content.md"] = text
            artifacts.append(SourceArtifact(kind="normalized_text", path="content.md", hash_sha256=hash_normalized).to_dict())
        else:
            excerpt = _safe_excerpt(text)
            hash_normalized = sha256_text(excerpt)
            files["excerpt.md"] = excerpt + "\n"
            artifacts.append(SourceArtifact(kind="excerpt", path="excerpt.md", hash_sha256=hash_normalized).to_dict())
        fetch_chain = [FetchChainEntry(method="local_file", status="complete", note="Read local draft from disk").to_dict()]
        content_status = "complete"
    elif resolved_type == "pdf_arxiv":
        artifacts.append(SourceArtifact(kind="manifest", note="PDF/arXiv fetch deferred; store safe metadata only").to_dict())
        if mode == "local_blob":
            artifacts.append(SourceArtifact(kind="local_blob_ref", note="Full binary content must stay outside Git").to_dict())
    elif resolved_type == "github_artifact":
        artifacts.append(SourceArtifact(kind="manifest", note="GitHub artifact must be pinned by commit/ref before authority use").to_dict())
    else:
        artifacts.append(SourceArtifact(kind="manifest", note="Article fetch deferred; excerpt_only default").to_dict())

    packet = SourcePacket(
        schema_version="1.0",
        id=packet_id,
        source_type=resolved_type,
        original_url=original_url,
        canonical_url=canonical_url,
        retrieved_at=utc_now_iso(),
        curator_note=note,
        ingest_depth=depth,
        authority="source_grounded",
        trust_scope="external" if resolved_type != "local_draft" else "operator",
        content_status=content_status,
        content_mode=mode,
        redistributable=redistributable,
        hash_original=hash_original,
        hash_normalized=hash_normalized,
        artifacts=artifacts,
        fetch_chain=fetch_chain,
    )
    packet.validate()
    return packet, files


def ingest_source(
    root: str | Path,
    value: str,
    *,
    note: str,
    depth: str,
    audience: str,
    subject_repo_id: str,
    subject_head_sha: str,
    base_canonical_rev: str,
    redistributable: str = "unknown",
    content_mode: str | None = None,
    source_type: str | None = None,
) -> IngestResult:
    paths = TopologyPaths.from_root(root)
    packet, files = build_source_packet(
        value,
        note=note,
        depth=depth,
        redistributable=redistributable,
        content_mode=content_mode,
        source_type=source_type,
    )
    packet_dir = paths.ensure_dir(f"raw/packets/{packet.id}")
    for relative, text in files.items():
        atomic_write_text(packet_dir / relative, text)
    atomic_write_text(packet_dir / "packet.json", json.dumps(packet.to_dict(), indent=2, sort_keys=True) + "\n")
    digest_job = create_job(
        root,
        "digest",
        payload={"source_id": packet.id, "audience": audience},
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        base_canonical_rev=base_canonical_rev,
        created_by="reader",
    )
    return IngestResult(packet.id, packet_dir / "packet.json", digest_job)
