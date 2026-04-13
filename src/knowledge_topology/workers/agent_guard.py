"""Deterministic guards for agent integration hooks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str


def allow(reason: str = "allowed") -> GuardResult:
    return GuardResult(allowed=True, reason=reason)


def deny(reason: str) -> GuardResult:
    return GuardResult(allowed=False, reason=reason)


def is_inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def normalize_root(root: str | Path) -> Path:
    return Path(root).expanduser().resolve(strict=False)


def normalize_cwd(event: dict[str, Any], root: Path) -> Path | None:
    value = event.get("cwd")
    if value is None:
        return root
    if not isinstance(value, str) or not value.strip():
        return None
    cwd = Path(value).expanduser()
    if not cwd.is_absolute():
        cwd = root / cwd
    resolved = cwd.resolve(strict=False)
    if not is_inside(resolved, root):
        return None
    return resolved


def normalize_candidate(raw_path: str, *, root: Path, cwd: Path) -> Path | None:
    if not raw_path.strip():
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    resolved = candidate.resolve(strict=False)
    if not is_inside(resolved, root):
        return None
    return resolved


def is_denied_surface(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        return True
    folded = [part.casefold() for part in relative_parts]
    return bool(folded) and folded[0] == "canonical"


def validate_payload(tool_name: str, tool_input: Any) -> str | None:
    if not isinstance(tool_input, dict):
        return f"{tool_name} tool_input must be an object"
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        return f"{tool_name} tool_input.file_path is required"
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        if not isinstance(edits, list) or not edits:
            return "MultiEdit tool_input.edits must be a non-empty list"
        if not all(isinstance(item, dict) for item in edits):
            return "MultiEdit tool_input.edits must contain objects"
    return None


def guard_claude_pre_tool_use(root: str | Path, payload_text: str) -> GuardResult:
    try:
        event = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        return deny(f"invalid hook JSON: {exc.msg}")
    if not isinstance(event, dict):
        return deny("hook JSON must be an object")

    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return deny("tool_name is required")
    if tool_name not in WRITE_TOOLS:
        return allow(f"{tool_name} is outside direct file-write guard scope")

    root_path = normalize_root(root)
    cwd = normalize_cwd(event, root_path)
    if cwd is None:
        return deny("cwd must resolve inside topology root")

    tool_input = event.get("tool_input")
    payload_error = validate_payload(tool_name, tool_input)
    if payload_error is not None:
        return deny(payload_error)

    candidate = normalize_candidate(tool_input["file_path"], root=root_path, cwd=cwd)
    if candidate is None:
        return deny("file_path must resolve inside topology root")
    if is_denied_surface(candidate, root_path):
        return deny("direct writes to canonical surfaces are blocked; emit a mutation pack instead")
    return allow("file path is outside protected canonical surfaces")
