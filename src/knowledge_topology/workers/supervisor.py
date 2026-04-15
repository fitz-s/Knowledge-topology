"""P12.4 protocol-driven maintainer supervisor."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_topology.adapters.digest_model import CommandDigestProviderAdapter, DigestProviderAdapter, JsonDirectoryDigestProviderAdapter
from knowledge_topology.git_state import read_git_state
from knowledge_topology.ids import new_id
from knowledge_topology.paths import QUEUE_KINDS, TopologyPaths
from knowledge_topology.schema.loader import load_json
from knowledge_topology.schema.mutation_pack import MutationPack, MutationPackError
from knowledge_topology.storage.spool import fail_job, move_job, read_job
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.subjects import SubjectRegistryError, subject_projection_authority
from knowledge_topology.workers.apply import ApplyError, apply_mutation
from knowledge_topology.workers.compose_openclaw import OpenClawComposeError, write_openclaw_projection
from knowledge_topology.workers.doctor import doctor_canonical_parity, doctor_projections, doctor_public_safe, doctor_queues
from knowledge_topology.workers.lint import run_repo_lints, run_runtime_lints
from knowledge_topology.workers.reconcile import ReconcileError, reconcile_digest
from knowledge_topology.workers.run_digest_queue import DigestQueueRunResult, run_digest_queue


class SupervisorError(ValueError):
    """Raised when supervisor inputs or policy are unsafe."""


@dataclass(frozen=True)
class LeaseRecoveryResult:
    requeued: int = 0
    failed: int = 0
    paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    blocked_queue_kinds: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SupervisorResult:
    report_path: Path
    escalation_path: Path | None
    payload: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def write_job(path: Path, job: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(job, indent=2, sort_keys=True) + "\n")


def display_path(paths: TopologyPaths, path: str | Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return str(candidate)
    try:
        return str(candidate.resolve().relative_to(paths.root))
    except ValueError:
        return candidate.name


def sanitize_text(paths: TopologyPaths, value: str) -> str:
    sanitized = value
    for root_value in {str(paths.root), str(paths.root.resolve())}:
        sanitized = sanitized.replace(root_value, ".")
    return sanitized


def sanitize_messages(paths: TopologyPaths, messages: list[str]) -> list[str]:
    return [sanitize_text(paths, message) for message in messages]


def recover_expired_leases(root: str | Path, *, max_attempts: int = 3) -> LeaseRecoveryResult:
    if max_attempts <= 0:
        raise SupervisorError("max_attempts must be positive")
    paths = TopologyPaths.from_root(root)
    now = datetime.now(timezone.utc)
    requeued = 0
    failed = 0
    touched: list[str] = []
    errors: list[str] = []
    blocked: set[str] = set()
    for kind in QUEUE_KINDS:
        leased_dir = paths.resolve(f"ops/queue/{kind}/leased")
        for path in sorted(leased_dir.glob("job_*.json")):
            try:
                if path.is_symlink() or not path.is_file():
                    raise SupervisorError("leased job must be a regular non-symlink file")
                job = read_job(path)
                expires_at = parse_time(job.get("lease_expires_at"))
                if expires_at is None or expires_at > now:
                    continue
                attempts = int(job.get("attempts", 0))
                if attempts < max_attempts:
                    job["lease_owner"] = None
                    job["leased_at"] = None
                    job["lease_expires_at"] = None
                    write_job(path, job)
                    moved = move_job(path, "pending")
                    requeued += 1
                else:
                    job["last_error"] = "supervisor recovered expired lease after max attempts"
                    write_job(path, job)
                    moved = fail_job(path)
                    failed += 1
                touched.append(display_path(paths, moved))
            except Exception as exc:
                errors.append(f"{display_path(paths, path)}: {exc}")
                blocked.add(kind)
    return LeaseRecoveryResult(requeued=requeued, failed=failed, paths=touched, errors=errors, blocked_queue_kinds=sorted(blocked))


def existing_mutation_digest_ids(paths: TopologyPaths) -> set[str]:
    digest_ids: set[str] = set()
    for folder in ["mutations/pending", "mutations/approved", "mutations/applied", "mutations/rejected"]:
        for path in sorted(paths.resolve(folder).glob("mut_*.json")):
            try:
                payload = load_json(path)
            except Exception:
                continue
            metadata = payload.get("metadata", {})
            if isinstance(metadata, dict) and isinstance(metadata.get("digest_id"), str):
                digest_ids.add(metadata["digest_id"])
    return digest_ids


def digest_has_current_done_job(
    paths: TopologyPaths,
    *,
    source_id: str,
    digest_id: str,
    digest_path: Path,
    subject_repo_id: str,
    subject_head_sha: str,
    canonical_rev: str,
) -> bool:
    for job_path in sorted(paths.resolve("ops/queue/digest/done").glob("job_*.json")):
        try:
            job = read_job(job_path)
        except Exception:
            continue
        payload = job.get("payload", {})
        if not isinstance(payload, dict) or payload.get("source_id") != source_id:
            continue
        if payload.get("digest_id") != digest_id:
            continue
        if payload.get("digest_json_path") != display_path(paths, digest_path):
            continue
        if job.get("subject_repo_id") == subject_repo_id and job.get("subject_head_sha") == subject_head_sha and job.get("base_canonical_rev") == canonical_rev:
            return True
    return False


def reconcile_ready_digests(
    root: str | Path,
    *,
    subject_repo_id: str,
    subject_head_sha: str,
    canonical_rev: str,
    max_items: int,
) -> tuple[list[str], list[str], list[str]]:
    if max_items < 0:
        raise SupervisorError("max_reconcile must be non-negative")
    paths = TopologyPaths.from_root(root)
    existing = existing_mutation_digest_ids(paths)
    created: list[str] = []
    errors: list[str] = []
    skipped: list[str] = []
    for digest_path in sorted(paths.resolve("digests/by_source").glob("src_*/*.json")):
        if len(created) >= max_items:
            break
        try:
            digest = load_json(digest_path)
            digest_id = digest.get("id")
            source_id = digest.get("source_id")
            if not isinstance(digest_id, str) or digest_id in existing:
                continue
            if not isinstance(source_id, str) or not digest_has_current_done_job(
                paths,
                source_id=source_id,
                digest_id=digest_id,
                digest_path=digest_path,
                subject_repo_id=subject_repo_id,
                subject_head_sha=subject_head_sha,
                canonical_rev=canonical_rev,
            ):
                skipped.append(f"{display_path(paths, digest_path)}: missing current completed digest job binding")
                continue
            mutation = reconcile_digest(
                paths.root,
                digest_json=digest_path,
                subject_repo_id=subject_repo_id,
                subject_head_sha=subject_head_sha,
                base_canonical_rev=canonical_rev,
                proposed_by="supervisor",
            )
            created.append(display_path(paths, mutation))
            existing.add(digest_id)
        except (ReconcileError, ValueError) as exc:
            errors.append(f"{display_path(paths, digest_path)}: {exc}")
    return created, errors, skipped


def load_pack(path: Path) -> MutationPack:
    return MutationPack.from_dict(load_json(path))


def is_low_risk_pack(pack: MutationPack) -> bool:
    if pack.requires_human:
        return False
    if pack.proposal_type not in {"digest_reconcile", "writeback_session"}:
        return False
    if not pack.changes:
        return False
    return all(change.get("op") == "open_gap" for change in pack.changes)


def apply_low_risk_mutations(
    root: str | Path,
    *,
    subject_repo_id: str,
    subject_head_sha: str,
    canonical_rev: str,
    enabled: bool,
    max_items: int,
) -> tuple[list[str], list[str], list[str]]:
    if max_items < 0:
        raise SupervisorError("max_apply must be non-negative")
    paths = TopologyPaths.from_root(root)
    applied: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for path in sorted(paths.resolve("mutations/pending").glob("mut_*.json")):
        if len(applied) >= max_items:
            break
        try:
            pack = load_pack(path)
        except (MutationPackError, ValueError) as exc:
            errors.append(f"{display_path(paths, path)}: invalid mutation pack: {exc}")
            continue
        if not is_low_risk_pack(pack):
            skipped.append(display_path(paths, path))
            continue
        if not enabled:
            skipped.append(display_path(paths, path))
            continue
        try:
            applied_path, _ = apply_mutation(
                paths.root,
                path,
                current_canonical_rev=canonical_rev,
                subject_repo_id=subject_repo_id,
                subject_head_sha=subject_head_sha,
            )
            applied.append(display_path(paths, applied_path))
        except (ApplyError, ValueError) as exc:
            errors.append(f"{display_path(paths, path)}: {exc}")
    return applied, skipped, errors


def provider_from_args(
    *,
    root: Path,
    digest_provider_command: str | None,
    model_output_dir: str | None,
    provider_timeout_seconds: int,
) -> DigestProviderAdapter | None:
    if digest_provider_command and model_output_dir:
        raise SupervisorError("use only one digest provider")
    if digest_provider_command:
        return CommandDigestProviderAdapter(digest_provider_command, cwd=root, timeout_seconds=provider_timeout_seconds)
    if model_output_dir:
        return JsonDirectoryDigestProviderAdapter(model_output_dir, root=root)
    return None


def current_context(root: Path, *, subject_repo_id: str) -> tuple[str, str]:
    state = read_git_state(root)
    if state.head_sha is None:
        raise SupervisorError("topology root must be a git repository")
    try:
        _, _, subject_head_sha = subject_projection_authority(root, subject_repo_id)
    except SubjectRegistryError as exc:
        raise SupervisorError(str(exc)) from exc
    return state.head_sha, subject_head_sha


def result_to_dict(paths: TopologyPaths, result: Any) -> dict[str, Any]:
    if isinstance(result, DigestQueueRunResult):
        return {
            "leased": result.leased,
            "completed": result.completed,
            "failed": result.failed,
            "requeued": result.requeued,
            "digest_json_paths": [display_path(paths, path) for path in result.digest_json_paths],
            "digest_md_paths": [display_path(paths, path) for path in result.digest_md_paths],
            "done_job_paths": [display_path(paths, path) for path in result.done_job_paths],
            "failed_job_paths": [display_path(paths, path) for path in result.failed_job_paths],
        }
    raise TypeError(type(result).__name__)


def write_json_report(paths: TopologyPaths, folder: str, prefix: str, payload: dict[str, Any]) -> Path:
    output_dir = paths.ensure_dir(folder)
    output = output_dir / f"{prefix}_{new_id('evt')}.json"
    atomic_write_text(output, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output


def run_supervisor(
    root: str | Path,
    *,
    subject_repo_id: str,
    digest_provider_command: str | None = None,
    model_output_dir: str | None = None,
    provider_timeout_seconds: int = 120,
    owner: str = "topology-supervisor",
    max_digest_jobs: int = 1,
    max_reconcile: int = 10,
    max_apply: int = 10,
    max_attempts: int = 3,
    auto_apply_low_risk: bool = False,
    openclaw_project_id: str | None = None,
    subject_path: str | Path | None = None,
) -> SupervisorResult:
    paths = TopologyPaths.from_root(root)
    canonical_rev, subject_head_sha = current_context(paths.root, subject_repo_id=subject_repo_id)
    provider = provider_from_args(
        root=paths.root,
        digest_provider_command=digest_provider_command,
        model_output_dir=model_output_dir,
        provider_timeout_seconds=provider_timeout_seconds,
    )
    started_at = utc_now()
    recovery = recover_expired_leases(paths.root, max_attempts=max_attempts)
    digest_recovery_blocked = "digest" in recovery.blocked_queue_kinds
    if provider is None or digest_recovery_blocked:
        digest_result = DigestQueueRunResult()
    else:
        digest_result = run_digest_queue(
            paths.root,
            provider_adapter=provider,
            owner=owner,
            current_subject_repo_id=subject_repo_id,
            current_subject_head_sha=subject_head_sha,
            current_canonical_rev=canonical_rev,
            max_jobs=max_digest_jobs,
            max_attempts=max_attempts,
        )
    reconciled, reconcile_errors, stale_digest_skips = reconcile_ready_digests(
        paths.root,
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        canonical_rev=canonical_rev,
        max_items=max_reconcile,
    )
    applied, skipped, apply_errors = apply_low_risk_mutations(
        paths.root,
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        canonical_rev=canonical_rev,
        enabled=auto_apply_low_risk,
        max_items=max_apply,
    )
    projection_path: str | None = None
    projection_error: str | None = None
    if openclaw_project_id is not None:
        try:
            projection_path = display_path(paths, write_openclaw_projection(
                paths.root,
                project_id=openclaw_project_id,
                canonical_rev=canonical_rev,
                subject_repo_id=subject_repo_id,
                subject_head_sha=subject_head_sha,
                subject_path=subject_path,
            ))
        except (OpenClawComposeError, ValueError) as exc:
            projection_error = sanitize_text(paths, str(exc))
    repo_lint = run_repo_lints(paths.root)
    runtime_lint = run_runtime_lints(paths.root)
    queue_doctor = doctor_queues(paths.root)
    public_safe = doctor_public_safe(paths.root)
    projections = doctor_projections(
        paths.root,
        project_id=openclaw_project_id,
        canonical_rev=canonical_rev if openclaw_project_id else None,
        subject_repo_id=subject_repo_id if openclaw_project_id else None,
        subject_head_sha=subject_head_sha if openclaw_project_id else None,
    )
    canonical_parity = doctor_canonical_parity(paths.root)
    escalations = []
    if skipped:
        escalations.append({"kind": "human_gate_required", "mutation_paths": skipped})
    if reconcile_errors:
        escalations.append({"kind": "reconcile_errors", "messages": reconcile_errors})
    if stale_digest_skips:
        escalations.append({"kind": "stale_digest_skipped", "messages": stale_digest_skips})
    if apply_errors:
        escalations.append({"kind": "apply_errors", "messages": apply_errors})
    if recovery.errors:
        escalations.append({"kind": "lease_recovery_errors", "messages": recovery.errors})
    if projection_error:
        escalations.append({"kind": "projection_error", "message": projection_error})
    for name, result in {
        "lint_repo": repo_lint,
        "lint_runtime": runtime_lint,
        "doctor_queues": queue_doctor,
        "doctor_public_safe": public_safe,
        "doctor_projections": projections,
        "doctor_canonical_parity": canonical_parity,
    }.items():
        if not result.ok:
            escalations.append({"kind": name, "messages": sanitize_messages(paths, result.messages)})
    payload = {
        "schema_version": "1.0",
        "id": new_id("evt"),
        "started_at": started_at,
        "completed_at": utc_now(),
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "canonical_rev": canonical_rev,
        "auto_apply_low_risk": auto_apply_low_risk,
        "lease_recovery": {
            "requeued": recovery.requeued,
            "failed": recovery.failed,
            "paths": recovery.paths,
            "errors": recovery.errors,
            "blocked_queue_kinds": recovery.blocked_queue_kinds,
        },
        "digest_queue": result_to_dict(paths, digest_result),
        "reconciled_mutations": reconciled,
        "applied_mutations": applied,
        "skipped_mutations": skipped,
        "projection_path": projection_path,
        "checks": {
            "lint_repo": {"ok": repo_lint.ok, "messages": sanitize_messages(paths, repo_lint.messages)},
            "lint_runtime": {"ok": runtime_lint.ok, "messages": sanitize_messages(paths, runtime_lint.messages)},
            "doctor_queues": {"ok": queue_doctor.ok, "messages": sanitize_messages(paths, queue_doctor.messages)},
            "doctor_public_safe": {"ok": public_safe.ok, "messages": sanitize_messages(paths, public_safe.messages)},
            "doctor_projections": {"ok": projections.ok, "messages": sanitize_messages(paths, projections.messages)},
            "doctor_canonical_parity": {"ok": canonical_parity.ok, "messages": sanitize_messages(paths, canonical_parity.messages)},
        },
        "escalations": escalations,
    }
    report_path = write_json_report(paths, "ops/reports/tmp/supervisor", "supervisor", payload)
    payload["report_path"] = display_path(paths, report_path)
    atomic_write_text(report_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    escalation_path = None
    if escalations:
        escalation_payload = {
            "schema_version": "1.0",
            "id": new_id("esc"),
            "created_at": utc_now(),
            "source_report": display_path(paths, report_path),
            "subject_repo_id": subject_repo_id,
            "canonical_rev": canonical_rev,
            "items": escalations,
        }
        escalation_path = write_json_report(paths, "ops/reports/tmp/supervisor/escalations", "escalation", escalation_payload)
        payload["escalation_path"] = display_path(paths, escalation_path)
        atomic_write_text(report_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return SupervisorResult(report_path=report_path, escalation_path=escalation_path, payload=payload)
