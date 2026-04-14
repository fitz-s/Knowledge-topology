"""P7 doctor checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge_topology.ids import is_valid_id
from knowledge_topology.paths import QUEUE_KINDS, QUEUE_STATES, TopologyPaths
from knowledge_topology.schema.loader import load_json
from knowledge_topology.schema.source_packet import SourcePacket
from knowledge_topology.storage.registry import RegistryError
from knowledge_topology.storage.registry import read_jsonl


@dataclass(frozen=True)
class DoctorResult:
    ok: bool
    messages: list[str]


def stale_anchors(root: str | Path, *, subject_repo_id: str, subject_head_sha: str) -> DoctorResult:
    paths = TopologyPaths.from_root(root)
    messages: list[str] = []
    try:
        rows = read_jsonl(paths.resolve("canonical/registry/file_refs.jsonl"))
    except RegistryError as exc:
        return DoctorResult(ok=False, messages=[f"file_refs registry is invalid: {exc}"])
    for row in rows:
        if row.get("repo_id") != subject_repo_id:
            continue
        if row.get("commit_sha") != subject_head_sha:
            messages.append(f"{row.get('path')}: stale anchor {row.get('commit_sha')} != {subject_head_sha}")
    return DoctorResult(ok=not messages, messages=messages)


def symlinked(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def binary_like(path: Path) -> bool:
    data = path.read_bytes()
    if not data:
        return False
    if b"\x00" in data:
        return True
    sample = data[:4096]
    textish = sum(1 for byte in sample if 32 <= byte <= 126 or byte in {9, 10, 13})
    return textish / len(sample) < 0.7


def doctor_queues(root: str | Path) -> DoctorResult:
    paths = TopologyPaths.from_root(root)
    messages: list[str] = []
    queue_root = paths.root / "ops/queue"
    if symlinked(paths.root, queue_root):
        return DoctorResult(ok=False, messages=[f"{queue_root}: queue root is symlinked"])
    now = datetime.now(timezone.utc)
    for child in sorted(queue_root.iterdir()):
        if child.is_symlink():
            messages.append(f"{child}: queue kind is symlinked")
            continue
        if not child.is_dir():
            messages.append(f"{child}: stray file in queue root")
            continue
        if child.name not in QUEUE_KINDS:
            messages.append(f"{child}: unknown queue kind")
        for state_dir in sorted(child.iterdir()):
            if state_dir.is_symlink():
                messages.append(f"{state_dir}: queue state is symlinked")
                continue
            if not state_dir.is_dir():
                messages.append(f"{state_dir}: stray file in queue kind")
                continue
            if state_dir.name not in QUEUE_STATES:
                messages.append(f"{state_dir}: unknown queue state")
                continue
            for job_path in sorted(state_dir.iterdir()):
                if job_path.is_symlink():
                    messages.append(f"{job_path}: queue job is symlinked")
                    continue
                if not job_path.is_file():
                    messages.append(f"{job_path}: queue job is not a regular file")
                    continue
                if job_path.suffix != ".json" or not job_path.stem.startswith("job_"):
                    messages.append(f"{job_path}: stray file in queue state")
                    continue
                try:
                    job = json.loads(job_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    messages.append(f"{job_path}: malformed queue job: {exc}")
                    continue
                if not isinstance(job, dict):
                    messages.append(f"{job_path}: queue job must be an object")
                    continue
                if job.get("id") != job_path.stem:
                    messages.append(f"{job_path}: queue job filename/id mismatch")
                if not isinstance(job.get("id"), str) or not is_valid_id(job["id"], prefix="job"):
                    messages.append(f"{job_path}: invalid queue job id")
                if state_dir.name == "leased":
                    try:
                        expires = datetime.fromisoformat(str(job.get("lease_expires_at", "")).replace("Z", "+00:00"))
                    except ValueError:
                        messages.append(f"{job_path}: invalid lease expiry")
                    else:
                        if expires <= now:
                            messages.append(f"{job_path}: expired lease")
                if state_dir.name == "failed":
                    messages.append(f"{job_path}: failed job")
    return DoctorResult(ok=not messages, messages=messages)


def doctor_projections(
    root: str | Path,
    *,
    project_id: str | None = None,
    canonical_rev: str | None = None,
    subject_repo_id: str | None = None,
    subject_head_sha: str | None = None,
) -> DoctorResult:
    paths = TopologyPaths.from_root(root)
    messages: list[str] = []
    tasks_root = paths.root / "projections/tasks"
    if symlinked(paths.root, tasks_root):
        return DoctorResult(ok=False, messages=[f"{tasks_root}: projection parent is symlinked"])
    for task_dir in sorted(tasks_root.glob("*")):
        if task_dir.is_symlink() or not task_dir.is_dir():
            messages.append(f"{task_dir}: builder pack directory is unsafe")
            continue
        for filename in ["metadata.json", "brief.md", "constraints.json", "relationship-tests.yaml", "source-bundle.json", "writeback-targets.json"]:
            path = task_dir / filename
            if not path.exists():
                messages.append(f"{path}: projection file missing")
            elif symlinked(paths.root, path):
                messages.append(f"{path}: projection file is symlinked")
    openclaw = paths.root / "projections/openclaw"
    if symlinked(paths.root, openclaw):
        messages.append(f"{openclaw}: OpenClaw projection parent is symlinked")
        return DoctorResult(ok=False, messages=messages)
    runtime = openclaw / "runtime-pack.json"
    manifest = openclaw / "wiki-mirror/manifest.json"
    if runtime.exists() or manifest.exists():
        for path in [runtime, openclaw / "runtime-pack.md", openclaw / "memory-prompt.md", manifest]:
            if not path.exists():
                messages.append(f"{path}: OpenClaw projection file missing")
            elif symlinked(paths.root, path):
                messages.append(f"{path}: OpenClaw projection file is symlinked")
        try:
            runtime_payload = json.loads(runtime.read_text(encoding="utf-8")) if runtime.exists() and not symlinked(paths.root, runtime) else {}
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() and not symlinked(paths.root, manifest) else {}
        except json.JSONDecodeError as exc:
            messages.append(f"{runtime}: OpenClaw projection JSON invalid: {exc}")
            runtime_payload = {}
            manifest_payload = {}
        for field, expected in {
            "project_id": project_id,
            "canonical_rev": canonical_rev,
            "subject_repo_id": subject_repo_id,
            "subject_head_sha": subject_head_sha,
        }.items():
            runtime_value = runtime_payload.get(field)
            manifest_value = manifest_payload.get(field)
            if runtime_value != manifest_value:
                messages.append(f"OpenClaw projection {field} metadata mismatch")
            if expected is not None and runtime_value != expected:
                messages.append(f"OpenClaw projection {field} is stale")
        pages = manifest_payload.get("pages", [])
        if isinstance(pages, list):
            for page in pages:
                if not isinstance(page, dict) or not isinstance(page.get("path"), str) or ".." in Path(page.get("path", "")).parts:
                    messages.append("OpenClaw projection manifest page path is unsafe")
                    continue
                page_path = openclaw / "wiki-mirror" / page["path"]
                if not page_path.exists() or symlinked(paths.root, page_path):
                    messages.append(f"{page_path}: OpenClaw wiki page is unsafe")
    return DoctorResult(ok=not messages, messages=messages)


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def doctor_canonical_parity(root: str | Path) -> DoctorResult:
    paths = TopologyPaths.from_root(root)
    messages: list[str] = []
    registries = {
        "create_claim": ("claim_id", "canonical/registry/claims.jsonl"),
        "add_edge": ("edge_id", "canonical/registry/edges.jsonl"),
        "propose_node": ("node_id", "canonical/registry/nodes.jsonl"),
    }
    registry_rows: dict[str, dict[str, Any]] = {}
    for op, (id_field, relative) in registries.items():
        seen: set[str] = set()
        for row in read_jsonl(paths.resolve(relative)):
            row_id = row.get(id_field) or row.get("id")
            if isinstance(row_id, str):
                if row_id in seen:
                    messages.append(f"{relative}: duplicate id {row_id}")
                seen.add(row_id)
                registry_rows[row_id] = row
    page_ids: set[str] = set()
    for page in paths.resolve("canonical/nodes").glob("*/*.md"):
        if symlinked(paths.root, page):
            messages.append(f"{page}: canonical page is symlinked")
            continue
        data = frontmatter(page)
        op = data.get("op")
        page_id = data.get("id")
        if page_id:
            page_ids.add(page_id)
        if op not in registries or not page_id:
            continue
        row = registry_rows.get(page_id)
        if row is None:
            messages.append(f"{page}: missing registry row for {page_id}")
            continue
        for field in ["id", "type", "status"]:
            if field in data and field in row and str(row[field]) != data[field]:
                messages.append(f"{page}: {field} mismatch")
    for row_id in sorted(set(registry_rows) - page_ids):
        messages.append(f"canonical/nodes: missing page for {row_id}")
    return DoctorResult(ok=not messages, messages=messages)


def doctor_public_safe(root: str | Path) -> DoctorResult:
    paths = TopologyPaths.from_root(root)
    messages: list[str] = []
    packets_root = paths.root / "raw/packets"
    if symlinked(paths.root, packets_root):
        return DoctorResult(ok=False, messages=[f"{packets_root}: source packet parent is symlinked"])
    for packet_dir in packets_root.glob("src_*"):
        if packet_dir.is_symlink() or not packet_dir.is_dir():
            messages.append(f"{packet_dir}: source packet directory is symlinked")
            continue
        packet_path = packet_dir / "packet.json"
        if packet_path.is_symlink() or not packet_path.exists():
            messages.append(f"{packet_path}: source packet file is unsafe")
            continue
        try:
            packet = SourcePacket(**load_json(packet_path))
            packet.validate()
        except Exception as exc:
            messages.append(f"{packet_path}: invalid source packet: {exc}")
            continue
        if packet.content_mode == "public_text" and packet.redistributable != "yes":
            messages.append(f"{packet_path}: public_text requires redistributable=yes")
        content = packet_dir / "content.md"
        if content.exists():
            if content.is_symlink():
                messages.append(f"{content}: public content is symlinked")
            elif packet.source_type != "local_draft" and len(content.read_text(encoding="utf-8")) > 8000:
                messages.append(f"{content}: external public_text exceeds 8000 characters")
        for child in packet_dir.iterdir():
            if child.is_symlink():
                messages.append(f"{child}: packet artifact is symlinked")
            if child.suffix.lower() == ".pdf":
                messages.append(f"{child}: PDF bytes must not be tracked in packet dir")
            if child.is_file() and "local_blob" in child.name:
                messages.append(f"{child}: local blob bytes must not be tracked in packet dir")
            if child.is_file() and child.name not in {"packet.json", "content.md", "excerpt.md"} and binary_like(child):
                messages.append(f"{child}: binary-looking bytes must not be tracked in packet dir")
        for artifact in packet.artifacts:
            if isinstance(artifact, dict) and str(artifact.get("kind", "")).casefold().startswith("local_blob"):
                artifact_path = artifact.get("path")
                if isinstance(artifact_path, str):
                    candidate = packet_dir / artifact_path
                    if candidate.exists():
                        messages.append(f"{candidate}: local blob bytes must not be tracked in packet dir")
        serialized = json.dumps(packet.artifacts)
        if any(marker in serialized.casefold() for marker in (".openclaw", "private", "cache")):
            messages.append(f"{packet_path}: private/cache/OpenClaw path marker in artifacts")
    return DoctorResult(ok=not messages, messages=messages)
