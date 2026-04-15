"""P11.4 OpenClaw live writeback bridge."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_topology.ids import is_valid_id, new_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.storage.spool import create_job, complete_job, fail_job, lease_next, read_job
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.workers.writeback import writeback_session


class OpenClawLiveError(ValueError):
    """Raised when an OpenClaw live writeback is unsafe."""


ISSUER = "topology_openclaw_live"
INDEX_RELATIVE = ".tmp/openclaw-live/issued-leases.jsonl"
SECRET_RELATIVE = ".tmp/openclaw-live/issuer-secret.txt"
PRIVATE_MARKERS = (
    ".openclaw",
    "openclaw_config",
    "openclaw-session",
    "openclaw_session",
    "session",
    "credential",
    "token",
    "secret",
    "private",
    "cache",
)


@dataclass(frozen=True)
class LiveWritebackResult:
    mutation_path: Path | None
    relationship_tests_path: Path | None
    lease_path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def summary_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def safe_tmp_path(paths: TopologyPaths, relative: str, label: str) -> Path:
    target = paths.root / relative
    current = paths.root
    for part in Path(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise OpenClawLiveError(f"{label} parent must not be a symlink")
        if current.exists() and not current.is_dir():
            raise OpenClawLiveError(f"{label} parent must be a directory")
    if target.is_symlink():
        raise OpenClawLiveError(f"{label} must not be a symlink")
    resolved = target.resolve() if target.exists() else target.parent.resolve() / target.name
    if paths.root not in resolved.parents and resolved != paths.root:
        raise OpenClawLiveError(f"{label} escaped topology root")
    return target


def ensure_private_dir(paths: TopologyPaths) -> Path:
    directory = safe_tmp_path(paths, ".tmp/openclaw-live/placeholder", "OpenClaw live state").parent
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OpenClawLiveError(f"{label} must be a regular non-symlink file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OpenClawLiveError(f"{label} JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenClawLiveError(f"{label} must be a JSON object")
    return payload


def private_secret(paths: TopologyPaths) -> str:
    ensure_private_dir(paths)
    path = safe_tmp_path(paths, SECRET_RELATIVE, "OpenClaw live secret")
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    atomic_write_text(path, secret + "\n")
    return secret


def signature(secret: str, entry: dict[str, Any]) -> str:
    fields = [
        entry["job_id"],
        entry["lease_nonce"],
        entry["runtime_summary_hash"],
        entry["project_id"],
        entry["canonical_rev"],
        entry["subject_repo_id"],
        entry["subject_head_sha"],
    ]
    return hmac.new(secret.encode("utf-8"), "|".join(fields).encode("utf-8"), hashlib.sha256).hexdigest()


def index_path(paths: TopologyPaths) -> Path:
    ensure_private_dir(paths)
    return safe_tmp_path(paths, INDEX_RELATIVE, "OpenClaw live issued index")


def read_index(paths: TopologyPaths) -> list[dict[str, Any]]:
    path = index_path(paths)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def write_index(paths: TopologyPaths, rows: list[dict[str, Any]]) -> None:
    path = index_path(paths)
    atomic_write_text(path, "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def update_index_entry(paths: TopologyPaths, job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    rows = read_index(paths)
    found = None
    for row in rows:
        if row.get("job_id") == job_id:
            row.update(updates)
            found = row
            break
    if found is None:
        raise OpenClawLiveError("issued lease entry not found")
    write_index(paths, rows)
    return found


def issue_openclaw_live_lease(
    root: str | Path,
    *,
    project_id: str,
    canonical_rev: str,
    subject_repo_id: str,
    subject_head_sha: str,
    runtime_summary: dict[str, Any],
    created_by: str = "openclaw-live-issuer",
) -> Path:
    paths = TopologyPaths.from_root(root)
    assert_no_private_strings(runtime_summary)
    digest = summary_hash(runtime_summary)
    nonce = secrets.token_hex(16)
    pending = create_job(
        paths.root,
        "writeback",
        payload={
            "issuer": ISSUER,
            "lease_nonce": nonce,
            "runtime_summary_hash": digest,
            "project_id": project_id,
            "mode": "runtime_writeback",
        },
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        base_canonical_rev=canonical_rev,
        created_by=created_by,
    )
    job_id = pending.stem
    entry = {
        "job_id": job_id,
        "lease_nonce": nonce,
        "runtime_summary_hash": digest,
        "project_id": project_id,
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "status": "issued",
        "created_at": utc_now(),
    }
    entry["signature"] = signature(private_secret(paths), entry)
    rows = read_index(paths)
    rows.append(entry)
    write_index(paths, rows)
    return pending


def lease_openclaw_live_job(root: str | Path, *, owner: str, lease_seconds: int = 900) -> Path:
    paths = TopologyPaths.from_root(root)
    leased = lease_next(paths.root, "writeback", owner=owner, lease_seconds=lease_seconds)
    if leased is None:
        raise OpenClawLiveError("no OpenClaw live writeback job is pending")
    job = read_job(leased)
    payload = job.get("payload", {})
    if not isinstance(payload, dict) or payload.get("issuer") != ISSUER:
        raise OpenClawLiveError("leased writeback job is not an OpenClaw live job")
    update_index_entry(paths, job["id"], {
        "status": "leased",
        "lease_owner": owner,
        "leased_at": job.get("leased_at"),
        "lease_expires_at": job.get("lease_expires_at"),
    })
    return leased


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise OpenClawLiveError("lease expiry is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OpenClawLiveError("lease expiry is invalid") from exc


def validate_lease_path(paths: TopologyPaths, lease_path: str | Path) -> Path:
    lease = Path(lease_path).expanduser()
    if not lease.is_absolute():
        lease = paths.root / lease
    leased_dir = paths.resolve("ops/queue/writeback/leased")
    current = paths.root
    try:
        relative = lease.relative_to(paths.root)
    except ValueError as exc:
        raise OpenClawLiveError("lease escaped topology root") from exc
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise OpenClawLiveError("lease parent must not be a symlink")
    if lease.parent != leased_dir:
        raise OpenClawLiveError("lease must be under ops/queue/writeback/leased")
    if lease.is_symlink() or not lease.is_file():
        raise OpenClawLiveError("lease must be a regular non-symlink file")
    return lease


def validate_issued_entry(paths: TopologyPaths, job: dict[str, Any], expected: dict[str, str], *, lease_stem: str) -> dict[str, Any]:
    job_id = job.get("id")
    payload = job.get("payload", {})
    if not isinstance(job_id, str) or not is_valid_id(job_id, prefix="job") or not isinstance(payload, dict):
        raise OpenClawLiveError("lease job is malformed")
    if lease_stem != job_id:
        raise OpenClawLiveError("lease filename does not match job id")
    rows = read_index(paths)
    matches = [row for row in rows if row.get("job_id") == job_id]
    if len(matches) != 1:
        raise OpenClawLiveError("issued lease entry missing")
    entry = matches[0]
    if entry.get("status") == "consumed":
        raise OpenClawLiveError("issued lease already consumed")
    if entry.get("status") not in {"leased", "in_progress"}:
        raise OpenClawLiveError("issued lease was not leased by topology")
    secret = private_secret(paths)
    expected_signature = signature(secret, entry)
    if not hmac.compare_digest(str(entry.get("signature", "")), expected_signature):
        raise OpenClawLiveError("issued lease signature mismatch")
    for key in ["lease_nonce", "runtime_summary_hash", "project_id"]:
        if payload.get(key) != entry.get(key):
            raise OpenClawLiveError(f"lease {key} mismatch")
    for key, value in expected.items():
        if entry.get(key) != value:
            raise OpenClawLiveError(f"issued lease {key} mismatch")
    if job.get("subject_repo_id") != expected["subject_repo_id"]:
        raise OpenClawLiveError("lease subject_repo_id mismatch")
    if job.get("subject_head_sha") != expected["subject_head_sha"]:
        raise OpenClawLiveError("lease subject_head_sha mismatch")
    if job.get("base_canonical_rev") != expected["canonical_rev"]:
        raise OpenClawLiveError("lease canonical_rev mismatch")
    if payload.get("issuer") != ISSUER:
        raise OpenClawLiveError("lease issuer mismatch")
    if entry.get("lease_owner") != job.get("lease_owner") or entry.get("leased_at") != job.get("leased_at"):
        raise OpenClawLiveError("lease metadata mismatch")
    expires_at = parse_time(job.get("lease_expires_at"))
    if expires_at <= datetime.now(timezone.utc):
        raise OpenClawLiveError("lease is expired")
    return entry


def projection_file(paths: TopologyPaths, relative: str, label: str) -> Path:
    path = paths.root / relative
    current = paths.root
    for part in Path(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise OpenClawLiveError(f"{label} parent must not be a symlink")
    if path.is_symlink() or not path.is_file():
        raise OpenClawLiveError(f"{label} must be a regular non-symlink file")
    return path


def validate_projection(paths: TopologyPaths, expected: dict[str, str]) -> None:
    runtime = read_json(projection_file(paths, "projections/openclaw/runtime-pack.json", "runtime pack"), "runtime pack")
    projection_file(paths, "projections/openclaw/runtime-pack.md", "runtime markdown")
    projection_file(paths, "projections/openclaw/memory-prompt.md", "memory prompt")
    manifest = read_json(projection_file(paths, "projections/openclaw/wiki-mirror/manifest.json", "wiki manifest"), "wiki manifest")
    for field in ["project_id", "canonical_rev", "subject_repo_id", "subject_head_sha"]:
        if runtime.get(field) != expected[field]:
            raise OpenClawLiveError(f"runtime pack {field} mismatch")
        if manifest.get(field) != expected[field]:
            raise OpenClawLiveError(f"wiki manifest {field} mismatch")
    for page in manifest.get("pages", []):
        if not isinstance(page, dict):
            raise OpenClawLiveError("wiki manifest page is malformed")
        path = page.get("path")
        if not isinstance(path, str) or not re.fullmatch(r"pages/[A-Za-z0-9_]+\.md", path):
            raise OpenClawLiveError("wiki manifest page path is unsafe")
        projection_file(paths, f"projections/openclaw/wiki-mirror/{path}", "wiki page")


def assert_no_private_strings(value: Any, field: str = "summary") -> None:
    if isinstance(value, str):
        folded = value.casefold()
        if value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value):
            raise OpenClawLiveError(f"{field} contains private path")
        if any(marker in folded for marker in PRIVATE_MARKERS):
            raise OpenClawLiveError(f"{field} contains private OpenClaw state")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_private_strings(item, f"{field}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            assert_no_private_strings(item, f"{field}.{key}")


def safe_staged_summary_path(paths: TopologyPaths, job_id: str, *, allow_existing: bool) -> Path:
    if not is_valid_id(job_id, prefix="job"):
        raise OpenClawLiveError("job id is invalid")
    tmp = paths.root / ".tmp"
    writeback = tmp / "writeback"
    job_dir = writeback / job_id
    for directory in [tmp, writeback]:
        if directory.is_symlink():
            raise OpenClawLiveError("summary staging parent must not be a symlink")
        if directory.exists() and not directory.is_dir():
            raise OpenClawLiveError("summary staging parent must be a directory")
        directory.mkdir(exist_ok=True)
    if job_dir.exists() and not allow_existing:
        raise OpenClawLiveError("summary staging directory already exists")
    if job_dir.is_symlink():
        raise OpenClawLiveError("summary staging directory must not be a symlink")
    if not job_dir.exists():
        os.mkdir(job_dir)
    path = job_dir / "summary.json"
    if path.exists() and not allow_existing:
        raise OpenClawLiveError("summary staging file already exists")
    if path.is_symlink():
        raise OpenClawLiveError("summary staging file must not be a symlink")
    return path


def verify_evidence(paths: TopologyPaths, summary: dict[str, Any], digest_hash: str, job_id: str) -> None:
    source_id = summary.get("source_id")
    digest_id = summary.get("digest_id")
    if not isinstance(source_id, str) or not is_valid_id(source_id, prefix="src"):
        raise OpenClawLiveError("summary source_id is invalid")
    if not isinstance(digest_id, str) or not is_valid_id(digest_id, prefix="dg"):
        raise OpenClawLiveError("summary digest_id is invalid")
    packet_path = paths.resolve(f"raw/packets/{source_id}/packet.json")
    digest_path = paths.resolve(f"digests/by_source/{source_id}/{digest_id}.json")
    packet = read_json(packet_path, "source packet")
    digest = read_json(digest_path, "digest")
    if digest.get("source_id") != source_id:
        raise OpenClawLiveError("digest source_id mismatch")
    artifact_ok = any(
        isinstance(item, dict)
        and item.get("kind") == "runtime_summary_evidence"
        and item.get("runtime_summary_hash") == digest_hash
        and item.get("openclaw_live_job_id") == job_id
        for item in packet.get("artifacts", [])
    )
    digest_ok = any(
        isinstance(item, dict)
        and item.get("kind") == "runtime_summary_evidence"
        and item.get("runtime_summary_hash") == digest_hash
        and item.get("openclaw_live_job_id") == job_id
        for item in digest.get("direct_evidence", [])
    )
    if not artifact_ok or not digest_ok:
        raise OpenClawLiveError("runtime evidence is not bound to summary")


def find_existing_mutation(paths: TopologyPaths, staged_summary: Path, job_id: str) -> Path | None:
    target = str(staged_summary)
    for path in sorted(paths.resolve("mutations/pending").glob("mut_*.json")):
        payload = read_json(path, "pending mutation")
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict) and (
            metadata.get("writeback_summary") == target or metadata.get("openclaw_live_job_id") == job_id
        ):
            return path
    return None


def consume_lease(paths: TopologyPaths, lease_path: Path, mutation_path: Path | None) -> Path:
    job = read_job(lease_path)
    if mutation_path is not None:
        job["mutation_pack_id"] = mutation_path.stem
    atomic_write_text(lease_path, json.dumps(job, indent=2, sort_keys=True) + "\n")
    update_index_entry(paths, job["id"], {"status": "consumed", "mutation_pack_id": mutation_path.stem if mutation_path else None})
    return complete_job(lease_path)


def fail_lease(paths: TopologyPaths, lease_path: Path, exc: BaseException) -> Path:
    job = read_job(lease_path)
    job["last_error"] = " ".join(str(exc).split())[:500]
    atomic_write_text(lease_path, json.dumps(job, indent=2, sort_keys=True) + "\n")
    update_index_entry(paths, job["id"], {"status": "failed", "last_error": job["last_error"]})
    return fail_job(lease_path)


def run_openclaw_live_writeback(
    root: str | Path,
    *,
    project_id: str,
    canonical_rev: str,
    subject_repo_id: str,
    subject_head_sha: str,
    lease_path: str | Path,
    runtime_summary_path: str | Path,
    fail_after_write: bool = False,
) -> LiveWritebackResult:
    paths = TopologyPaths.from_root(root)
    summary = read_json(Path(runtime_summary_path), "runtime summary")
    assert_no_private_strings(summary)
    digest_hash = summary_hash(summary)
    expected = {
        "project_id": project_id,
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
    }
    lease = validate_lease_path(paths, lease_path)
    job = read_job(lease)
    entry = validate_issued_entry(paths, job, expected, lease_stem=lease.stem)
    if entry.get("runtime_summary_hash") != digest_hash:
        raise OpenClawLiveError("runtime summary hash mismatch")
    job_id = job["id"]
    validate_projection(paths, expected)
    verify_evidence(paths, summary, digest_hash, job_id)
    staged = safe_staged_summary_path(paths, job_id, allow_existing=entry.get("status") == "in_progress")
    existing = find_existing_mutation(paths, staged, job_id)
    if entry.get("status") == "in_progress" and existing is not None:
        done = consume_lease(paths, lease, existing)
        return LiveWritebackResult(existing, None, done)
    update_index_entry(paths, job_id, {"status": "in_progress", "staged_summary_path": str(staged)})
    atomic_write_text(staged, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    try:
        mutation, reltests = writeback_session(
            paths.root,
            summary_path=staged,
            subject_repo_id=subject_repo_id,
            subject_head_sha=subject_head_sha,
            base_canonical_rev=canonical_rev,
            current_canonical_rev=canonical_rev,
            current_subject_head_sha=subject_head_sha,
            metadata_extra={
                "openclaw_live_job_id": job_id,
                "runtime_summary_hash": digest_hash,
                "project_id": project_id,
            },
        )
        if fail_after_write:
            raise OpenClawLiveError("injected failure after mutation write")
        done = consume_lease(paths, lease, mutation)
        return LiveWritebackResult(mutation, reltests, done)
    except Exception as exc:
        if not fail_after_write:
            fail_lease(paths, lease, exc)
        raise


def create_runtime_source_packet(
    root: str | Path,
    *,
    project_id: str,
    canonical_rev: str,
    subject_repo_id: str,
    subject_head_sha: str,
    runtime_summary: dict[str, Any],
) -> Path:
    paths = TopologyPaths.from_root(root)
    assert_no_private_strings(runtime_summary)
    digest_hash = summary_hash(runtime_summary)
    source_id = new_id("src")
    packet_dir = paths.ensure_dir(f"raw/packets/{source_id}")
    excerpt = canonical_json(runtime_summary)
    atomic_write_text(packet_dir / "excerpt.md", excerpt + "\n")
    packet = {
        "schema_version": "1.0",
        "id": source_id,
        "source_type": "local_draft",
        "original_url": f"openclaw-runtime:{project_id}",
        "canonical_url": None,
        "retrieved_at": utc_now(),
        "curator_note": "OpenClaw runtime summary captured for digesting",
        "ingest_depth": "standard",
        "authority": "runtime_observed",
        "trust_scope": "runtime",
        "content_status": "partial",
        "content_mode": "excerpt_only",
        "redistributable": "no",
        "hash_original": None,
        "hash_normalized": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "artifacts": [{"kind": "runtime_summary_evidence", "runtime_summary_hash": digest_hash}],
        "fetch_chain": [{"method": "openclaw_runtime", "status": "partial", "note": "Captured runtime summary"}],
    }
    atomic_write_text(packet_dir / "packet.json", json.dumps(packet, indent=2, sort_keys=True) + "\n")
    create_job(
        paths.root,
        "digest",
        payload={"source_id": source_id, "audience": "openclaw"},
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        base_canonical_rev=canonical_rev,
        created_by="openclaw-live",
    )
    return packet_dir / "packet.json"
