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
    local_blob_bytes = 0
    for artifact in packet.artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_kind = artifact.get("artifact_kind")
        if isinstance(artifact_kind, str):
            present.add(artifact_kind)
            if artifact.get("kind") == "video_text_artifact" and video_text_artifact_readable(packet_path.parent, artifact):
                text_ready.add(artifact_kind)
        if artifact.get("kind") == "local_blob_ref" and isinstance(artifact.get("byte_length"), int):
            local_blob_bytes += artifact["byte_length"]
    missing = [kind for kind in REQUIRED_TEXT_ARTIFACTS if kind not in text_ready]
    optional_missing = [kind for kind in OPTIONAL_ARTIFACTS if kind not in present]
    ready = not missing
    return {
        "source_id": packet.id,
        "packet_path": str(packet_path),
        "ready_for_deep_digest": ready,
        "present_artifacts": sorted(present),
        "text_ready_artifacts": sorted(text_ready),
        "missing_required_artifacts": missing,
        "missing_optional_artifacts": optional_missing,
        "local_blob_bytes": local_blob_bytes,
        "next_actions": missing_actions(missing),
    }


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
        return {**status, "digest_ready": True, "shallow_risk": False}
    if allow_locator_only:
        return {**status, "digest_ready": True, "shallow_risk": True}
    return {**status, "digest_ready": False, "shallow_risk": True}


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
