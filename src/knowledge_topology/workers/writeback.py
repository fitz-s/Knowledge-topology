"""P7 session writeback worker."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from knowledge_topology.ids import is_valid_id
from knowledge_topology.ids import new_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.mutation_pack import MutationPack
from knowledge_topology.workers.compose_builder import deterministic_reltest_id
from knowledge_topology.storage.transaction import atomic_write_text


class WritebackError(ValueError):
    """Raised when writeback input is invalid."""


STATUS_VALUES = {"draft", "active", "contested"}
TEST_RESULTS = {"passed", "failed", "skipped"}
CONFLICT_SEVERITY = {"low", "medium", "high"}
MAX_ITEMS = 50
MAX_TEXT = 500
FILE_REF_FIELDS = {
    "repo_id",
    "commit_sha",
    "path",
    "line_range",
    "symbol",
    "anchor_kind",
    "excerpt_hash",
    "verified_at",
}
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


def _require(value: str, field: str) -> None:
    if not value.strip():
        raise WritebackError(f"{field} is required")


def bounded_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WritebackError(f"{field} must be a non-empty string")
    text = " ".join(value.strip().split())
    if len(text) > MAX_TEXT:
        raise WritebackError(f"{field} must be {MAX_TEXT} characters or fewer")
    return text


def require_list(summary: dict[str, Any], field: str) -> list[Any]:
    value = summary.get(field, [])
    if not isinstance(value, list):
        raise WritebackError(f"{field} must be a list")
    if len(value) > MAX_ITEMS:
        raise WritebackError(f"{field} must contain at most {MAX_ITEMS} items")
    return value


def normalize_statement_items(summary: dict[str, Any], field: str, key: str) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(require_list(summary, field), start=1):
        if isinstance(item, str):
            normalized.append({key: bounded_text(item, f"{field}[{index}]"), "status": "draft"})
        elif isinstance(item, dict):
            statement = bounded_text(item.get(key), f"{field}[{index}].{key}")
            status = item.get("status", "draft")
            if status not in STATUS_VALUES:
                raise WritebackError(f"{field}[{index}].status must be draft, active, or contested")
            normalized.append({key: statement, "status": status})
        else:
            raise WritebackError(f"{field}[{index}] must be a string or object")
    return normalized


def normalize_interfaces(
    summary: dict[str, Any],
    *,
    subject_repo_id: str,
    subject_head_sha: str,
) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(require_list(summary, "interfaces"), start=1):
        if not isinstance(item, dict):
            raise WritebackError(f"interfaces[{index}] must be an object")
        normalized.append({
            "name": bounded_text(item.get("name"), f"interfaces[{index}].name"),
            "contract": bounded_text(item.get("contract"), f"interfaces[{index}].contract"),
            "file_refs": normalize_file_refs(
                item.get("file_refs", []),
                f"interfaces[{index}].file_refs",
                subject_repo_id=subject_repo_id,
                subject_head_sha=subject_head_sha,
            ),
        })
    return normalized


def normalize_runtime_assumptions(summary: dict[str, Any]) -> list[dict[str, str]]:
    normalized = []
    for index, item in enumerate(require_list(summary, "runtime_assumptions"), start=1):
        if not isinstance(item, dict):
            raise WritebackError(f"runtime_assumptions[{index}] must be an object")
        normalized.append({
            "statement": bounded_text(item.get("statement"), f"runtime_assumptions[{index}].statement"),
            "observed_in": bounded_text(item.get("observed_in"), f"runtime_assumptions[{index}].observed_in"),
        })
    return normalized


def normalize_task_lessons(summary: dict[str, Any]) -> list[dict[str, str]]:
    normalized = []
    for index, item in enumerate(require_list(summary, "task_lessons"), start=1):
        if isinstance(item, str):
            normalized.append({
                "lesson": bounded_text(item, f"task_lessons[{index}]"),
                "applies_to": "current_task",
            })
        elif isinstance(item, dict):
            normalized.append({
                "lesson": bounded_text(item.get("lesson"), f"task_lessons[{index}].lesson"),
                "applies_to": bounded_text(item.get("applies_to"), f"task_lessons[{index}].applies_to"),
            })
        else:
            raise WritebackError(f"task_lessons[{index}] must be a string or object")
    return normalized


def normalize_tests_run(summary: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(require_list(summary, "tests_run"), start=1):
        if not isinstance(item, dict):
            raise WritebackError(f"tests_run[{index}] must be an object")
        result = item.get("result")
        if result not in TEST_RESULTS:
            raise WritebackError(f"tests_run[{index}].result must be passed, failed, or skipped")
        normalized.append({
            "command": bounded_text(item.get("command"), f"tests_run[{index}].command"),
            "result": result,
            "notes": bounded_text(item.get("notes", "not recorded"), f"tests_run[{index}].notes"),
        })
    return normalized


def normalize_commands_run(summary: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(require_list(summary, "commands_run"), start=1):
        if not isinstance(item, dict):
            raise WritebackError(f"commands_run[{index}] must be an object")
        exit_code = item.get("exit_code")
        if not isinstance(exit_code, int):
            raise WritebackError(f"commands_run[{index}].exit_code must be an integer")
        normalized.append({
            "command": bounded_text(item.get("command"), f"commands_run[{index}].command"),
            "exit_code": exit_code,
            "notes": bounded_text(item.get("notes", "not recorded"), f"commands_run[{index}].notes"),
        })
    return normalized


def normalize_conflicts(summary: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(require_list(summary, "conflicts"), start=1):
        if not isinstance(item, dict):
            raise WritebackError(f"conflicts[{index}] must be an object")
        severity = item.get("severity")
        if severity not in CONFLICT_SEVERITY:
            raise WritebackError(f"conflicts[{index}].severity must be low, medium, or high")
        refs = item.get("refs", [])
        if not isinstance(refs, list) or not all(isinstance(ref, str) and is_valid_id(ref) for ref in refs):
            raise WritebackError(f"conflicts[{index}].refs must be opaque ID strings")
        normalized.append({
            "summary": bounded_text(item.get("summary"), f"conflicts[{index}].summary"),
            "expected": bounded_text(item.get("expected"), f"conflicts[{index}].expected"),
            "observed": bounded_text(item.get("observed"), f"conflicts[{index}].observed"),
            "severity": severity,
            "refs": sorted(refs),
        })
    return normalized


def normalized_path_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def safe_file_ref_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    folded = raw.casefold().replace("\\", "/")
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
    normalized = normalized_path_token(raw)
    if any(token in normalized for token in FORBIDDEN_FILE_REF_TOKENS):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_./@+-]+", raw):
        return None
    if "/" not in raw and "." not in raw:
        return None
    return raw


def normalize_file_refs(
    value: Any,
    field: str = "file_refs",
    *,
    subject_repo_id: str,
    subject_head_sha: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise WritebackError(f"{field} must be a list")
    if len(value) > MAX_ITEMS:
        raise WritebackError(f"{field} must contain at most {MAX_ITEMS} items")
    refs = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise WritebackError(f"{field}[{index}] must be an object")
        extra = set(item) - FILE_REF_FIELDS
        if extra:
            raise WritebackError(f"{field}[{index}] has unknown fields: {', '.join(sorted(extra))}")
        path = safe_file_ref_path(item.get("path"))
        if path is None:
            raise WritebackError(f"{field}[{index}].path is unsafe")
        repo_id = item.get("repo_id")
        commit_sha = item.get("commit_sha")
        if not isinstance(repo_id, str) or not re.fullmatch(r"repo_[A-Za-z0-9_.:-]+", repo_id):
            raise WritebackError(f"{field}[{index}].repo_id is invalid")
        if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9A-Fa-f]{6,64}|[A-Za-z0-9_.:-]+", commit_sha):
            raise WritebackError(f"{field}[{index}].commit_sha is invalid")
        if repo_id != subject_repo_id:
            raise WritebackError(f"{field}[{index}].repo_id does not match subject_repo_id")
        if commit_sha != subject_head_sha:
            raise WritebackError(f"{field}[{index}].commit_sha does not match subject_head_sha")
        output = {"repo_id": repo_id, "commit_sha": commit_sha, "path": path}
        line_range = item.get("line_range")
        if line_range is not None:
            if (
                not isinstance(line_range, list)
                or len(line_range) != 2
                or not all(isinstance(part, int) and part > 0 for part in line_range)
            ):
                raise WritebackError(f"{field}[{index}].line_range is invalid")
            output["line_range"] = line_range
        symbol = item.get("symbol")
        if symbol is not None:
            if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]{0,120}", symbol):
                raise WritebackError(f"{field}[{index}].symbol is invalid")
            output["symbol"] = symbol
        anchor_kind = item.get("anchor_kind")
        if anchor_kind is not None:
            if anchor_kind not in {"symbol", "line", "excerpt"}:
                raise WritebackError(f"{field}[{index}].anchor_kind is invalid")
            output["anchor_kind"] = anchor_kind
        excerpt_hash = item.get("excerpt_hash")
        if excerpt_hash is not None:
            if not isinstance(excerpt_hash, str) or not re.fullmatch(r"[0-9A-Fa-f]{8,128}", excerpt_hash):
                raise WritebackError(f"{field}[{index}].excerpt_hash is invalid")
            output["excerpt_hash"] = excerpt_hash
        verified_at = item.get("verified_at")
        if verified_at is not None:
            if not isinstance(verified_at, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T[0-9:.-]+Z",
                verified_at,
            ):
                raise WritebackError(f"{field}[{index}].verified_at is invalid")
            output["verified_at"] = verified_at
        refs.append(output)
    return sorted(refs, key=lambda item: item["path"])


def load_summary(
    summary_path: str | Path,
    *,
    subject_repo_id: str,
    subject_head_sha: str,
) -> dict[str, Any]:
    path = Path(summary_path)
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WritebackError(f"summary JSON is invalid: {exc}") from exc
    if not isinstance(summary, dict):
        raise WritebackError("summary JSON must be an object")
    source_id = summary.get("source_id")
    digest_id = summary.get("digest_id")
    if not isinstance(source_id, str) or not is_valid_id(source_id, prefix="src"):
        raise WritebackError("source_id must use src_ opaque ID")
    if not isinstance(digest_id, str) or not is_valid_id(digest_id, prefix="dg"):
        raise WritebackError("digest_id must use dg_ opaque ID")
    return {
        "source_id": source_id,
        "digest_id": digest_id,
        "decisions": normalize_statement_items(summary, "decisions", "statement"),
        "invariants": normalize_statement_items(summary, "invariants", "statement"),
        "interfaces": normalize_interfaces(
            summary,
            subject_repo_id=subject_repo_id,
            subject_head_sha=subject_head_sha,
        ),
        "runtime_assumptions": normalize_runtime_assumptions(summary),
        "task_lessons": normalize_task_lessons(summary),
        "tests_run": normalize_tests_run(summary),
        "commands_run": normalize_commands_run(summary),
        "file_refs": normalize_file_refs(
            summary.get("file_refs", []),
            subject_repo_id=subject_repo_id,
            subject_head_sha=subject_head_sha,
        ),
        "conflicts": normalize_conflicts(summary),
    }


def writeback_session(
    root: str | Path,
    *,
    summary_path: str | Path,
    subject_repo_id: str,
    subject_head_sha: str,
    base_canonical_rev: str,
    current_canonical_rev: str,
    current_subject_head_sha: str,
) -> tuple[Path, Path]:
    for field, value in {
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "base_canonical_rev": base_canonical_rev,
        "current_canonical_rev": current_canonical_rev,
        "current_subject_head_sha": current_subject_head_sha,
    }.items():
        _require(value, field)
    if base_canonical_rev != current_canonical_rev:
        raise WritebackError("base_canonical_rev is stale")
    if subject_head_sha != current_subject_head_sha:
        raise WritebackError("subject_head_sha is stale")
    paths = TopologyPaths.from_root(root)
    summary = load_summary(
        summary_path,
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
    )
    source_id = summary["source_id"]
    digest_id = summary["digest_id"]
    changes: list[dict[str, Any]] = []
    for item in summary["decisions"]:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": item["statement"],
            "source_id": source_id,
            "digest_id": digest_id,
            "type": "decision",
            "status": item["status"],
            "authority": "repo_observed",
        })
    for item in summary["invariants"]:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": item["statement"],
            "source_id": source_id,
            "digest_id": digest_id,
            "type": "invariant",
            "status": item["status"],
            "authority": "repo_observed",
        })
    for item in summary["interfaces"]:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": item["contract"],
            "source_id": source_id,
            "digest_id": digest_id,
            "type": "interface",
            "status": "draft",
            "authority": "repo_observed",
            "name": item["name"],
            "file_refs": item["file_refs"],
        })
    for item in summary["runtime_assumptions"]:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": item["statement"],
            "source_id": source_id,
            "digest_id": digest_id,
            "type": "runtime_observation",
            "status": "draft",
            "authority": "runtime_observed",
            "scope": "runtime",
            "sensitivity": "runtime_only",
            "audiences": ["openclaw"],
            "observed_in": item["observed_in"],
        })
    for item in summary["task_lessons"]:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": item["lesson"],
            "source_id": source_id,
            "digest_id": digest_id,
            "type": "task_lesson",
            "status": "draft",
            "authority": "repo_observed",
            "applies_to": item["applies_to"],
        })
    if not summary["task_lessons"]:
        for item in summary["tests_run"]:
            changes.append({
                "op": "propose_node",
                "node_id": new_id("nd"),
                "reason": f"Test {item['result']}: {item['command']} ({item['notes']})",
                "source_id": source_id,
                "digest_id": digest_id,
                "type": "task_lesson",
                "status": "draft",
                "authority": "repo_observed",
                "lesson_kind": "test_result",
                "test_result": item["result"],
                "command": item["command"],
            })
        for item in summary["commands_run"]:
            changes.append({
                "op": "propose_node",
                "node_id": new_id("nd"),
                "reason": f"Command exited {item['exit_code']}: {item['command']} ({item['notes']})",
                "source_id": source_id,
                "digest_id": digest_id,
                "type": "task_lesson",
                "status": "draft",
                "authority": "repo_observed",
                "lesson_kind": "command_result",
                "exit_code": item["exit_code"],
                "command": item["command"],
            })
    for item in summary["conflicts"]:
        changes.append({
            "op": "propose_node",
            "node_id": new_id("nd"),
            "reason": item["summary"],
            "source_id": source_id,
            "digest_id": digest_id,
            "type": "decision",
            "status": "contested",
            "authority": "repo_observed",
            "conflict": {
                "expected": item["expected"],
                "observed": item["observed"],
                "severity": item["severity"],
                "refs": item["refs"],
            },
        })
    if not changes:
        raise WritebackError(
            "writeback summary must include one of: decisions, invariants, interfaces, "
            "runtime_assumptions, task_lessons, tests_run, commands_run, conflicts"
        )
    has_conflict = bool(summary["conflicts"])
    pack = MutationPack(
        schema_version="1.0",
        id=new_id("mut"),
        proposal_type="session_writeback",
        proposed_by="writeback",
        base_canonical_rev=base_canonical_rev,
        subject_repo_id=subject_repo_id,
        subject_head_sha=subject_head_sha,
        changes=changes,
        evidence_refs=[digest_id, source_id],
        requires_human=has_conflict,
        human_gate_class="high_impact_contradiction" if has_conflict else None,
        merge_confidence="low" if has_conflict else "medium",
        metadata={
            "writeback_summary": str(summary_path),
            "file_refs": summary["file_refs"],
            "tests_run": summary["tests_run"],
            "commands_run": summary["commands_run"],
        },
    )
    mutation_path = paths.resolve(f"mutations/pending/{pack.id}.json")
    atomic_write_text(mutation_path, json.dumps(pack.to_dict(), indent=2, sort_keys=True) + "\n")
    delta_dir = paths.ensure_dir(f".tmp/writeback/{pack.id}")
    reltest_path = delta_dir / "relationship-tests.yaml"
    reltest_lines = []
    for change in changes:
        if change.get("type") == "invariant":
            reltest_lines.extend([
                "- schema_version: 1.0",
                f"  id: {deterministic_reltest_id(change['node_id'])}",
                f"  invariant_node_id: {change['node_id']}",
                f"  property: {json.dumps(change['reason'])}",
                f"  evidence_refs: {json.dumps(pack.evidence_refs)}",
                "  suggested_test_shape: unit",
                "  failure_if: [\"invariant is violated\"]",
                "  status: draft",
            ])
    atomic_write_text(reltest_path, ("\n".join(reltest_lines) + "\n") if reltest_lines else "[]\n")
    return mutation_path, reltest_path
