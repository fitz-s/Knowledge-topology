"""P12.2 operator-facing video/media workflow."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.source_packet import SourcePacket
from knowledge_topology.storage.spool import create_job
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.workers.fetch import FetchError
from knowledge_topology.workers.fetch import TEXT_VIDEO_ARTIFACT_KINDS
from knowledge_topology.workers.fetch import build_source_packet
from knowledge_topology.workers.fetch import read_packet


class VideoWorkflowError(ValueError):
    """Raised when video workflow state is unsafe or incomplete."""


REQUIRED_TEXT_ARTIFACTS = ["transcript", "key_frames", "audio_summary"]
OPTIONAL_ARTIFACTS = ["video_file", "landing_page_metadata"]
TEXT_ARTIFACT_PATHS = {"transcript.md", "key_frames.md", "audio_summary.md", "landing_page_metadata.md"}
PROVIDERS = {"manual-upload", "youtube", "yt-dlp", "browser-capture"}
TRANSCRIBERS = {"none", "whisper", "provider"}
VISION_PROVIDERS = {"none", "gemini", "openai"}
DEEP_READY_ORIGINS = {
    "transcript": {"platform_caption", "audio_transcription", "human_transcript"},
    "key_frames": {"frame_extraction", "vision_frame_analysis", "human_frame_notes"},
    "audio_summary": {"audio_model_summary", "human_audio_summary"},
}
SHALLOW_ONLY_ORIGINS = {"page_visible_excerpt", "page_visible_chapter_list", "inferred_from_page", "legacy_unknown"}
PROVIDER_ATTESTED_ORIGINS = {"platform_caption", "audio_transcription", "frame_extraction", "vision_frame_analysis", "audio_model_summary"}
HUMAN_ATTESTED_ORIGINS = {"human_transcript", "human_frame_notes", "human_audio_summary"}
SHALLOW_CONTENT_MARKERS = (
    "page-visible",
    "page visible",
    "visible page",
    "visible description",
    "chapter list",
    "chapter structure",
    "not a full audio transcript",
    "not from a full transcript",
    "inferred from the visible page",
    "inferred from page",
    "not from audio",
)


@dataclass(frozen=True)
class VideoIngestResult:
    packet_id: str
    packet_path: Path
    status: dict[str, Any]
    digest_job_path: Path | None


def video_status(root: str | Path, source_id: str) -> dict[str, Any]:
    paths = TopologyPaths.from_root(root)
    packet_path, packet = read_packet(paths, source_id)
    if packet.source_type != "video_platform":
        raise VideoWorkflowError("source packet is not video_platform")
    present = set()
    text_ready = set()
    deep_ready = set()
    shallow_only: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    local_blob_bytes = 0
    for artifact in packet.artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_kind = artifact.get("artifact_kind")
        if isinstance(artifact_kind, str):
            present.add(artifact_kind)
            if artifact.get("kind") == "video_text_artifact" and video_text_artifact_readable(packet_path.parent, artifact):
                text_ready.add(artifact_kind)
                if video_text_deep_ready(packet_path.parent, artifact_kind, artifact):
                    deep_ready.add(artifact_kind)
                elif artifact_kind in REQUIRED_TEXT_ARTIFACTS:
                    reason = shallow_artifact_reason(packet_path.parent, artifact_kind, artifact)
                    rejected.append({"artifact_kind": artifact_kind, "reason": reason})
                    shallow_only.append({
                        "artifact_kind": artifact_kind,
                        "evidence_origin": artifact.get("evidence_origin", "legacy_unknown"),
                        "coverage": artifact.get("coverage", "legacy_unknown"),
                        "modality": artifact.get("modality", "legacy_unknown"),
                    })
        if artifact.get("kind") == "local_blob_ref" and isinstance(artifact.get("byte_length"), int):
            local_blob_bytes += artifact["byte_length"]
    missing = [kind for kind in REQUIRED_TEXT_ARTIFACTS if kind not in deep_ready]
    optional_missing = [kind for kind in OPTIONAL_ARTIFACTS if kind not in present]
    ready = not missing
    return {
        "source_id": packet.id,
        "packet_path": str(packet_path.relative_to(paths.root)),
        "ready_for_deep_digest": ready,
        "present_artifacts": sorted(present),
        "text_ready_artifacts": sorted(text_ready),
        "deep_ready_artifacts": sorted(deep_ready),
        "shallow_only_artifacts": shallow_only,
        "rejected_for_deep_digest": rejected,
        "missing_required_artifacts": missing,
        "missing_optional_artifacts": optional_missing,
        "local_blob_bytes": local_blob_bytes,
        "next_actions": missing_actions(missing),
    }


def video_artifact_deep_ready(artifact_kind: str, artifact: dict[str, Any]) -> bool:
    allowed = DEEP_READY_ORIGINS.get(artifact_kind)
    if allowed is None:
        return False
    origin = artifact.get("evidence_origin", "legacy_unknown")
    coverage = artifact.get("coverage", "legacy_unknown")
    modality = artifact.get("modality", "legacy_unknown")
    attestation = artifact.get("evidence_attestation", "legacy_unknown")
    if origin not in allowed:
        return False
    if origin in PROVIDER_ATTESTED_ORIGINS and attestation != "provider_generated":
        return False
    if origin in HUMAN_ATTESTED_ORIGINS and attestation != "operator_attested":
        return False
    manifest_hash = artifact.get("attestation_manifest_hash")
    if attestation in {"operator_attested", "provider_generated"} and not (isinstance(manifest_hash, str) and manifest_hash.startswith("sha256:")):
        return False
    if coverage in {"page_visible_only", "chapter_only", "legacy_unknown"}:
        return False
    if modality == "page" or modality == "legacy_unknown":
        return False
    return True


def text_contains_shallow_markers(text: str) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in SHALLOW_CONTENT_MARKERS)


def video_text_deep_ready(packet_dir: Path, artifact_kind: str, artifact: dict[str, Any]) -> bool:
    if not video_artifact_deep_ready(artifact_kind, artifact):
        return False
    path = artifact.get("path")
    if not isinstance(path, str):
        return False
    target = packet_dir / path
    return not text_contains_shallow_markers(target.read_text(encoding="utf-8", errors="replace"))


def shallow_artifact_reason(packet_dir: Path, artifact_kind: str, artifact: dict[str, Any]) -> str:
    origin = artifact.get("evidence_origin", "legacy_unknown")
    coverage = artifact.get("coverage", "legacy_unknown")
    modality = artifact.get("modality", "legacy_unknown")
    attestation = artifact.get("evidence_attestation", "legacy_unknown")
    if origin in SHALLOW_ONLY_ORIGINS:
        return f"{origin} cannot satisfy {artifact_kind} evidence"
    if origin in PROVIDER_ATTESTED_ORIGINS and attestation != "provider_generated":
        return f"{origin} requires provider_generated attestation"
    if origin in HUMAN_ATTESTED_ORIGINS and attestation != "operator_attested":
        return f"{origin} requires operator_attested attestation"
    if attestation in {"operator_attested", "provider_generated"} and not isinstance(artifact.get("attestation_manifest_hash"), str):
        return f"{artifact_kind} requires external attestation manifest"
    if coverage in {"page_visible_only", "chapter_only", "legacy_unknown"}:
        return f"{coverage} coverage cannot satisfy {artifact_kind} evidence"
    if modality in {"page", "legacy_unknown"}:
        return f"{modality} modality cannot satisfy {artifact_kind} evidence"
    path = artifact.get("path")
    if isinstance(path, str):
        target = packet_dir / path
        if target.exists() and not target.is_symlink() and text_contains_shallow_markers(target.read_text(encoding="utf-8", errors="replace")):
            return f"{artifact_kind} text contains page-visible or inferred-content markers"
    return f"{artifact_kind} artifact lacks accepted deep evidence provenance"


def video_text_artifact_readable(packet_dir: Path, artifact: dict[str, Any]) -> bool:
    path = artifact.get("path")
    if not isinstance(path, str) or path not in TEXT_ARTIFACT_PATHS:
        return False
    target = packet_dir / path
    if target.is_symlink() or not target.is_file():
        return False
    return target.parent.resolve() == packet_dir.resolve()


def missing_actions(missing: list[str]) -> list[str]:
    actions = []
    for kind in missing:
        if kind == "transcript":
            actions.append("attach transcript text with topology video attach-artifact --artifact-kind transcript --track-text")
        elif kind == "key_frames":
            actions.append("attach key-frame descriptions with topology video attach-artifact --artifact-kind key_frames --track-text")
        elif kind == "audio_summary":
            actions.append("attach audio summary with topology video attach-artifact --artifact-kind audio_summary --track-text")
    return actions


def prepare_digest(root: str | Path, source_id: str, *, allow_locator_only: bool = False) -> dict[str, Any]:
    status = video_status(root, source_id)
    if status["ready_for_deep_digest"]:
        return {**status, "digest_ready": True, "deep_digest_ready": True, "locator_digest_allowed": False, "shallow_risk": False}
    if allow_locator_only:
        return {**status, "digest_ready": False, "deep_digest_ready": False, "locator_digest_allowed": True, "shallow_risk": True}
    return {**status, "digest_ready": False, "deep_digest_ready": False, "locator_digest_allowed": False, "shallow_risk": True}


def video_trace(root: str | Path, source_id: str) -> dict[str, Any]:
    paths = TopologyPaths.from_root(root)
    packet_path, _ = read_packet(paths, source_id)
    status = video_status(root, source_id)
    digest_paths = sorted(paths.resolve(f"digests/by_source/{source_id}").glob("dg_*.json"))
    mutation_paths = []
    for path in sorted(paths.resolve("mutations/pending").glob("mut_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if source_id in payload.get("evidence_refs", []) or payload.get("metadata", {}).get("source_id") == source_id:
            mutation_paths.append(path)
    if mutation_paths:
        stage = "reconciled"
    elif digest_paths:
        stage = "digested"
    elif status["ready_for_deep_digest"]:
        stage = "deep_ready"
    elif status["present_artifacts"]:
        stage = "shallow_evidence"
    else:
        stage = "locator_only"
    return {
        "source_id": source_id,
        "stage": stage,
        "packet": str(packet_path.relative_to(paths.root)),
        "digest_paths": [str(path.relative_to(paths.root)) for path in digest_paths],
        "mutation_paths": [str(path.relative_to(paths.root)) for path in mutation_paths],
        "blocking_reasons": [item["reason"] for item in status["rejected_for_deep_digest"]] + status["next_actions"],
        "ready_for_deep_digest": status["ready_for_deep_digest"],
    }


def provider_status(provider: str, transcriber: str, vision_provider: str) -> list[dict[str, Any]]:
    messages = []
    if provider not in PROVIDERS:
        raise VideoWorkflowError("unsupported video provider")
    if transcriber not in TRANSCRIBERS:
        raise VideoWorkflowError("unsupported transcriber")
    if vision_provider not in VISION_PROVIDERS:
        raise VideoWorkflowError("unsupported vision provider")
    if provider == "manual-upload":
        messages.append({"provider": provider, "status": "manual_required", "note": "manual-upload creates locator and checklist only"})
    elif provider in {"youtube", "yt-dlp"}:
        if shutil.which("yt-dlp") is None:
            messages.append({"provider": provider, "status": "unavailable", "note": "yt-dlp executable not found"})
        else:
            messages.append({"provider": provider, "status": "not_implemented", "note": "automatic provider execution is deferred"})
    elif provider == "browser-capture":
        messages.append({"provider": provider, "status": "manual_required", "note": "browser capture requires operator action"})
    if transcriber != "none":
        messages.append({"provider": transcriber, "status": "not_implemented", "note": "transcriber adapter is deferred"})
    if vision_provider != "none":
        messages.append({"provider": vision_provider, "status": "not_implemented", "note": "vision adapter is deferred"})
    return messages


def write_video_locator_packet(
    root: str | Path,
    url: str,
    *,
    note: str,
    depth: str,
    redistributable: str,
) -> tuple[str, Path]:
    paths = TopologyPaths.from_root(root)
    packet, files = build_source_packet(
        url,
        note=note,
        depth=depth,
        redistributable=redistributable,
        content_mode="excerpt_only",
        source_type="video_platform",
        topology_root=paths.root,
        fetcher=None,
    )
    packet_dir = paths.ensure_dir(f"raw/packets/{packet.id}")
    for relative, text in files.items():
        atomic_write_text(packet_dir / relative, text)
    atomic_write_text(packet_dir / "packet.json", json.dumps(packet.to_dict(), indent=2, sort_keys=True) + "\n")
    return packet.id, packet_dir / "packet.json"


def video_ingest(
    root: str | Path,
    url: str,
    *,
    note: str,
    depth: str,
    audience: str,
    subject_repo_id: str,
    subject_head_sha: str,
    base_canonical_rev: str,
    provider: str,
    transcriber: str,
    vision_provider: str,
    auto_digest: bool = False,
    redistributable: str = "unknown",
) -> VideoIngestResult:
    packet_id, packet_path = write_video_locator_packet(
        root,
        url,
        note=note,
        depth=depth,
        redistributable=redistributable,
    )
    provider_messages = provider_status(provider, transcriber, vision_provider)
    status = video_status(root, packet_id)
    status["provider_results"] = provider_messages
    digest_job_path = None
    if auto_digest:
        prepared = prepare_digest(root, packet_id)
        status["auto_digest"] = prepared
        if prepared["digest_ready"] and not prepared["shallow_risk"]:
            digest_job_path = create_job(
                root,
                "digest",
                payload={"source_id": packet_id, "audience": audience},
                subject_repo_id=subject_repo_id,
                subject_head_sha=subject_head_sha,
                base_canonical_rev=base_canonical_rev,
                created_by="video-ingest",
            )
        else:
            status["digest_job_skipped"] = True
    return VideoIngestResult(packet_id=packet_id, packet_path=packet_path, status=status, digest_job_path=digest_job_path)
