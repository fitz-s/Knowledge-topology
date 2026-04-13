"""P9 deterministic OpenClaw runtime projection compiler."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from knowledge_topology.git_state import read_git_state
from knowledge_topology.ids import is_valid_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.storage.registry import read_jsonl
from knowledge_topology.storage.transaction import atomic_write_text


class OpenClawComposeError(ValueError):
    """Raised when OpenClaw projection cannot be compiled safely."""


VALID_SENSITIVITY = {"public", "internal", "operator_only", "runtime_only"}
VALID_SCOPE = {"global", "repo", "operator", "runtime"}
VALID_AUTHORITY = {"source_grounded", "repo_observed", "runtime_observed", "fitz_curated", "model_inferred"}
VALID_STATUS = {"draft", "active", "contested", "superseded", "rejected"}
VISIBLE_STATUS = {"active", "draft", "contested"}
VALID_NODE_TYPES = {
    "finding",
    "method",
    "claim",
    "assumption",
    "question",
    "fitz_belief",
    "decision",
    "invariant",
    "interface",
    "component",
    "runtime_observation",
    "operator_directive",
    "artifact",
    "task_lesson",
}
RECORD_FIELDS = [
    "id",
    "kind",
    "type",
    "status",
    "authority",
    "scope",
    "sensitivity",
    "audiences",
    "confidence",
    "summary",
    "statement",
    "source_ids",
    "claim_ids",
    "basis_claim_ids",
    "file_refs",
    "tags",
    "updated_at",
]
FILE_REF_FIELDS = ["repo_id", "commit_sha", "path", "path_at_capture", "line_range", "symbol", "anchor_kind", "excerpt_hash", "verified_at"]
FORBIDDEN_PATH_PARTS = ("local_blobs", ".openclaw-wiki", ".tmp", "cache")
FORBIDDEN_ANCHOR_PATH_PARTS = (
    "local_blobs",
    ".openclaw-wiki",
    ".tmp",
    "/cache/",
    "openclaw_home",
    "openclaw/config",
    "openclaw/session",
    ".openclaw/session",
    ".openclaw/config",
    "library/application support/openclaw",
)
FORBIDDEN_TEXT = (
    "raw/local_blobs",
    "local_blobs",
    ".openclaw-wiki",
    "openclaw wiki apply",
    "openclaw owns canonical",
    "openclaw is canonical",
    "openclaw has canonical authority",
    "canonical authority",
    "source of truth",
    "canonical truth",
    "canonical owner",
    "owns canonical truth",
    "unsafe_raw_text",
    "/users/",
    "\\users\\",
    "~/.openclaw",
    "~\\.openclaw",
    "%userprofile%",
    "%appdata%",
    "%localappdata%",
    "openclaw_home",
    "openclaw_config",
    "application support/openclaw",
    "application support\\openclaw",
    "openclaw/session",
    "openclaw\\session",
    "openclaw/config",
    "openclaw\\config",
    "\\.openclaw",
    ".openclaw\\",
    "c:\\",
    ".openclaw/",
    "../",
    "..\\",
    "private/",
    "private\\",
)
WRITEBACK_POLICY = {
    "read_surfaces": [
        "projections/openclaw/runtime-pack.json",
        "projections/openclaw/runtime-pack.md",
        "projections/openclaw/memory-prompt.md",
        "projections/openclaw/wiki-mirror/",
    ],
    "allowed_writeback_surfaces": [
        "raw/packets/",
        "mutations/pending/",
        ".tmp/writeback/",
        "ops/queue/",
        "ops/events/",
        "ops/gaps/",
        "ops/escalations/",
    ],
    "forbidden_surfaces": [
        "canonical/",
        "canonical/registry/",
        "digests/",
        "projections/openclaw/",
        ".openclaw-wiki/",
        "openclaw_private_config_session_credential_paths",
    ],
    "ops_events_policy": "semantic_events_only_no_queue_churn",
    "required_preconditions": ["canonical_rev", "subject_repo_id", "subject_head_sha"],
    "runtime_observation_authority": "runtime_observed",
    "canonical_write_path": "mutation_pack_only",
    "queue_semantics": "local_spool_single_filesystem",
    "wiki_policy": "read_only_mirror_no_openclaw_wiki_apply_authority",
}
PROJECTED_AUDIENCES = {"openclaw", "all"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_nonblank(value: str, field: str) -> None:
    if not value.strip():
        raise OpenClawComposeError(f"{field} is required")


def require_topology_state(root: Path, *, canonical_rev: str, allow_dirty: bool) -> None:
    state = read_git_state(root)
    if state.head_sha is None:
        if allow_dirty:
            return
        raise OpenClawComposeError("topology root must be a git repository before composing OpenClaw projection")
    if allow_dirty:
        return
    if not allow_dirty and state.dirty:
        raise OpenClawComposeError("topology repo must be clean before composing OpenClaw projection")
    if not allow_dirty and state.head_sha != canonical_rev:
        raise OpenClawComposeError("canonical_rev does not match current topology HEAD")


def subject_verified(subject_path: str | Path | None, *, subject_head_sha: str, allow_dirty: bool) -> bool:
    if subject_path is None:
        return False
    state = read_git_state(Path(subject_path))
    if state.head_sha is None:
        raise OpenClawComposeError("subject_path must be a git repository")
    if not allow_dirty and state.dirty:
        raise OpenClawComposeError("subject repo must be clean before composing OpenClaw projection")
    if not allow_dirty and state.head_sha != subject_head_sha:
        raise OpenClawComposeError("subject_head_sha does not match current subject HEAD")
    return True


def safe_openclaw_dir(paths: TopologyPaths) -> Path:
    projections = paths.root / "projections"
    openclaw = projections / "openclaw"
    wiki = openclaw / "wiki-mirror"
    pages = wiki / "pages"
    for directory in (projections, openclaw, wiki, pages):
        if directory.exists() and directory.is_symlink():
            raise OpenClawComposeError(f"OpenClaw projection directory must not be a symlink: {directory}")
    pages.mkdir(parents=True, exist_ok=True)
    for directory in (projections, openclaw, wiki, pages):
        resolved = directory.resolve()
        if directory != resolved:
            raise OpenClawComposeError(f"OpenClaw projection directory escaped lexical path: {directory}")
    return openclaw


def safe_output(openclaw_dir: Path, relative: str) -> Path:
    output = openclaw_dir / relative
    resolved = output.resolve()
    if resolved != output or openclaw_dir not in resolved.parents:
        raise OpenClawComposeError(f"OpenClaw projection output escaped projection root: {relative}")
    return output


def string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return sorted(item.strip() for item in value)


def safe_tags(value: Any) -> list[str] | None:
    values = string_list(value)
    if values is None:
        return None
    safe = [item for item in values if safe_text(item) is not None]
    return safe or None


def projected_audiences(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    safe = sorted({item.strip() for item in value if item.strip() in PROJECTED_AUDIENCES})
    return safe or None


def opaque_id_list(value: Any, prefix: str) -> list[str] | None:
    if not isinstance(value, list):
        return None
    ids = sorted(item.strip() for item in value if isinstance(item, str) and is_valid_id(item.strip(), prefix=prefix))
    return ids or None


def safe_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    folded = value.casefold()
    compact = re.sub(r"[^a-z0-9]", "", folded)
    if "openclaw" in compact:
        return None
    if any(token in folded for token in FORBIDDEN_TEXT):
        return None
    if "openclaw" in folded and "canonical" in folded:
        return None
    if "openclaw" in folded and any(token in folded for token in ("authority", "authoritative", "truth", "owns", "controls", "carries")):
        return None
    if "openclaw" in folded and any(token in folded for token in ("system of record", "controlling memory", "responsible for final", "deciding memory", "governs", "durable topology memory")):
        return None
    if "openclaw" in folded and any(token in folded for token in ("config", "credential", "credentials", "session", "secret", "token", "key")):
        return None
    return value.strip()


def safe_anchor_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    folded = raw.casefold().replace("\\", "/")
    compact = re.sub(r"[^a-z0-9]", "", folded)
    if "openclaw" in compact:
        return None
    if "\\" in raw or raw.startswith("~") or "%" in raw or folded.startswith("file:") or re.match(r"^[A-Za-z]:[\\/]", raw):
        return None
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        return None
    if any(part in folded for part in FORBIDDEN_ANCHOR_PATH_PARTS):
        return None
    return raw


def safe_metadata_value(value: str, field: str) -> str:
    require_nonblank(value, field)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        raise OpenClawComposeError(f"{field} must be a safe slug or revision token")
    folded = value.casefold()
    if any(token in folded for token in ("local_blobs", ".openclaw", "openclaw_config", "openclaw_token")):
        raise OpenClawComposeError(f"{field} contains forbidden projection text")
    return value


def safe_file_ref(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    clean_path = safe_anchor_path(item.get("path"))
    if clean_path is None:
        return None
    output: dict[str, Any] = {"path": clean_path}
    for field in FILE_REF_FIELDS:
        if field == "path" or field not in item:
            continue
        if field == "path_at_capture":
            safe = safe_anchor_path(item[field])
            if safe is not None:
                output[field] = safe
        elif field == "line_range":
            value = item[field]
            if isinstance(value, list) and len(value) == 2 and all(isinstance(part, int) and part > 0 for part in value):
                output[field] = value
        else:
            text = safe_text(item[field])
            if text is not None:
                output[field] = text
    return output


def visible_to_openclaw(record: dict[str, Any]) -> bool:
    record_type = record.get("type")
    if not isinstance(record_type, str) or record_type.strip() != record_type or record_type not in VALID_NODE_TYPES:
        return False
    if projected_audiences(record.get("audiences")) is None:
        return False
    if record.get("sensitivity") not in VALID_SENSITIVITY:
        return False
    if record.get("scope") not in VALID_SCOPE:
        return False
    if record.get("authority") not in VALID_AUTHORITY:
        return False
    if record.get("status") not in VALID_STATUS:
        return False
    if record.get("status") not in VISIBLE_STATUS:
        return False
    if record.get("sensitivity") == "operator_only" or record.get("scope") == "operator":
        return False
    if record_type == "operator_directive":
        return False
    if record_type == "runtime_observation" and record.get("authority") != "runtime_observed":
        return False
    return True


def runtime_record(record: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {"id": record.get("id") or record.get("node_id"), "kind": "node"}
    for field in RECORD_FIELDS:
        if field in {"id", "kind"} or field not in record:
            continue
        if field == "source_ids":
            values = opaque_id_list(record[field], "src")
            if values is not None:
                output[field] = values
        elif field in {"claim_ids", "basis_claim_ids"}:
            values = opaque_id_list(record[field], "clm")
            if values is not None:
                output[field] = values
        elif field == "tags":
            values = safe_tags(record[field])
            if values is not None:
                output[field] = values
        elif field == "file_refs":
            refs = [safe for item in record[field] if (safe := safe_file_ref(item)) is not None] if isinstance(record[field], list) else []
            if refs:
                output[field] = sorted(refs, key=lambda item: json.dumps(item, sort_keys=True))
        elif field in {"summary", "statement"}:
            text = safe_text(record[field])
            if text is not None:
                output[field] = text
        elif field in {"type", "status", "authority", "scope", "sensitivity", "confidence", "updated_at"}:
            text = safe_text(record[field])
            if text is not None:
                output[field] = text
        elif field == "audiences":
            audiences = projected_audiences(record[field])
            if audiences is not None:
                output[field] = audiences
        else:
            output[field] = record[field]
    return {field: output[field] for field in RECORD_FIELDS if field in output}


def projected_nodes(paths: TopologyPaths) -> list[dict[str, Any]]:
    records = []
    for row in read_jsonl(paths.resolve("canonical/registry/nodes.jsonl")):
        record_id = row.get("id") or row.get("node_id")
        if not isinstance(record_id, str) or not is_valid_id(record_id, prefix="nd"):
            continue
        if visible_to_openclaw(row):
            records.append(runtime_record(row))
    return sorted(records, key=lambda item: item["id"])


def metadata(
    *,
    project_id: str,
    canonical_rev: str,
    subject_repo_id: str,
    subject_head_sha: str,
    subject_state_verified: bool,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "subject_state_verified": subject_state_verified,
        "generated_at": generated_at,
    }


def wiki_page(record: dict[str, Any], meta: dict[str, Any]) -> str:
    title = record.get("summary") or record.get("statement") or record["id"]
    lines = [
        "---",
        f"id: {record['id']}",
        f"kind: {record['kind']}",
        "owner: knowledge-topology",
        "authority: derived",
        "write_policy: read_only",
        "source_ids: " + json.dumps(record.get("source_ids", [])),
        "sensitivity: " + str(record.get("sensitivity", "")),
        "audiences: " + json.dumps(record.get("audiences", [])),
        "canonical_rev: " + meta["canonical_rev"],
        "---",
        "",
        "# " + str(title),
        "",
        "READ ONLY: This page is derived from Knowledge Topology. Do not edit it as canonical memory.",
        "",
    ]
    if "summary" in record:
        lines.extend(["## Summary", "", str(record["summary"]), ""])
    elif "statement" in record:
        lines.extend(["## Statement", "", str(record["statement"]), ""])
    lines.extend(["## Source IDs", "", json.dumps(record.get("source_ids", [])), ""])
    if record.get("file_refs"):
        lines.extend(["## File Refs", "", json.dumps(record["file_refs"], indent=2, sort_keys=True), ""])
    return "\n".join(lines)


def render_runtime_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# OpenClaw Runtime Pack",
        "",
        "READ ONLY: This pack is derived from Knowledge Topology. OpenClaw is a runtime consumer, not canonical owner.",
        "",
        f"- Project: {pack['project_id']}",
        f"- Canonical revision: {pack['canonical_rev']}",
        f"- Subject: {pack['subject_repo_id']} @ {pack['subject_head_sha']}",
        f"- Subject state verified: {str(pack['subject_state_verified']).lower()}",
        "",
        "## Records",
        "",
    ]
    for record in pack["records"]:
        lines.append(f"- {record['id']} ({record.get('type', 'unknown')}, {record.get('authority', 'unknown')})")
    lines.extend(["", "## Writeback Policy", "", json.dumps(pack["writeback_policy"], indent=2, sort_keys=True), ""])
    return "\n".join(lines)


def render_memory_prompt(pack: dict[str, Any]) -> str:
    lines = [
        "# Knowledge Topology Runtime Context",
        "",
        "READ ONLY DERIVED ARTIFACT. OpenClaw consumes this projection; it does not own canonical truth.",
        "",
        "## Projection Metadata",
        "",
        f"- project_id: {pack['project_id']}",
        f"- canonical_rev: {pack['canonical_rev']}",
        f"- subject_repo_id: {pack['subject_repo_id']}",
        f"- subject_head_sha: {pack['subject_head_sha']}",
        f"- subject_state_verified: {str(pack['subject_state_verified']).lower()}",
        f"- generated_at: {pack['generated_at']}",
        "",
        "## Runtime Instructions",
        "",
        "Use these records as runtime context. Return durable changes through mutation packs; do not edit canonical topology or this generated projection.",
        "",
        "## Records Summary",
        "",
    ]
    for record in pack["records"]:
        text = record.get("summary") or record.get("statement") or ""
        lines.append(f"- {record['id']}: {text}")
    lines.extend(["", "## Open Gaps", "", json.dumps(pack["open_gaps"], indent=2, sort_keys=True), ""])
    lines.extend(["## Writeback Policy", "", json.dumps(pack["writeback_policy"], indent=2, sort_keys=True), ""])
    return "\n".join(lines)


def write_openclaw_projection(
    root: str | Path,
    *,
    project_id: str,
    canonical_rev: str,
    subject_repo_id: str,
    subject_head_sha: str,
    subject_path: str | Path | None = None,
    allow_dirty: bool = False,
    clock: Callable[[], str] = utc_now,
) -> Path:
    for field, value in {
        "project_id": project_id,
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
    }.items():
        safe_metadata_value(value, field)
    paths = TopologyPaths.from_root(root)
    require_topology_state(paths.root, canonical_rev=canonical_rev, allow_dirty=allow_dirty)
    verified = subject_verified(subject_path, subject_head_sha=subject_head_sha, allow_dirty=allow_dirty)
    generated_at = clock()
    meta = metadata(
        project_id=project_id,
        canonical_rev=canonical_rev,
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        subject_state_verified=verified,
        generated_at=generated_at,
    )
    records = projected_nodes(paths)
    pack = {
        **meta,
        "records": records,
        "open_gaps": [],
        "pending_escalations": [],
        "writeback_policy": WRITEBACK_POLICY,
    }

    openclaw_dir = safe_openclaw_dir(paths)
    pages_dir = openclaw_dir / "wiki-mirror/pages"
    for stale in pages_dir.iterdir():
        if stale.is_symlink() or stale.is_file():
            stale.unlink()
        elif stale.is_dir():
            shutil.rmtree(stale)
    page_entries = []
    for record in records:
        relative = f"wiki-mirror/pages/{record['id']}.md"
        page_entries.append({
            "id": record["id"],
            "kind": record["kind"],
            "path": f"pages/{record['id']}.md",
            "source_ids": record.get("source_ids", []),
            "sensitivity": record.get("sensitivity"),
            "audiences": record.get("audiences", []),
        })
        atomic_write_text(safe_output(openclaw_dir, relative), wiki_page(record, meta) + "\n")
    manifest = {
        "schema_version": "1.0",
        "owner": "knowledge-topology",
        "authority": "derived",
        "write_policy": "read_only",
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "subject_state_verified": verified,
        "generated_at": generated_at,
        "pages": sorted(page_entries, key=lambda item: item["id"]),
    }
    atomic_write_text(safe_output(openclaw_dir, "runtime-pack.json"), json.dumps(pack, indent=2, sort_keys=True) + "\n")
    atomic_write_text(safe_output(openclaw_dir, "runtime-pack.md"), render_runtime_markdown(pack) + "\n")
    atomic_write_text(safe_output(openclaw_dir, "memory-prompt.md"), render_memory_prompt(pack) + "\n")
    atomic_write_text(safe_output(openclaw_dir, "wiki-mirror/manifest.json"), json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    # Keep directory materialized even when there are no visible records.
    pages_dir.mkdir(parents=True, exist_ok=True)
    return openclaw_dir
