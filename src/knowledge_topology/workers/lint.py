"""P7 deterministic lint checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from knowledge_topology.ids import is_valid_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.loader import load_json
from knowledge_topology.schema.source_packet import SourcePacket, SourcePacketError


@dataclass(frozen=True)
class LintResult:
    ok: bool
    messages: list[str]


RELTEST_REQUIRED_FIELDS = {
    "schema_version",
    "id",
    "invariant_node_id",
    "property",
    "evidence_refs",
    "suggested_test_shape",
    "failure_if",
    "status",
}
RELTEST_STATUSES = {"draft", "active", "contested", "superseded", "rejected"}


class RelationshipTestError(ValueError):
    """Raised when a relationship-test file violates the constrained schema."""


def _parse_scalar(raw: str) -> object:
    value = raw.strip()
    if value == "":
        raise RelationshipTestError("empty scalar value")
    if value.startswith("[") or value.startswith("{") or value.startswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise RelationshipTestError(f"invalid JSON scalar: {value}") from exc
    return value


def _parse_field(line: str) -> tuple[str, object]:
    if ":" not in line:
        raise RelationshipTestError(f"missing ':' in line: {line}")
    key, raw_value = line.split(":", 1)
    key = key.strip()
    if not key:
        raise RelationshipTestError("empty field name")
    return key, _parse_scalar(raw_value)


def parse_relationship_tests(reltest_path: Path) -> list[dict[str, object]]:
    text = reltest_path.read_text(encoding="utf-8")
    if text.strip() == "[]":
        return []
    if not text.strip():
        raise RelationshipTestError("empty relationship-test file")

    tests: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        if raw_line.startswith("- "):
            if current is not None:
                tests.append(current)
            current = {}
            key, value = _parse_field(raw_line[2:])
        elif raw_line.startswith("  "):
            if current is None:
                raise RelationshipTestError(f"field before list item at line {line_no}")
            key, value = _parse_field(raw_line[2:])
        else:
            raise RelationshipTestError(f"expected list item or indented field at line {line_no}")

        if current is None:
            raise RelationshipTestError(f"field before list item at line {line_no}")
        if key in current:
            raise RelationshipTestError(f"duplicate field {key} at line {line_no}")
        current[key] = value

    if current is not None:
        tests.append(current)
    if not tests:
        raise RelationshipTestError("relationship-test file must be [] or a non-empty list")
    for index, item in enumerate(tests, start=1):
        validate_relationship_test(item, index=index)
    return tests


def validate_relationship_test(item: dict[str, object], *, index: int) -> None:
    missing = RELTEST_REQUIRED_FIELDS - set(item)
    if missing:
        raise RelationshipTestError(f"item {index} missing fields: {', '.join(sorted(missing))}")
    extra = set(item) - RELTEST_REQUIRED_FIELDS
    if extra:
        raise RelationshipTestError(f"item {index} unknown fields: {', '.join(sorted(extra))}")
    if str(item["schema_version"]) != "1.0":
        raise RelationshipTestError(f"item {index} unsupported schema_version")
    if not isinstance(item["id"], str) or not is_valid_id(item["id"], prefix="reltest"):
        raise RelationshipTestError(f"item {index} id must use reltest_ opaque ID")
    if not isinstance(item["invariant_node_id"], str) or not is_valid_id(item["invariant_node_id"], prefix="nd"):
        raise RelationshipTestError(f"item {index} invariant_node_id must use nd_ opaque ID")
    if not isinstance(item["property"], str) or not item["property"].strip():
        raise RelationshipTestError(f"item {index} property is required")
    if not isinstance(item["evidence_refs"], list) or not all(isinstance(ref, str) and "_" in ref for ref in item["evidence_refs"]):
        raise RelationshipTestError(f"item {index} evidence_refs must be a list of opaque IDs")
    if not isinstance(item["suggested_test_shape"], str) or not item["suggested_test_shape"].strip():
        raise RelationshipTestError(f"item {index} suggested_test_shape is required")
    if not isinstance(item["failure_if"], list) or not all(isinstance(value, str) and value.strip() for value in item["failure_if"]):
        raise RelationshipTestError(f"item {index} failure_if must be a non-empty string list")
    if not item["failure_if"]:
        raise RelationshipTestError(f"item {index} failure_if must not be empty")
    if item["status"] not in RELTEST_STATUSES:
        raise RelationshipTestError(f"item {index} status must be a valid topology status")


def lint_source_packets(paths: TopologyPaths) -> list[str]:
    messages: list[str] = []
    for packet_path in paths.resolve("raw/packets").glob("src_*/packet.json"):
        try:
            packet = SourcePacket(**load_json(packet_path))
            packet.validate()
        except (TypeError, SourcePacketError, ValueError) as exc:
            messages.append(f"{packet_path}: invalid source packet: {exc}")
            continue
        if packet.content_mode == "public_text" and packet.redistributable != "yes":
            messages.append(f"{packet_path}: public_text requires redistributable=yes")
    return messages


def lint_projection_leakage(paths: TopologyPaths) -> list[str]:
    messages: list[str] = []
    projections = paths.resolve("projections")
    if projections.exists():
        for path in projections.rglob("*"):
            if path.is_file():
                messages.append(f"{path}: generated projection file outside tests/fixtures")
    return messages


def lint_relationship_tests(paths: TopologyPaths) -> list[str]:
    messages: list[str] = []
    reltest_paths = [
        *paths.resolve("projections/tasks").glob("*/relationship-tests.yaml"),
        *paths.resolve(".tmp/writeback").glob("*/relationship-tests.yaml"),
    ]
    for reltest_path in reltest_paths:
        try:
            parse_relationship_tests(reltest_path)
        except RelationshipTestError as exc:
            messages.append(f"{reltest_path}: malformed relationship tests: {exc}")
    return messages


def lint_missing_antibodies(paths: TopologyPaths) -> list[str]:
    messages: list[str] = []
    for task_dir in paths.resolve("projections/tasks").glob("*"):
        if not task_dir.is_dir() or task_dir.is_symlink():
            continue
        constraints = task_dir / "constraints.json"
        reltests = task_dir / "relationship-tests.yaml"
        if not constraints.exists():
            continue
        if not reltests.exists():
            messages.append(f"{task_dir}: builder-critical invariants missing relationship tests")
            continue
        payload = json.loads(constraints.read_text(encoding="utf-8"))
        invariants = payload.get("invariants", [])
        invariant_ids = {
            item.get("id") or item.get("node_id")
            for item in invariants
            if isinstance(item, dict) and isinstance(item.get("id") or item.get("node_id"), str)
        }
        invariant_count = int(payload.get("count", len(invariant_ids)))
        if invariant_count <= 0 and not invariant_ids:
            continue
        try:
            covered = {item["invariant_node_id"] for item in parse_relationship_tests(reltests)}
        except RelationshipTestError:
            continue
        missing = sorted(invariant_ids - covered)
        if invariant_count > 0 and (not covered or missing):
            detail = f": {', '.join(missing)}" if missing else ""
            messages.append(f"{task_dir}: builder-critical invariants missing relationship tests{detail}")
    return messages


def run_lints(root: str | Path) -> LintResult:
    paths = TopologyPaths.from_root(root)
    messages: list[str] = []
    messages.extend(lint_source_packets(paths))
    messages.extend(lint_projection_leakage(paths))
    messages.extend(lint_relationship_tests(paths))
    messages.extend(lint_missing_antibodies(paths))
    return LintResult(ok=not messages, messages=messages)
