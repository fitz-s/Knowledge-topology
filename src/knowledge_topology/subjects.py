"""Deterministic subject registry helpers."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_topology.git_state import read_git_state
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.storage.transaction import atomic_write_text


SUBJECT_FIELDS = [
    "schema_version",
    "subject_repo_id",
    "name",
    "kind",
    "location",
    "default_branch",
    "head_sha",
    "visibility",
    "sensitivity",
    "created_at",
    "updated_at",
]
SUBJECT_HEADER = [
    "# Subject repositories known to the topology.",
    "#",
    "# Fill this registry before producing mutation packs or builder packs for a",
    "# codebase. `subject_repo_id` values are stable external identifiers used in",
    "# mutation preconditions, file refs, and projection metadata.",
    "",
]
SUBJECT_ID_RE = re.compile(r"[A-Za-z0-9_.:-]+")
SUBJECT_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:-]+")
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T[0-9:.-]+Z")
HEAD_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:-]+")


class SubjectRegistryError(ValueError):
    """Raised when subject registry data is invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def registry_path(root: str | Path) -> Path:
    return TopologyPaths.from_root(root).root / "SUBJECTS.yaml"


def _parse_scalar(raw: str) -> str | None:
    value = raw.strip()
    if value == "null":
        return None
    if not value:
        raise SubjectRegistryError("subject scalar value is empty")
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SubjectRegistryError(f"invalid quoted subject value: {value}") from exc
        if not isinstance(parsed, str):
            raise SubjectRegistryError("subject scalar must decode to string")
        return parsed
    return value


def _render_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if not isinstance(value, str):
        raise SubjectRegistryError("subject scalar must be a string or null")
    return json.dumps(value)


def _field_error(field: str, message: str) -> SubjectRegistryError:
    return SubjectRegistryError(f"{field}: {message}")


