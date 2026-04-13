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
from knowledge_topology.schema.mutation_pack import HUMAN_GATE_CLASSES
from knowledge_topology.storage.registry import RegistryError, read_jsonl
from knowledge_topology.storage.transaction import atomic_write_text


class OpenClawComposeError(ValueError):
    """Raised when OpenClaw projection cannot be compiled safely."""


VALID_SENSITIVITY = {"public", "internal", "operator_only", "runtime_only"}
VALID_SCOPE = {"global", "repo", "operator", "runtime"}
VALID_AUTHORITY = {"source_grounded", "repo_observed", "runtime_observed", "fitz_curated", "model_inferred"}
VALID_STATUS = {"draft", "active", "contested", "superseded", "rejected"}
VISIBLE_STATUS = {"active", "draft", "contested"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
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
    "source_ids",
    "claim_ids",
    "basis_claim_ids",
    "updated_at",
]
FORBIDDEN_SLUG_TOKENS = (
    "ignore",
    "disregard",
    "override",
    "bypass",
    "disable",
    "delete",
    "write",
    "apply",
    "execute",
    "shell",
    "command",
    "canonical",
    "policy",
    "gate",
    "human",
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
        if directory.is_symlink():
            raise OpenClawComposeError(f"OpenClaw projection directory must not be a symlink: {directory}")
        if directory.exists() and not directory.is_dir():
            raise OpenClawComposeError(f"OpenClaw projection path must be a directory: {directory}")
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
    if output.exists() and not output.is_file():
        raise OpenClawComposeError(f"OpenClaw projection output target must be a file: {relative}")
    return output


def string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return sorted(item.strip() for item in value)


def projected_audiences(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    safe = sorted({item.strip() for item in value if item.strip() in PROJECTED_AUDIENCES})
    return safe or None


def safe_read_jsonl(paths: TopologyPaths, relative: str, label: str) -> list[dict[str, Any]]:
    path = paths.root / relative
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OpenClawComposeError(f"{label} registry is invalid: input must be a regular file")
    try:
        return read_jsonl(path)
    except (OSError, RegistryError) as exc:
        raise OpenClawComposeError(f"{label} registry is invalid: {exc}") from exc


def opaque_id_list(value: Any, prefix: str) -> list[str] | None:
    if not isinstance(value, list):
        return None
    ids = sorted(item.strip() for item in value if isinstance(item, str) and is_valid_id(item.strip(), prefix=prefix))
    return ids or None


def safe_metadata_value(value: str, field: str) -> str:
    require_nonblank(value, field)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        raise OpenClawComposeError(f"{field} must be a safe slug or revision token")
    folded = value.casefold()
    compact = re.sub(r"[^a-z0-9]", "", folded)
    if any(token in folded for token in ("local_blobs", ".openclaw", "openclaw_config", "openclaw_token")):
        raise OpenClawComposeError(f"{field} contains forbidden projection text")
    if any(token in compact for token in FORBIDDEN_SLUG_TOKENS):
        raise OpenClawComposeError(f"{field} contains forbidden projection text")
    return value


def safe_timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T[0-9:.-]+Z", value):
        raise OpenClawComposeError(f"{field} must be a UTC timestamp")
    return value


def visible_to_openclaw(record: dict[str, Any]) -> bool:
    record_type = record.get("type")
    if not isinstance(record_type, str) or record_type.strip() != record_type or record_type not in VALID_NODE_TYPES:
        return False
    if projected_audiences(record.get("audiences")) is None:
        return False
    sensitivity = record.get("sensitivity")
    scope = record.get("scope")
    authority = record.get("authority")
    status = record.get("status")
    if not isinstance(sensitivity, str) or sensitivity not in VALID_SENSITIVITY:
        return False
    if not isinstance(scope, str) or scope not in VALID_SCOPE:
        return False
    if not isinstance(authority, str) or authority not in VALID_AUTHORITY:
        return False
    if not isinstance(status, str) or status not in VALID_STATUS:
        return False
    if status not in VISIBLE_STATUS:
        return False
    if sensitivity == "operator_only" or scope == "operator":
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
        elif field in {"type", "status", "authority", "scope", "sensitivity"}:
            if isinstance(record[field], str):
                output[field] = record[field]
        elif field == "confidence":
            if record[field] in CONFIDENCE_VALUES:
                output[field] = record[field]
        elif field == "updated_at":
            if isinstance(record[field], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T[0-9:.-]+Z", record[field]):
                output[field] = record[field]
        elif field == "audiences":
            audiences = projected_audiences(record[field])
            if audiences is not None:
                output[field] = audiences
        else:
            output[field] = record[field]
    return {field: output[field] for field in RECORD_FIELDS if field in output}


def projected_nodes(paths: TopologyPaths) -> list[dict[str, Any]]:
    records = []
    rows = safe_read_jsonl(paths, "canonical/registry/nodes.jsonl", "nodes")
    for row in rows:
        record_id = row.get("id") or row.get("node_id")
        if not isinstance(record_id, str) or not is_valid_id(record_id, prefix="nd"):
            continue
        if visible_to_openclaw(row):
            records.append(runtime_record(row))
    return sorted(records, key=lambda item: item["id"])


def visible_labeled_record(record: dict[str, Any]) -> bool:
    if projected_audiences(record.get("audiences")) is None:
        return False
    sensitivity = record.get("sensitivity")
    scope = record.get("scope")
    authority = record.get("authority")
    status = record.get("status")
    if not isinstance(sensitivity, str) or sensitivity not in VALID_SENSITIVITY:
        return False
    if not isinstance(scope, str) or scope not in VALID_SCOPE:
        return False
    if not isinstance(authority, str) or authority not in VALID_AUTHORITY:
        return False
    if not isinstance(status, str) or status not in VISIBLE_STATUS:
        return False
    if sensitivity == "operator_only" or scope == "operator":
        return False
    return True


def projected_gap(record: dict[str, Any], visible_node_ids: set[str]) -> dict[str, Any] | None:
    if not visible_labeled_record(record):
        return None
    gap_id = record.get("gap_id")
    digest_id = record.get("digest_id")
    target_id = record.get("target_id")
    if not isinstance(gap_id, str) or not is_valid_id(gap_id, prefix="gap"):
        return None
    if not isinstance(digest_id, str) or not is_valid_id(digest_id, prefix="dg"):
        return None
    if target_id != "NEW" and (not isinstance(target_id, str) or not is_valid_id(target_id, prefix="nd")):
        return None
    if target_id != "NEW" and target_id not in visible_node_ids:
        return None
    output = {
        "gap_id": gap_id,
        "target_id": target_id,
        "digest_id": digest_id,
        "status": record["status"],
        "audiences": projected_audiences(record["audiences"]),
        "sensitivity": record["sensitivity"],
    }
    source_ids = opaque_id_list(record.get("source_ids", []), "src")
    if source_ids is not None:
        output["source_ids"] = source_ids
    return output


def projected_escalation(record: dict[str, Any]) -> dict[str, Any] | None:
    if not visible_labeled_record(record):
        return None
    escalation_id = record.get("id")
    if not isinstance(escalation_id, str) or not is_valid_id(escalation_id, prefix="esc"):
        return None
    gate = record.get("human_gate_class")
    if not isinstance(gate, str) or gate not in HUMAN_GATE_CLASSES:
        return None
    output = {
        "id": escalation_id,
        "status": record["status"],
        "audiences": projected_audiences(record["audiences"]),
        "sensitivity": record["sensitivity"],
        "human_gate_class": gate,
    }
    source_ids = opaque_id_list(record.get("source_ids", []), "src")
    if source_ids is not None:
        output["source_ids"] = source_ids
    return output


def projected_gaps(paths: TopologyPaths, visible_node_ids: set[str]) -> list[dict[str, Any]]:
    rows = safe_read_jsonl(paths, "ops/gaps/open.jsonl", "open gaps")
    gaps = [gap for row in rows if (gap := projected_gap(row, visible_node_ids)) is not None]
    return sorted(gaps, key=lambda item: item["gap_id"])


def projected_escalations(paths: TopologyPaths) -> list[dict[str, Any]]:
    escalations = []
    directory = paths.root / "ops/escalations"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise OpenClawComposeError("escalation input directory is invalid: input must be a regular directory")
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise OpenClawComposeError(f"escalation input must be a regular file: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and (projected := projected_escalation(payload)) is not None:
            escalations.append(projected)
    return sorted(escalations, key=lambda item: item["id"])


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
    title = record["id"]
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
    lines.extend(["## Record Metadata", "", f"- type: {record.get('type', '')}", f"- authority: {record.get('authority', '')}", ""])
    lines.extend(["## Source IDs", "", json.dumps(record.get("source_ids", [])), ""])
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
        lines.append(f"- {record['id']} ({record.get('type', 'unknown')}, {record.get('authority', 'unknown')})")
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
    generated_at = safe_timestamp(clock(), "generated_at")
    meta = metadata(
        project_id=project_id,
        canonical_rev=canonical_rev,
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        subject_state_verified=verified,
        generated_at=generated_at,
    )
    records = projected_nodes(paths)
    visible_node_ids = {record["id"] for record in records}
    pack = {
        **meta,
        "records": records,
        "open_gaps": projected_gaps(paths, visible_node_ids),
        "pending_escalations": projected_escalations(paths),
        "writeback_policy": WRITEBACK_POLICY,
    }

    openclaw_dir = safe_openclaw_dir(paths)
    pages_dir = openclaw_dir / "wiki-mirror/pages"
    runtime_json = safe_output(openclaw_dir, "runtime-pack.json")
    runtime_md = safe_output(openclaw_dir, "runtime-pack.md")
    memory_prompt = safe_output(openclaw_dir, "memory-prompt.md")
    manifest_json = safe_output(openclaw_dir, "wiki-mirror/manifest.json")
    page_outputs = [(record, safe_output(openclaw_dir, f"wiki-mirror/pages/{record['id']}.md")) for record in records]

    for stale in pages_dir.iterdir():
        if stale.is_symlink() or stale.is_file():
            stale.unlink()
        elif stale.is_dir():
            shutil.rmtree(stale)
        else:
            stale.unlink()
    page_entries = []
    for record, page_output in page_outputs:
        page_entries.append({
            "id": record["id"],
            "kind": record["kind"],
            "path": f"pages/{record['id']}.md",
            "source_ids": record.get("source_ids", []),
            "sensitivity": record.get("sensitivity"),
            "audiences": record.get("audiences", []),
        })
        atomic_write_text(page_output, wiki_page(record, meta) + "\n")
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
    atomic_write_text(runtime_json, json.dumps(pack, indent=2, sort_keys=True) + "\n")
    atomic_write_text(runtime_md, render_runtime_markdown(pack) + "\n")
    atomic_write_text(memory_prompt, render_memory_prompt(pack) + "\n")
    atomic_write_text(manifest_json, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    # Keep directory materialized even when there are no visible records.
    pages_dir.mkdir(parents=True, exist_ok=True)
    return openclaw_dir
