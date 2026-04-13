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
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.storage.registry import read_jsonl
from knowledge_topology.storage.transaction import atomic_write_text


class ComposeError(ValueError):
    """Raised when builder pack composition fails."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def visible_to_builders(record: dict[str, Any]) -> bool:
    audiences = record.get("audiences")
    sensitivity = record.get("sensitivity")
    scope = record.get("scope")
    record_type = record.get("type")
    status = record.get("status")
    if audiences is None or "builders" not in audiences:
        return False
    if scope in {"operator", "runtime"}:
        return False
    if record_type in {"operator_directive", "runtime_observation"}:
        return False
    if sensitivity in {"operator_only", "runtime_only"}:
        return False
    if status is not None and status not in {"active", "draft", "contested"}:
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


def load_applied_state(paths: TopologyPaths) -> dict[str, list[dict[str, Any]]]:
    return {
        "claims": read_jsonl(paths.resolve("canonical/registry/claims.jsonl")),
        "edges": read_jsonl(paths.resolve("canonical/registry/edges.jsonl")),
        "nodes": read_jsonl(paths.resolve("canonical/registry/nodes.jsonl")),
        "gaps": read_jsonl(paths.resolve("ops/gaps/open.jsonl")),
    }


def constraints_for(nodes: list[dict[str, Any]]) -> dict[str, Any]:
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
    return {"invariants": invariants, "count": len(invariants)}


def public_record(record: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {field: record[field] for field in fields if field in record}


def public_bundle(claims: list[dict[str, Any]], edges: list[dict[str, Any]], nodes: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "claims": [public_record(item, ["claim_id", "statement", "status", "audiences", "source_ids", "digest_id"]) for item in claims],
        "edges": [public_record(item, ["edge_id", "edge_type", "from_id", "to_id", "confidence", "status", "audiences", "basis_digest_id"]) for item in edges],
        "nodes": [public_record(item, ["id", "node_id", "type", "status", "audiences", "source_ids", "claim_ids", "tags"]) for item in nodes],
        "gaps": [public_record(item, ["gap_id", "summary", "reason", "status", "audiences", "digest_id", "target_id"]) for item in gaps],
    }


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
                "evidence_refs": node.get("source_ids", []),
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

    pack_dir = paths.ensure_dir(f"projections/tasks/{safe_task_id}")
    metadata = {
        "task_id": safe_task_id,
        "goal": goal,
        "canonical_rev": canonical_rev,
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "generated_at": utc_now(),
        "stale_when": ["canonical_rev changes", "subject_head_sha changes"],
    }
    constraints = constraints_for(nodes)
    source_bundle = public_bundle(claims, edges, nodes, gaps)
    writeback_targets = {
        "mutation_surface": "mutations/pending/",
        "required_summary_fields": ["decisions", "invariants", "interfaces", "runtime_assumptions", "tests_run"],
    }
    brief = "\n".join([
        f"# Builder Brief: {task_id}",
        "",
        goal,
        "",
        f"- Claims: {len(claims)}",
        f"- Edges: {len(edges)}",
        f"- Nodes: {len(nodes)}",
        f"- Open gaps: {len(gaps)}",
        "",
    ])

    atomic_write_text(pack_dir / "metadata.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    atomic_write_text(pack_dir / "constraints.json", json.dumps(constraints, indent=2, sort_keys=True) + "\n")
    atomic_write_text(pack_dir / "relationship-tests.yaml", relationship_tests_for(nodes))
    atomic_write_text(pack_dir / "source-bundle.json", json.dumps(source_bundle, indent=2, sort_keys=True) + "\n")
    atomic_write_text(pack_dir / "writeback-targets.json", json.dumps(writeback_targets, indent=2, sort_keys=True) + "\n")
    atomic_write_text(pack_dir / "brief.md", brief)
    return pack_dir
