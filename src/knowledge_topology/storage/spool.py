"""Single-filesystem spool queue helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from knowledge_topology.ids import new_id
from knowledge_topology.paths import QUEUE_KINDS, QUEUE_STATES, TopologyPaths
from knowledge_topology.storage.transaction import atomic_write_text


class SpoolError(RuntimeError):
    """Raised when a spool operation cannot proceed."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_spool(root: str | Path, kind: str) -> None:
    if kind not in QUEUE_KINDS:
        raise SpoolError(f"unknown queue kind: {kind}")
    paths = TopologyPaths.from_root(root)
    for state in QUEUE_STATES:
        paths.ensure_dir(f"ops/queue/{kind}/{state}")


def _job_path(root: str | Path, kind: str, state: str, job_id: str) -> Path:
    if state not in QUEUE_STATES:
        raise SpoolError(f"unknown queue state: {state}")
    paths = TopologyPaths.from_root(root)
    return paths.resolve(f"ops/queue/{kind}/{state}/{job_id}.json")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_job(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def create_job(
    root: str | Path,
    kind: str,
    *,
    payload: dict[str, Any],
    subject_repo_id: str,
    subject_head_sha: str,
    base_canonical_rev: str,
    created_by: str,
) -> Path:
    ensure_spool(root, kind)
    job_id = new_id("job")
    now = isoformat(utc_now())
    job = {
        "schema_version": "1.0",
        "id": job_id,
        "kind": kind,
        "created_at": now,
        "created_by": created_by,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "base_canonical_rev": base_canonical_rev,
        "payload": payload,
        "attempts": 0,
        "lease_owner": None,
        "leased_at": None,
        "lease_expires_at": None,
    }
    path = _job_path(root, kind, "pending", job_id)
    _write_json(path, job)
    return path


def lease_next(root: str | Path, kind: str, *, owner: str, lease_seconds: int = 900) -> Path | None:
    ensure_spool(root, kind)
    paths = TopologyPaths.from_root(root)
    pending_dir = paths.resolve(f"ops/queue/{kind}/pending")
    leased_dir = paths.resolve(f"ops/queue/{kind}/leased")
    for pending in sorted(pending_dir.glob("job_*.json")):
        leased = leased_dir / pending.name
        try:
            os.replace(pending, leased)
        except FileNotFoundError:
            continue
        job = read_job(leased)
        now = utc_now()
        job["attempts"] = int(job.get("attempts", 0)) + 1
        job["lease_owner"] = owner
        job["leased_at"] = isoformat(now)
        job["lease_expires_at"] = isoformat(now + timedelta(seconds=lease_seconds))
        _write_json(leased, job)
        return leased
    return None


def move_job(path: str | Path, target_state: str) -> Path:
    current = Path(path)
    if target_state not in QUEUE_STATES:
        raise SpoolError(f"unknown queue state: {target_state}")
    kind = current.parents[1].name
    root = current.parents[4]
    target = _job_path(root, kind, target_state, current.stem)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(current, target)
    return target


def complete_job(path: str | Path) -> Path:
    return move_job(path, "done")


def fail_job(path: str | Path) -> Path:
    return move_job(path, "failed")


def requeue_failed_job(path: str | Path) -> Path:
    current = Path(path)
    if current.parent.name != "failed":
        raise SpoolError("only failed jobs may be explicitly requeued")
    return move_job(current, "pending")
