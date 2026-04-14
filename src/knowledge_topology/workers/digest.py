"""P3 digest validation and artifact writer."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from knowledge_topology.adapters.digest_model import DigestModelAdapter
from knowledge_topology.adapters.digest_model import DigestModelRequest
from knowledge_topology.ids import is_valid_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.digest import Digest, DigestError
from knowledge_topology.schema.loader import load_json
from knowledge_topology.schema.source_packet import SourcePacket
from knowledge_topology.storage.transaction import atomic_write_text


class DigestWorkerError(ValueError):
    """Raised when digest artifact creation is unsafe or invalid."""


MAX_REQUEST_SOURCE_TEXT = 8000
PACKET_METADATA_FIELDS = [
    "id",
    "source_type",
    "retrieved_at",
    "curator_note",
    "ingest_depth",
    "authority",
    "trust_scope",
    "content_status",
    "content_mode",
    "redistributable",
    "hash_original",
    "hash_normalized",
]
ARTIFACT_FIELDS = {
    "kind",
    "path",
    "hash_sha256",
    "note",
    "content_type",
    "status_code",
    "final_url",
    "byte_length",
    "arxiv_id",
    "abs_url",
    "pdf_url",
    "repo",
    "artifact_type",
    "number",
    "ref",
    "commit_sha",
    "mutable_ref",
    "raw_url",
}
SAFE_ARTIFACT_PATHS = {"content.md", "excerpt.md"}
SAFE_URL_FIELDS = {"final_url", "raw_url", "abs_url", "pdf_url"}
SAFE_TOKEN_FIELDS = {"repo", "ref", "path", "commit_sha", "number", "arxiv_id"}


def render_digest_markdown(digest: Digest, source_packet: dict[str, Any]) -> str:
    sections = [
        f"# Digest {digest.id}",
        "",
        f"- Source: `{digest.source_id}`",
        f"- Source type: `{source_packet.get('source_type')}`",
        f"- Content mode: `{source_packet.get('content_mode')}`",
        f"- Digest depth: `{digest.digest_depth}`",
        f"- Passes completed: `{', '.join(str(item) for item in digest.passes_completed)}`",
        "",
        "## Source Artifacts",
        json.dumps(source_packet.get("artifacts", []), indent=2, sort_keys=True),
        "",
        "## Author Claims",
        json.dumps(digest.author_claims, indent=2, sort_keys=True),
        "",
        "## Direct Evidence",
        json.dumps(digest.direct_evidence, indent=2, sort_keys=True),
        "",
        "## Model Inferences",
        json.dumps(digest.model_inferences, indent=2, sort_keys=True),
        "",
        "## Boundary Conditions",
        json.dumps(digest.boundary_conditions, indent=2, sort_keys=True),
        "",
        "## Alternative Interpretations",
        json.dumps(digest.alternative_interpretations, indent=2, sort_keys=True),
        "",
        "## Contested Points",
        json.dumps(digest.contested_points, indent=2, sort_keys=True),
        "",
        "## Unresolved Ambiguity",
        json.dumps(digest.unresolved_ambiguity, indent=2, sort_keys=True),
        "",
        "## Open Questions",
        json.dumps(digest.open_questions, indent=2, sort_keys=True),
        "",
        "## Candidate Edges",
        json.dumps(digest.candidate_edges, indent=2, sort_keys=True),
        "",
        "## Fidelity Flags",
        json.dumps(digest.fidelity_flags, indent=2, sort_keys=True),
        "",
    ]
    return "\n".join(sections)


def prompt_for_depth(root: Path, depth: str) -> str:
    prompt_name = "digest_deep.md" if depth == "deep" else "digest_standard.md"
    prompt_path = root / "prompts" / prompt_name
    if prompt_path.is_symlink() or not prompt_path.is_file():
        raise DigestWorkerError(f"digest prompt not found or unsafe: {prompt_name}")
    return prompt_path.read_text(encoding="utf-8")


def bounded_source_text(text: str) -> str:
    return text[:MAX_REQUEST_SOURCE_TEXT]


def safe_packet_text_file(packet_dir: Path, filename: str) -> str | None:
    if filename not in {"content.md", "excerpt.md"}:
        raise DigestWorkerError("unsupported source text filename")
    if packet_dir.is_symlink() or not packet_dir.is_dir():
        raise DigestWorkerError("source packet directory is unsafe")
    target = packet_dir / filename
    if not target.exists():
        return None
    if target.is_symlink() or not target.is_file():
        raise DigestWorkerError(f"source packet text file is unsafe: {filename}")
    resolved = target.resolve()
    packet_root = packet_dir.resolve()
    if resolved.parent != packet_root:
        raise DigestWorkerError("source packet text file escaped packet directory")
    return bounded_source_text(target.read_text(encoding="utf-8"))


def safe_source_packet_path(paths: TopologyPaths, source_id: str) -> Path:
    if not is_valid_id(source_id, prefix="src"):
        raise DigestWorkerError("source_id must use src_ opaque ID")
    raw_dir = paths.root / "raw"
    packets_dir = raw_dir / "packets"
    packet_dir = packets_dir / source_id
    packet_path = packet_dir / "packet.json"
    for directory in [raw_dir, packets_dir, packet_dir]:
        if directory.is_symlink() or not directory.is_dir():
            raise DigestWorkerError("source packet parent path is unsafe")
    if packet_path.is_symlink() or not packet_path.is_file():
        raise DigestWorkerError(f"source packet not found or unsafe: {source_id}")
    return packet_path


def sanitized_artifacts(source_packet: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = []
    for artifact in source_packet.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        sanitized: dict[str, Any] = {}
        for field in ARTIFACT_FIELDS:
            value = artifact.get(field)
            if isinstance(value, bool):
                sanitized[field] = value
                continue
            if isinstance(value, int):
                sanitized[field] = value
                continue
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                continue
            if not safe_artifact_string(field, value, artifact.get("kind")):
                continue
            sanitized[field] = " ".join(value.split())[:500]
        if sanitized:
            artifacts.append(sanitized)
    return artifacts


def safe_artifact_string(field: str, value: str, artifact_kind: Any) -> bool:
    lowered = value.casefold()
    if any(marker in lowered for marker in ("raw/local_blobs", "local_blobs", "private", "cache")):
        return False
    if field == "path":
        if value in SAFE_ARTIFACT_PATHS:
            return True
        if artifact_kind == "github_blob":
            return bool(re.fullmatch(r"[A-Za-z0-9_./@+-]+", value)) and ".." not in Path(value).parts
        return False
    if field in SAFE_URL_FIELDS:
        return value.startswith("http://") or value.startswith("https://")
    if field == "repo":
        return bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value))
    if field in SAFE_TOKEN_FIELDS:
        return bool(re.fullmatch(r"[A-Za-z0-9_./@+-]+", value))
    return True


def sanitized_packet_metadata(source_packet: dict[str, Any]) -> dict[str, Any]:
    metadata = {field: source_packet.get(field) for field in PACKET_METADATA_FIELDS if field in source_packet}
    metadata["artifacts"] = sanitized_artifacts(source_packet)
    return metadata


def build_digest_model_request(root: str | Path, source_id: str) -> DigestModelRequest:
    paths = TopologyPaths.from_root(root)
    source_packet_path = safe_source_packet_path(paths, source_id)
    source_packet = load_json(source_packet_path)
    packet = SourcePacket(**source_packet)
    packet.validate()
    if packet.id != source_id:
        raise DigestWorkerError("source packet id does not match requested source")

    packet_dir = source_packet_path.parent
    source_text: str | None = None
    source_text_kind: str | None = None
    if packet.content_mode == "public_text":
        source_text = safe_packet_text_file(packet_dir, "content.md")
        source_text_kind = "content.md" if source_text is not None else None
    elif packet.content_mode == "excerpt_only":
        source_text = safe_packet_text_file(packet_dir, "excerpt.md")
        source_text_kind = "excerpt.md" if source_text is not None else None

    prompt = prompt_for_depth(paths.root, packet.ingest_depth)
    return DigestModelRequest(
        source_id=source_id,
        digest_depth=packet.ingest_depth,
        prompt=prompt,
        source_packet=sanitized_packet_metadata(source_packet),
        source_text=source_text,
        source_text_kind=source_text_kind,
    )


def write_digest_artifacts(
    root: str | Path,
    *,
    source_id: str,
    model_adapter: DigestModelAdapter,
) -> tuple[Path, Path]:
    paths = TopologyPaths.from_root(root)
    source_packet_path = paths.resolve(f"raw/packets/{source_id}/packet.json")
    if not source_packet_path.exists():
        raise DigestWorkerError(f"source packet not found: {source_id}")
    source_packet = load_json(source_packet_path)
    packet = SourcePacket(**source_packet)
    packet.validate()
    if packet.id != source_id:
        raise DigestWorkerError("source packet id does not match requested source")
    payload = model_adapter.load_output()
    digest = Digest.from_dict(payload)
    if digest.source_id != source_id:
        raise DigestError("digest source_id does not match requested source")

    digest_dir = paths.ensure_dir(f"digests/by_source/{source_id}")
    lock_dir = digest_dir / ".digest-write.lock"
    try:
        os.mkdir(lock_dir)
    except FileExistsError as exc:
        raise DigestWorkerError(f"digest artifact write already in progress for source: {source_id}") from exc
    try:
        if any(digest_dir.glob("*.json")):
            raise DigestWorkerError(f"digest artifact already exists for source: {source_id}")
        return write_digest_artifacts_locked(digest, digest_dir, source_packet)
    finally:
        lock_dir.rmdir()


def write_digest_artifacts_locked(digest: Digest, digest_dir: Path, source_packet: dict[str, Any]) -> tuple[Path, Path]:
    json_path = digest_dir / f"{digest.id}.json"
    md_path = digest_dir / f"{digest.id}.md"
    if json_path.exists() or md_path.exists():
        raise DigestWorkerError(f"digest artifact already exists: {digest.id}")
    atomic_write_text(json_path, json.dumps(digest.to_dict(), indent=2, sort_keys=True) + "\n")
    atomic_write_text(md_path, render_digest_markdown(digest, source_packet))
    return json_path, md_path
