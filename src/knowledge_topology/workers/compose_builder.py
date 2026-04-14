"""P6 deterministic builder pack compiler."""

from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_topology.git_state import read_git_state
from knowledge_topology.ids import CROCKFORD32
from knowledge_topology.ids import is_valid_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.storage.registry import RegistryError
from knowledge_topology.storage.registry import read_jsonl
from knowledge_topology.storage.transaction import atomic_write_text


class ComposeError(ValueError):
    """Raised when builder pack composition fails."""


VISIBLE_STATUS = {"active", "draft", "contested"}
VISIBLE_CONFIDENCE = {"high", "medium", "low"}
FORBIDDEN_FILE_REF_TOKENS = {
    "ignore",
    "read-only",
    "banner",
    "mutate",
    "bash",
    "append",
    "canonical",
    "registry",
    "disregard",
    "instructions",
    "override",
    "policy",
    "bypass",
    "apply",
    "gate",
    "write-directly",
    "delete",
    "execute",
    "shell",
    "command",
}
ID_LIST_FIELDS = {"source_ids", "claim_ids", "basis_claim_ids"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def visible_to_builders(record: dict[str, Any]) -> bool:
    audiences = record.get("audiences")
    sensitivity = record.get("sensitivity")
    scope = record.get("scope")
    record_type = record.get("type")
    status = record.get("status")
    if not isinstance(audiences, list) or "builders" not in audiences:
        return False
    if scope in {"operator", "runtime"}:
        return False
    if record_type in {"operator_directive", "runtime_observation"}:
        return False
    if sensitivity in {"operator_only", "runtime_only"}:
        return False
    if not isinstance(status, str) or status not in VISIBLE_STATUS:
        return False
    return True


def bounded(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(records, key=lambda item: json.dumps(item, sort_keys=True))[:limit]


def sanitize_task_id(task_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", task_id):
        raise ComposeError("task_id must be a safe slug using letters, numbers, dot, underscore, or dash")
    if ".." in task_id or "/" in task_id or "\\" in task_id:
        raise ComposeError("task_id must not contain path traversal")
    return task_id


def require_clean_git(root: Path, *, allow_dirty: bool) -> None:
    if allow_dirty:
        return
    state = read_git_state(root)
    if state.head_sha is not None and state.dirty:
        raise ComposeError("topology repo must be clean before composing builder pack")


def require_subject_clean(subject_path: str | Path | None, *, allow_dirty: bool) -> None:
    if allow_dirty or subject_path is None:
        return
    state = read_git_state(Path(subject_path))
    if state.head_sha is not None and state.dirty:
        raise ComposeError("subject repo must be clean before composing builder pack")


def deterministic_reltest_id(node_id: str) -> str:
    digest = hashlib.sha256(node_id.encode("utf-8")).digest()
    value = int.from_bytes(digest[:17], "big") >> 6
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD32[value & 31])
        value >>= 5
    return "reltest_" + "".join(reversed(chars))


def safe_pack_dir(paths: TopologyPaths, task_id: str) -> Path:
    projections_dir = paths.root / "projections"
    tasks_root = projections_dir / "tasks"
    for path in (projections_dir, tasks_root):
        if path.exists() and path.is_symlink():
            raise ComposeError("builder projection directories must not be symlinks")
    projections_dir.mkdir(parents=True, exist_ok=True)
    tasks_root.mkdir(parents=True, exist_ok=True)
    if projections_dir.resolve() != projections_dir or tasks_root.resolve() != tasks_root:
        raise ComposeError("builder projection directories must stay on their lexical paths")
    task_path = tasks_root / task_id
    if task_path.exists() and task_path.is_symlink():
        raise ComposeError("builder pack task directory must not be a symlink")
    task_path.mkdir(parents=True, exist_ok=True)
    resolved = task_path.resolve()
    if resolved != task_path or resolved.parent != tasks_root:
        raise ComposeError("builder pack directory must stay under projections/tasks")
    return task_path


def safe_output(pack_dir: Path, filename: str) -> Path:
    output = pack_dir / filename
    resolved = output.resolve()
    if resolved.parent != pack_dir:
        raise ComposeError("builder pack output path escaped task directory")
    return output


def load_applied_state(paths: TopologyPaths) -> dict[str, list[dict[str, Any]]]:
    return {
        "claims": read_jsonl(paths.resolve("canonical/registry/claims.jsonl")),
        "edges": read_jsonl(paths.resolve("canonical/registry/edges.jsonl")),
        "nodes": read_jsonl(paths.resolve("canonical/registry/nodes.jsonl")),
        "gaps": read_jsonl(paths.resolve("ops/gaps/open.jsonl")),
        "file_refs": safe_read_jsonl(paths, "canonical/registry/file_refs.jsonl", "file refs"),
    }


def preflight_input_path(paths: TopologyPaths, relative: str, label: str) -> Path:
    path = paths.root / relative
    current = paths.root
    for part in Path(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ComposeError(f"{label} input path is invalid: parent must not be a symlink")
        if current.exists() and not current.is_dir():
            raise ComposeError(f"{label} input path is invalid: parent must be a directory")
    if path.is_symlink():
        raise ComposeError(f"{label} input path is invalid: input must not be a symlink")
    if path.exists() and not path.is_file():
        raise ComposeError(f"{label} registry is invalid: input must be a regular file")
    return path


def safe_read_jsonl(paths: TopologyPaths, relative: str, label: str) -> list[dict[str, Any]]:
    path = preflight_input_path(paths, relative, label)
    try:
        return read_jsonl(path)
    except (OSError, RegistryError) as exc:
        raise ComposeError(f"{label} registry is invalid: {exc}") from exc


def normalize_token_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def safe_file_ref_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    folded = raw.casefold().replace("\\", "/")
    normalized = normalize_token_text(raw)
    if (
        "\\" in raw
        or raw.startswith("~")
        or "%" in raw
        or folded.startswith("file:")
        or re.match(r"^[A-Za-z]:[\\/]", raw)
    ):
        return None
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        return None
    if folded == "canonical" or folded.startswith("canonical/") or folded.startswith("projections/"):
        return None
    if any(marker in folded for marker in ("raw/local_blobs", "local_blobs", ".tmp", ".openclaw", "private", "cache")):
        return None
    if any(token in normalized for token in FORBIDDEN_FILE_REF_TOKENS):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_./@+-]+", raw):
        return None
    if "/" not in raw and "." not in raw:
        return None
    return raw


def safe_file_ref(row: dict[str, Any], *, subject_repo_id: str, subject_head_sha: str) -> dict[str, Any] | None:
    if row.get("repo_id") != subject_repo_id or row.get("commit_sha") != subject_head_sha:
        return None
    path = safe_file_ref_path(row.get("path"))
    if path is None:
        return None
    output: dict[str, Any] = {"repo_id": subject_repo_id, "commit_sha": subject_head_sha, "path": path}
    line_range = row.get("line_range")
    if (
        isinstance(line_range, list)
        and len(line_range) == 2
        and all(isinstance(part, int) and part > 0 for part in line_range)
    ):
        output["line_range"] = line_range
    symbol = row.get("symbol")
    if isinstance(symbol, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]{0,120}", symbol):
        output["symbol"] = symbol
    if row.get("anchor_kind") in {"symbol", "line", "excerpt"}:
        output["anchor_kind"] = row["anchor_kind"]
    excerpt_hash = row.get("excerpt_hash")
    if isinstance(excerpt_hash, str) and re.fullmatch(r"[0-9A-Fa-f]{8,128}", excerpt_hash):
        output["excerpt_hash"] = excerpt_hash
    verified_at = row.get("verified_at")
    if isinstance(verified_at, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T[0-9:.-]+Z", verified_at):
        output["verified_at"] = verified_at
    return output


def safe_row(record: dict[str, Any]) -> dict[str, Any]:
    title = record.get("summary") or record.get("statement") or record.get("reason") or record.get("contract")
    output = {field: record[field] for field in ["type", "status", "authority"] if field in record}
    record_id = record.get("id") or record.get("node_id")
    if isinstance(record_id, str):
        output["id"] = record_id
    source_ids = safe_id_list(record.get("source_ids"))
    if source_ids:
        output["source_ids"] = source_ids
    if isinstance(title, str) and title.strip():
        output["title"] = " ".join(title.strip().split())[:160]
    return output


def safe_id_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(item for item in value if isinstance(item, str) and is_valid_id(item))


def constraints_for(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    file_refs: list[dict[str, Any]],
    *,
    subject_repo_id: str,
    subject_head_sha: str,
) -> dict[str, Any]:
    invariants = [
        {
            "id": node.get("id") or node.get("node_id"),
            "type": node.get("type"),
            "status": node.get("status"),
            "source": "canonical/registry/nodes.jsonl",
        }
        for node in nodes
        if node.get("type") == "invariant"
    ]
    interfaces = [
        {
            "id": node.get("id") or node.get("node_id"),
            "status": node.get("status"),
            "source_ids": safe_id_list(node.get("source_ids")),
        }
        for node in nodes
        if node.get("type") == "interface"
    ]
    visible_node_ids = {
        node.get("id") or node.get("node_id")
        for node in nodes
        if isinstance(node.get("id") or node.get("node_id"), str)
    }
    contradiction_pressure = contradiction_edges(edges, visible_node_ids)
    safe_refs = [
        safe
        for item in file_refs
        if (safe := safe_file_ref(
            item,
            subject_repo_id=subject_repo_id,
            subject_head_sha=subject_head_sha,
        )) is not None
    ]
    safe_refs = sorted(safe_refs, key=lambda item: item["path"])[:20]
    invariants = sorted(invariants, key=lambda item: item["id"])[:10]
    interfaces = sorted(interfaces, key=lambda item: item["id"])[:10]
    contradiction_pressure = contradiction_pressure[:10]
    return {
        "invariants": invariants,
        "interfaces": interfaces,
        "file_refs": safe_refs,
        "contradiction_pressure": contradiction_pressure,
        "count": len(invariants),
        "counts": {
            "invariants": len(invariants),
            "interfaces": len(interfaces),
            "file_refs": len(safe_refs),
            "contradiction_pressure": len(contradiction_pressure),
        },
    }


def contradiction_edges(edges: list[dict[str, Any]], visible_node_ids: set[str]) -> list[dict[str, Any]]:
    output = []
    for edge in edges:
        edge_type = edge.get("type") or edge.get("edge_type")
        edge_id = edge.get("id") or edge.get("edge_id")
        if edge_type not in {"CONTRADICTS", "DIVERGES_FROM"}:
            continue
        if edge.get("status") not in VISIBLE_STATUS or edge.get("confidence") not in VISIBLE_CONFIDENCE:
            continue
        from_id = edge.get("from_id")
        to_id = edge.get("to_id")
        if not valid_edge_endpoint(from_id, visible_node_ids) or not valid_edge_endpoint(to_id, visible_node_ids):
            continue
        if not isinstance(edge_id, str) or not (is_valid_id(edge_id, prefix="edg") or edge_id.startswith("edge_")):
            continue
        output.append({
            "id": edge_id,
            "type": edge_type,
            "from_id": from_id,
            "to_id": to_id,
            "confidence": edge["confidence"],
            "basis_claim_ids": safe_id_list(edge.get("basis_claim_ids")),
            "source_ids": safe_id_list(edge.get("source_ids")),
        })
    return sorted(output, key=lambda item: item["id"])


def valid_edge_endpoint(value: Any, visible_node_ids: set[str]) -> bool:
    if not isinstance(value, str) or "_" not in value:
        return False
    prefix = value.split("_", 1)[0]
    if prefix == "nd":
        return value in visible_node_ids
    return prefix == "src" and is_valid_id(value, prefix="src")


def public_record(record: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in fields:
        if field not in record:
            continue
        if field in ID_LIST_FIELDS:
            output[field] = safe_id_list(record[field])
        else:
            output[field] = record[field]
    return output


def public_bundle(claims: list[dict[str, Any]], edges: list[dict[str, Any]], nodes: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "claims": [public_record(item, ["claim_id", "statement", "status", "audiences", "source_ids", "digest_id"]) for item in claims],
        "edges": [public_record(item, ["edge_id", "edge_type", "from_id", "to_id", "confidence", "status", "audiences", "basis_digest_id"]) for item in edges],
        "nodes": [public_record(item, ["id", "node_id", "type", "status", "audiences", "source_ids", "claim_ids", "tags"]) for item in nodes],
        "gaps": [public_record(item, ["gap_id", "summary", "reason", "status", "audiences", "digest_id", "target_id"]) for item in gaps],
    }


def brief_for(
    task_id: str,
    goal: str,
    metadata: dict[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> str:
    decisions = sorted(
        [safe_row(node) for node in nodes if node.get("type") == "decision"],
        key=lambda item: item.get("id", ""),
    )[:10]
    invariants = sorted(
        [safe_row(node) for node in nodes if node.get("type") == "invariant"],
        key=lambda item: item.get("id", ""),
    )[:10]
    interfaces = sorted(
        [safe_row(node) for node in nodes if node.get("type") == "interface"],
        key=lambda item: item.get("id", ""),
    )[:10]
    visible_ids = {
        node.get("id") or node.get("node_id")
        for node in nodes
        if isinstance(node.get("id") or node.get("node_id"), str)
    }
    pressure = contradiction_edges(edges, visible_ids)[:10]
    gap_rows = sorted(
        [
            public_record(gap, ["gap_id", "summary", "status", "audiences", "digest_id", "target_id"])
            for gap in gaps
        ],
        key=lambda item: item.get("gap_id", ""),
    )[:10]
    sections = [
        f"# Builder Brief: {task_id}",
        "",
        "## Task Goal",
        "",
        goal,
        "",
        "## Revision Preconditions",
        "",
        f"- canonical_rev: {metadata['canonical_rev']}",
        f"- subject_repo_id: {metadata['subject_repo_id']}",
        f"- subject_head_sha: {metadata['subject_head_sha']}",
        "",
        "## Key Decisions",
        "",
        json.dumps(decisions, indent=2, sort_keys=True),
        "",
        "## Invariants",
        "",
        json.dumps(invariants, indent=2, sort_keys=True),
        "",
        "## Interfaces",
        "",
        json.dumps(interfaces, indent=2, sort_keys=True),
        "",
        "## Contradiction Pressure",
        "",
        json.dumps(pressure, indent=2, sort_keys=True),
        "",
        "## Open Gaps",
        "",
        json.dumps(gap_rows, indent=2, sort_keys=True),
        "",
        "## Writeback Reminder",
        "",
        "At task end, write back decisions, invariants, interfaces, runtime_assumptions, "
        "tests_run, commands_run, file_refs, conflicts, and task_lessons.",
        "",
    ]
    return "\n".join(sections)


def relationship_tests_for(nodes: list[dict[str, Any]]) -> str:
    tests = []
    for node in nodes:
        node_id = node.get("id") or node.get("node_id")
        if node.get("type") == "invariant" and node_id:
            tests.append({
                "schema_version": "1.0",
                "id": deterministic_reltest_id(node_id),
                "invariant_node_id": node_id,
                "property": "Invariant remains satisfied by implementation.",
                "evidence_refs": safe_id_list(node.get("source_ids")),
                "suggested_test_shape": "unit",
                "failure_if": ["implementation violates invariant"],
                "status": "draft",
            })
    if not tests:
        return "[]\n"
    lines = []
    for item in tests:
        lines.append("- schema_version: " + item["schema_version"])
        lines.append("  id: " + item["id"])
        lines.append("  invariant_node_id: " + item["invariant_node_id"])
        lines.append("  property: " + json.dumps(item["property"]))
        lines.append("  evidence_refs: " + json.dumps(item["evidence_refs"]))
        lines.append("  suggested_test_shape: " + item["suggested_test_shape"])
        lines.append("  failure_if: " + json.dumps(item["failure_if"]))
        lines.append("  status: " + item["status"])
    return "\n".join(lines) + "\n"


def write_builder_pack(
    root: str | Path,
    *,
    task_id: str,
    goal: str,
    canonical_rev: str,
    subject_repo_id: str,
    subject_head_sha: str,
    subject_path: str | Path | None = None,
    allow_dirty: bool = False,
) -> Path:
    for field, value in {
        "task_id": task_id,
        "goal": goal,
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
    }.items():
        if not value.strip():
            raise ComposeError(f"{field} is required")

    safe_task_id = sanitize_task_id(task_id)
    paths = TopologyPaths.from_root(root)
    require_clean_git(paths.root, allow_dirty=allow_dirty)
    require_subject_clean(subject_path, allow_dirty=allow_dirty)
    state = load_applied_state(paths)
    claims = bounded([item for item in state["claims"] if visible_to_builders(item)], 40)
    edges = bounded([item for item in state["edges"] if visible_to_builders(item)], 40)
    nodes = bounded([item for item in state["nodes"] if visible_to_builders(item)], 40)
    gaps = bounded([item for item in state["gaps"] if visible_to_builders(item)], 20)

    pack_dir = safe_pack_dir(paths, safe_task_id)
    metadata = {
        "task_id": safe_task_id,
        "goal": goal,
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "generated_at": utc_now(),
        "stale_when": ["canonical_rev changes", "subject_head_sha changes"],
    }
    constraints = constraints_for(
        nodes,
        state["edges"],
        state["file_refs"],
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
    )
    source_bundle = public_bundle(claims, edges, nodes, gaps)
    writeback_targets = {
        "mutation_surface": "mutations/pending/",
        "required_summary_fields": ["source_id", "digest_id"],
        "accepted_candidate_fields": [
            "decisions",
            "invariants",
            "interfaces",
            "runtime_assumptions",
            "task_lessons",
            "tests_run",
            "commands_run",
            "file_refs",
            "conflicts",
        ],
    }
    brief = brief_for(safe_task_id, goal, metadata, nodes, edges, gaps)

    atomic_write_text(safe_output(pack_dir, "metadata.json"), json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    atomic_write_text(safe_output(pack_dir, "constraints.json"), json.dumps(constraints, indent=2, sort_keys=True) + "\n")
    atomic_write_text(safe_output(pack_dir, "relationship-tests.yaml"), relationship_tests_for(nodes))
    atomic_write_text(safe_output(pack_dir, "source-bundle.json"), json.dumps(source_bundle, indent=2, sort_keys=True) + "\n")
    atomic_write_text(safe_output(pack_dir, "writeback-targets.json"), json.dumps(writeback_targets, indent=2, sort_keys=True) + "\n")
    atomic_write_text(safe_output(pack_dir, "brief.md"), brief)
    return pack_dir