def _require_token(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _field_error(field, "is required")
    token = value.strip()
    if not SUBJECT_TOKEN_RE.fullmatch(token):
        raise _field_error(field, "must be a safe token")
    return token


def _require_subject_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _field_error("subject_repo_id", "is required")
    token = value.strip()
    if not SUBJECT_ID_RE.fullmatch(token):
        raise _field_error("subject_repo_id", "must be a safe identifier")
    return token


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _field_error(field, "is required")
    return value.strip()


def _require_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise _field_error(field, "must be a UTC timestamp")
    return value


def _normalize_head_sha(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not HEAD_TOKEN_RE.fullmatch(value.strip()):
        raise _field_error("head_sha", "must be null or a safe revision token")
    return value.strip()


def _normalize_subject(record: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in SUBJECT_FIELDS if field not in record]
    if missing:
        raise SubjectRegistryError(f"subject record missing fields: {', '.join(missing)}")
    extra = sorted(set(record) - set(SUBJECT_FIELDS))
    if extra:
        raise SubjectRegistryError(f"subject record has unknown fields: {', '.join(extra)}")
    kind = _require_token(record["kind"], "kind")
    if kind != "git":
        raise _field_error("kind", "only git subjects are supported")
    sensitivity = _require_token(record["sensitivity"], "sensitivity")
    visibility = _require_token(record["visibility"], "visibility")
    normalized = {
        "schema_version": _require_text(record["schema_version"], "schema_version"),
        "subject_repo_id": _require_subject_id(record["subject_repo_id"]),
        "name": _require_text(record["name"], "name"),
        "kind": kind,
        "location": _require_text(record["location"], "location"),
        "default_branch": _require_token(record["default_branch"], "default_branch"),
        "head_sha": _normalize_head_sha(record["head_sha"]),
        "visibility": visibility,
        "sensitivity": sensitivity,
        "created_at": _require_timestamp(record["created_at"], "created_at"),
        "updated_at": _require_timestamp(record["updated_at"], "updated_at"),
    }
    return normalized


def _normalized_absolute_path(path: Path) -> Path:
    anchor = Path(path.anchor or "/")
    current = anchor
    parts = list(path.parts)
    start = 1 if path.is_absolute() else 0
    for part in parts[start:]:
        if part in {"", "."}:
            continue
        if part == "..":
            raise SubjectRegistryError("location must not contain '..'")
        current = current / part
    return current


def _reject_symlinked_path(path: Path, *, label: str) -> None:
    current = Path(path.anchor or "/")
    parts = list(path.parts)
    start = 1 if path.is_absolute() else 0
    for index, part in enumerate(parts[start:], start=start):
        current = current / part
        if current.is_symlink():
            raise SubjectRegistryError(f"{label} is symlinked: {current}")
        if index < len(parts) - 1 and current.exists() and not current.is_dir():
            raise SubjectRegistryError(f"{label} parent is not a directory: {current}")


def resolve_subject_location(root: str | Path, location: str, *, label: str = "location") -> Path:
    topology_root = TopologyPaths.from_root(root).root
    raw = _require_text(location, label)
    source = Path(raw)
    if source.is_absolute():
        resolved = _normalized_absolute_path(source)
    else:
        resolved = _normalized_absolute_path(topology_root / source)
        if topology_root != resolved and topology_root not in resolved.parents:
            raise SubjectRegistryError(f"{label} escapes topology root")
    _reject_symlinked_path(resolved, label=label)
    return resolved


def read_subject_registry(root: str | Path) -> list[dict[str, Any]]:
    path = registry_path(root)
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise SubjectRegistryError("SUBJECTS.yaml must be a regular file")
    subjects: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    saw_root = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line == "subjects:":
            saw_root = True
            continue
        if raw_line.startswith("  - "):
            if current is not None:
                subjects.append(_normalize_subject(current))
            current = {}
            line = raw_line[4:]
        elif raw_line.startswith("    "):
            if current is None:
                raise SubjectRegistryError("subject field appeared before a list item")
            line = raw_line[4:]
        else:
            raise SubjectRegistryError(f"unsupported SUBJECTS.yaml line: {raw_line}")
        if ":" not in line:
            raise SubjectRegistryError(f"subject line missing ':': {raw_line}")
        key, value = line.split(":", 1)
        field = key.strip()
        if field in (current or {}):
            raise SubjectRegistryError(f"duplicate subject field: {field}")
        assert current is not None
        current[field] = _parse_scalar(value)
    if not saw_root:
        raise SubjectRegistryError("SUBJECTS.yaml missing top-level 'subjects:' key")
    if current is not None:
        subjects.append(_normalize_subject(current))
    seen: set[str] = set()
    for subject in subjects:
        subject_id = subject["subject_repo_id"]
        if subject_id in seen:
            raise SubjectRegistryError(f"duplicate subject_repo_id: {subject_id}")
        seen.add(subject_id)
    return sorted(subjects, key=lambda item: item["subject_repo_id"])


def write_subject_registry(root: str | Path, subjects: list[dict[str, Any]]) -> Path:
    normalized = [_normalize_subject(subject) for subject in subjects]
    seen: set[str] = set()
    for subject in normalized:
        subject_id = subject["subject_repo_id"]
        if subject_id in seen:
            raise SubjectRegistryError(f"duplicate subject_repo_id: {subject_id}")
        seen.add(subject_id)
    lines = list(SUBJECT_HEADER)
    lines.append("subjects:")
    for subject in sorted(normalized, key=lambda item: item["subject_repo_id"]):
        lines.append(f"  - schema_version: {_render_scalar(subject['schema_version'])}")
        for field in SUBJECT_FIELDS[1:]:
            lines.append(f"    {field}: {_render_scalar(subject[field])}")
    atomic_write_text(registry_path(root), "\n".join(lines) + "\n")
    return registry_path(root)


def build_subject_record(
    *,
    subject_repo_id: str,
    name: str,
    kind: str,
    location: str,
    default_branch: str,
    visibility: str,
    sensitivity: str,
    created_at: str,
    updated_at: str,
    head_sha: str | None = None,
) -> dict[str, Any]:
    return _normalize_subject({
        "schema_version": "1.0",
        "subject_repo_id": subject_repo_id,
        "name": name,
        "kind": kind,
        "location": location,
        "default_branch": default_branch,
        "head_sha": head_sha,
        "visibility": visibility,
        "sensitivity": sensitivity,
        "created_at": created_at,
        "updated_at": updated_at,
    })


def add_subject(
    root: str | Path,
    *,
    subject_repo_id: str,
    name: str,
    kind: str,
    location: str,
    default_branch: str,
    visibility: str,
    sensitivity: str,
    now: str,
) -> dict[str, Any]:
    resolve_subject_location(root, location)
    subjects = read_subject_registry(root)
    if any(subject["subject_repo_id"] == subject_repo_id for subject in subjects):
        raise SubjectRegistryError(f"duplicate subject_repo_id: {subject_repo_id}")
    subject = build_subject_record(
        subject_repo_id=subject_repo_id,
        name=name,
        kind=kind,
        location=location,
        default_branch=default_branch,
        visibility=visibility,
        sensitivity=sensitivity,
        created_at=now,
        updated_at=now,
    )
    write_subject_registry(root, [*subjects, subject])
    return subject


def get_subject(root: str | Path, subject_repo_id: str) -> dict[str, Any]:
    subject_id = _require_subject_id(subject_repo_id)
    for subject in read_subject_registry(root):
        if subject["subject_repo_id"] == subject_id:
            return subject
    raise SubjectRegistryError(f"subject not found: {subject_id}")


def show_subject(root: str | Path, subject_repo_id: str) -> dict[str, Any]:
    subject = get_subject(root, subject_repo_id)
    resolve_subject_location(root, subject["location"])
    return subject


def resolve_subject(root: str | Path, subject_repo_id: str) -> dict[str, Any]:
    subject = get_subject(root, subject_repo_id)
    return {
        **subject,
        "resolved_location": str(resolve_subject_location(root, subject["location"])),
    }


def subject_projection_authority(root: str | Path, subject_repo_id: str) -> tuple[dict[str, Any], Path, str]:
    subject = get_subject(root, subject_repo_id)
    stored_location = resolve_subject_location(root, subject["location"], label="stored subject location")
    stored_head = subject["head_sha"]
    if stored_head is None:
        raise SubjectRegistryError("stored subject head_sha is null; run topology subject refresh")
    return subject, stored_location, stored_head


def _git_head(path: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def refresh_subject(root: str | Path, subject_repo_id: str, *, now: str) -> dict[str, Any]:
    subject = get_subject(root, subject_repo_id)
    location = resolve_subject_location(root, subject["location"])
    if not location.exists():
        raise SubjectRegistryError(f"subject location does not exist: {location}")
    head_sha = _git_head(location)
    if head_sha is None:
        raise SubjectRegistryError(f"subject location is not a git repository: {location}")
    refreshed = {**subject, "head_sha": head_sha, "updated_at": now}
    subjects = [
        refreshed if item["subject_repo_id"] == refreshed["subject_repo_id"] else item
        for item in read_subject_registry(root)
    ]
    write_subject_registry(root, subjects)
    return refreshed


def subject_for_projection(
    root: str | Path,
    *,
    subject_repo_id: str,
    subject_head_sha: str,
    subject_path: str | Path | None,
    allow_dirty: bool = False,
) -> tuple[dict[str, Any], Path, bool]:
    subject, stored_location, stored_head = subject_projection_authority(root, subject_repo_id)
    if stored_head != subject_head_sha:
        raise SubjectRegistryError("subject_head_sha does not match stored subject head")
    if subject_path is None:
        return subject, stored_location, False
    provided_path = resolve_subject_location(root, str(subject_path), label="subject_path")
    if provided_path != stored_location:
        raise SubjectRegistryError("subject_path does not match stored subject location")
    state = read_git_state(provided_path)
    head_sha = state.head_sha
    if head_sha is None:
        raise SubjectRegistryError(f"subject_path is not a git repository: {provided_path}")
    if not allow_dirty and state.dirty:
        raise SubjectRegistryError("subject repo must be clean before composing OpenClaw projection")
    if head_sha != subject_head_sha:
        raise SubjectRegistryError("subject_head_sha does not match current subject HEAD")
    return subject, stored_location, True
