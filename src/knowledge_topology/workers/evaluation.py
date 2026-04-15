"""P12.5 deterministic evaluation reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_topology.git_state import read_git_state
from knowledge_topology.ids import new_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.loader import load_json
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.subjects import SubjectRegistryError, subject_projection_authority


class EvaluationError(ValueError):
    """Raised when evaluation inputs are invalid."""


@dataclass(frozen=True)
class EvaluationResult:
    report_path: Path
    payload: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def display_path(paths: TopologyPaths, path: str | Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return str(candidate)
    try:
        return str(candidate.resolve().relative_to(paths.root))
    except ValueError:
        return candidate.name


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def current_revisions(root: Path, subject_repo_id: str | None) -> tuple[str | None, str | None]:
    topology_state = read_git_state(root)
    canonical_rev = topology_state.head_sha
    subject_head = None
    if subject_repo_id is not None:
        try:
            _, _, subject_head = subject_projection_authority(root, subject_repo_id)
        except SubjectRegistryError:
            subject_head = None
    return canonical_rev, subject_head


def builder_pack_metrics(paths: TopologyPaths, *, canonical_rev: str | None, subject_repo_id: str | None, subject_head_sha: str | None) -> dict[str, Any]:
    packs = []
    stale = 0
    for metadata_path in sorted((paths.root / "projections/tasks").glob("*/metadata.json")):
        try:
            metadata = load_json(metadata_path)
        except Exception:
            continue
        task_dir = metadata_path.parent
        size = sum(path.stat().st_size for path in task_dir.glob("*") if path.is_file())
        is_stale = False
        if canonical_rev is not None and metadata.get("canonical_rev") != canonical_rev:
            is_stale = True
        if subject_repo_id is not None and metadata.get("subject_repo_id") != subject_repo_id:
            is_stale = True
        if subject_head_sha is not None and metadata.get("subject_head_sha") != subject_head_sha:
            is_stale = True
        stale += int(is_stale)
        packs.append({
            "task_id": metadata.get("task_id"),
            "path": display_path(paths, task_dir),
            "size_bytes": size,
            "stale": is_stale,
        })
    return {
        "count": len(packs),
        "stale_count": stale,
        "stale_rate": ratio(stale, len(packs)),
        "size_bytes": {
            "total": sum(item["size_bytes"] for item in packs),
            "max": max((item["size_bytes"] for item in packs), default=0),
        },
        "packs": packs,
    }


def mutation_files(paths: TopologyPaths, folder: str) -> list[Path]:
    return sorted(paths.resolve(folder).glob("mut_*.json"))


def mutation_payloads(paths: TopologyPaths, folder: str) -> list[dict[str, Any]]:
    payloads = []
    for path in mutation_files(paths, folder):
        try:
            payload = load_json(path)
        except Exception:
            continue
        payload["_path"] = display_path(paths, path)
        payloads.append(payload)
    return payloads


def mutation_metrics(paths: TopologyPaths, *, canonical_rev: str | None, subject_repo_id: str | None, subject_head_sha: str | None) -> dict[str, Any]:
    pending = mutation_payloads(paths, "mutations/pending")
    applied = mutation_payloads(paths, "mutations/applied")
    rejected = mutation_payloads(paths, "mutations/rejected")
    all_packs = [*pending, *applied, *rejected]
    writeback_total = [pack for pack in all_packs if pack.get("proposal_type") in {"session_writeback", "openclaw_runtime_writeback"} or "writeback" in str(pack.get("metadata", {}))]
    writeback_applied = [pack for pack in applied if pack in writeback_total or pack.get("proposal_type") in {"session_writeback", "openclaw_runtime_writeback"}]
    stale_packs = 0
    stale_field_failures = 0
    conflicted_packs = 0
    conflict_signals = 0
    for pack in all_packs:
        pack_stale = False
        if canonical_rev is not None and pack.get("base_canonical_rev") != canonical_rev and pack in pending:
            stale_field_failures += 1
            pack_stale = True
        if subject_repo_id is not None and pack.get("subject_repo_id") != subject_repo_id and pack in pending:
            stale_field_failures += 1
            pack_stale = True
        if subject_head_sha is not None and pack.get("subject_head_sha") != subject_head_sha and pack in pending:
            stale_field_failures += 1
            pack_stale = True
        stale_packs += int(pack_stale)
        metadata = pack.get("metadata", {})
        pack_conflicted = False
        if isinstance(metadata, dict) and metadata.get("conflicts"):
            conflict_signals += 1
            pack_conflicted = True
        if pack.get("human_gate_class") in {"high_impact_contradiction", "supersede_delete"}:
            conflict_signals += 1
            pack_conflicted = True
        conflicted_packs += int(pack_conflicted)
    return {
        "pending_count": len(pending),
        "applied_count": len(applied),
        "rejected_count": len(rejected),
        "writeback_acceptance_rate": ratio(len(writeback_applied), len(writeback_total)),
        "stale_precondition_count": stale_packs,
        "stale_precondition_field_failures": stale_field_failures,
        "stale_precondition_rate": ratio(stale_packs, len(pending)),
        "conflict_count": conflicted_packs,
        "conflict_signals": conflict_signals,
        "conflict_rate": ratio(conflicted_packs, len(all_packs)),
    }


def video_metrics(paths: TopologyPaths) -> dict[str, Any]:
    total = 0
    manual = 0
    ready = 0
    for packet_path in sorted(paths.resolve("raw/packets").glob("src_*/packet.json")):
        try:
            packet = load_json(packet_path)
        except Exception:
            continue
        if packet.get("source_type") != "video_platform":
            continue
        total += 1
        artifacts = packet.get("artifacts", [])
        kinds = {item.get("kind") for item in artifacts if isinstance(item, dict)}
        locator_requires_capture = any(
            isinstance(item, dict)
            and item.get("kind") == "video_platform_locator"
            and item.get("requires_operator_capture") is True
            for item in artifacts
        )
        if locator_requires_capture or "video_capture_plan" in kinds or "video_capture_brief" in kinds:
            manual += 1
        if {"video_text_artifact"}.intersection(kinds) or {"transcript", "key_frames", "audio_summary"}.intersection(kinds):
            ready += 1
    return {
        "video_platform_sources": total,
        "manual_intervention_count": manual,
        "manual_intervention_rate": ratio(manual, total),
        "digest_ready_evidence_count": ready,
    }


def openclaw_metrics(paths: TopologyPaths) -> dict[str, Any]:
    pending = mutation_payloads(paths, "mutations/pending")
    applied = mutation_payloads(paths, "mutations/applied")
    rejected = mutation_payloads(paths, "mutations/rejected")
    runtime_pending = [pack for pack in pending if isinstance(pack.get("metadata"), dict) and pack["metadata"].get("openclaw_live_job_id")]
    runtime_applied = [pack for pack in applied if isinstance(pack.get("metadata"), dict) and pack["metadata"].get("openclaw_live_job_id")]
    runtime_rejected = [pack for pack in rejected if isinstance(pack.get("metadata"), dict) and pack["metadata"].get("openclaw_live_job_id")]
    decided = len(runtime_applied) + len(runtime_rejected)
    return {
        "runtime_pending_count": len(runtime_pending),
        "runtime_applied_count": len(runtime_applied),
        "runtime_rejected_count": len(runtime_rejected),
        "runtime_decided_count": decided,
        "runtime_proposal_count": len(runtime_pending) + decided,
        "runtime_proposal_acceptance_rate": ratio(len(runtime_applied), decided),
    }


def run_evaluation(root: str | Path, *, subject_repo_id: str | None = None) -> EvaluationResult:
    paths = TopologyPaths.from_root(root)
    canonical_rev, subject_head_sha = current_revisions(paths.root, subject_repo_id)
    payload = {
        "schema_version": "1.0",
        "id": new_id("evt"),
        "generated_at": utc_now(),
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "metrics": {
            "builder_packs": builder_pack_metrics(paths, canonical_rev=canonical_rev, subject_repo_id=subject_repo_id, subject_head_sha=subject_head_sha),
            "mutations": mutation_metrics(paths, canonical_rev=canonical_rev, subject_repo_id=subject_repo_id, subject_head_sha=subject_head_sha),
            "video": video_metrics(paths),
            "openclaw": openclaw_metrics(paths),
            "builder_task_success_rate": {"status": "not_measured", "reason": "requires paired with/without pack task experiments"},
            "context_fragment_relevance_score": {"status": "not_measured", "reason": "requires manual or captured relevance judgments"},
        },
    }
    output_dir = paths.ensure_dir("ops/reports/tmp/evaluations")
    report_path = output_dir / f"evaluation_{payload['id']}.json"
    payload["report_path"] = display_path(paths, report_path)
    atomic_write_text(report_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return EvaluationResult(report_path=report_path, payload=payload)
