"""P7 deterministic lint checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.loader import load_json
from knowledge_topology.schema.source_packet import SourcePacket, SourcePacketError


@dataclass(frozen=True)
class LintResult:
    ok: bool
    messages: list[str]


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
    for reltest_path in paths.resolve("projections/tasks").glob("*/relationship-tests.yaml"):
        text = reltest_path.read_text(encoding="utf-8")
        if text.strip() == "[]":
            continue
        if "schema_version: 1.0" not in text:
            messages.append(f"{reltest_path}: missing schema_version")
        if "id: reltest_" not in text:
            messages.append(f"{reltest_path}: missing reltest_ id")
    return messages


def lint_missing_antibodies(paths: TopologyPaths) -> list[str]:
    messages: list[str] = []
    for task_dir in paths.resolve("projections/tasks").glob("*"):
        if not task_dir.is_dir() or task_dir.is_symlink():
            continue
        constraints = task_dir / "constraints.json"
        reltests = task_dir / "relationship-tests.yaml"
        if not constraints.exists() or not reltests.exists():
            continue
        payload = json.loads(constraints.read_text(encoding="utf-8"))
        invariant_count = int(payload.get("count", 0))
        if invariant_count > 0 and reltests.read_text(encoding="utf-8").strip() == "[]":
            messages.append(f"{task_dir}: builder-critical invariants missing relationship tests")
    return messages


def run_lints(root: str | Path) -> LintResult:
    paths = TopologyPaths.from_root(root)
    messages: list[str] = []
    messages.extend(lint_source_packets(paths))
    messages.extend(lint_projection_leakage(paths))
    messages.extend(lint_relationship_tests(paths))
    messages.extend(lint_missing_antibodies(paths))
    return LintResult(ok=not messages, messages=messages)
