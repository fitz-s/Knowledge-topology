"""P11.2 digest queue runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_topology.adapters.digest_model import DictDigestAdapter
from knowledge_topology.adapters.digest_model import DigestProviderAdapter
from knowledge_topology.ids import is_valid_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.storage.spool import complete_job
from knowledge_topology.storage.spool import fail_job
from knowledge_topology.storage.spool import lease_next
from knowledge_topology.storage.spool import move_job
from knowledge_topology.storage.spool import read_job
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.workers.digest import build_digest_model_request
from knowledge_topology.workers.digest import write_digest_artifacts


class DigestQueueRunnerError(ValueError):
    """Raised when a digest queue job cannot be run safely."""


@dataclass(frozen=True)
class DigestQueueRunResult:
    leased: int = 0
    completed: int = 0
    failed: int = 0
    requeued: int = 0
    digest_json_paths: list[Path] = field(default_factory=list)
    digest_md_paths: list[Path] = field(default_factory=list)
    done_job_paths: list[Path] = field(default_factory=list)
    failed_job_paths: list[Path] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def bounded_error(exc: BaseException, limit: int = 4096) -> str:
    return " ".join(str(exc).split())[:limit]


def write_job(path: Path, job: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(job, indent=2, sort_keys=True) + "\n")


def annotate_failure(path: Path, exc: BaseException) -> Path:
    job = read_job(path)
    job["last_error"] = bounded_error(exc)
    write_job(path, job)
    return fail_job(path)


def clear_lease(path: Path) -> None:
    job = read_job(path)
    job["lease_owner"] = None
    job["leased_at"] = None
    job["lease_expires_at"] = None
    write_job(path, job)


def recover_expired_leases(root: str | Path, *, max_attempts: int) -> tuple[int, list[Path]]:
    if max_attempts <= 0:
        raise DigestQueueRunnerError("max_attempts must be positive")
    paths = TopologyPaths.from_root(root)
    leased_dir = paths.resolve("ops/queue/digest/leased")
    requeued = 0
    failed: list[Path] = []
    now = utc_now()
    for path in sorted(leased_dir.glob("job_*.json")):
        job = read_job(path)
        expires_at = parse_time(job.get("lease_expires_at"))
        if expires_at is None or expires_at > now:
            continue
        attempts = int(job.get("attempts", 0))
        if attempts < max_attempts:
            clear_lease(path)
            move_job(path, "pending")
            requeued += 1
        else:
            failed.append(annotate_failure(path, DigestQueueRunnerError("digest job lease expired")))
    return requeued, failed


def validate_job_preconditions(
    job: dict[str, Any],
    *,
    current_subject_repo_id: str,
    current_subject_head_sha: str,
    current_canonical_rev: str,
) -> str:
    source_id = job.get("payload", {}).get("source_id")
    if not isinstance(source_id, str) or not is_valid_id(source_id, prefix="src"):
        raise DigestQueueRunnerError("digest job payload.source_id must use src_ opaque ID")
    if job.get("base_canonical_rev") != current_canonical_rev:
        raise DigestQueueRunnerError("digest job base_canonical_rev is stale")
    if job.get("subject_repo_id") != current_subject_repo_id:
        raise DigestQueueRunnerError("digest job subject_repo_id mismatch")
    if job.get("subject_head_sha") != current_subject_head_sha:
        raise DigestQueueRunnerError("digest job subject_head_sha is stale")
    return source_id


def reject_existing_digest_artifacts(root: str | Path, source_id: str) -> None:
    paths = TopologyPaths.from_root(root)
    digest_dir = paths.resolve(f"digests/by_source/{source_id}")
    if digest_dir.exists() and any(digest_dir.glob("*.json")):
        raise DigestQueueRunnerError(f"digest artifact already exists for source: {source_id}")


def run_digest_queue(
    root: str | Path,
    *,
    provider_adapter: DigestProviderAdapter,
    owner: str,
    current_subject_repo_id: str,
    current_subject_head_sha: str,
    current_canonical_rev: str,
    max_jobs: int = 1,
    lease_seconds: int = 900,
    max_attempts: int = 3,
) -> DigestQueueRunResult:
    for field_name, value in {
        "owner": owner,
        "current_subject_repo_id": current_subject_repo_id,
        "current_subject_head_sha": current_subject_head_sha,
        "current_canonical_rev": current_canonical_rev,
    }.items():
        if not value.strip():
            raise DigestQueueRunnerError(f"{field_name} is required")
    if max_jobs < 0:
        raise DigestQueueRunnerError("max_jobs must be non-negative")
    requeued, recovery_failed = recover_expired_leases(root, max_attempts=max_attempts)
    leased = 0
    completed = 0
    failed_paths = list(recovery_failed)
    json_paths: list[Path] = []
    md_paths: list[Path] = []
    done_paths: list[Path] = []

    for _ in range(max_jobs):
        leased_path = lease_next(root, "digest", owner=owner, lease_seconds=lease_seconds)
        if leased_path is None:
            break
        leased += 1
        try:
            job = read_job(leased_path)
            source_id = validate_job_preconditions(
                job,
                current_subject_repo_id=current_subject_repo_id,
                current_subject_head_sha=current_subject_head_sha,
                current_canonical_rev=current_canonical_rev,
            )
            reject_existing_digest_artifacts(root, source_id)
            request = build_digest_model_request(root, source_id)
            payload = provider_adapter.generate(request)
            digest_json, digest_md = write_digest_artifacts(
                root,
                source_id=source_id,
                model_adapter=DictDigestAdapter(payload),
            )
            done_paths.append(complete_job(leased_path))
            json_paths.append(digest_json)
            md_paths.append(digest_md)
            completed += 1
        except Exception as exc:
            failed_paths.append(annotate_failure(leased_path, exc))

    return DigestQueueRunResult(
        leased=leased,
        completed=completed,
        failed=len(failed_paths),
        requeued=requeued,
        digest_json_paths=json_paths,
        digest_md_paths=md_paths,
        done_job_paths=done_paths,
        failed_job_paths=failed_paths,
    )
