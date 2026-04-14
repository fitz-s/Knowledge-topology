from __future__ import annotations

from pathlib import Path

from knowledge_topology.subjects import build_subject_record, write_subject_registry


FIXED_SUBJECT_TIME = "2026-04-13T00:00:00Z"


def seed_subject_registry(
    root: Path,
    *,
    subject_repo_id: str = "repo_knowledge_topology",
    head_sha: str | None = "abc123",
    location: str = ".",
    default_branch: str = "main",
    visibility: str = "public",
    sensitivity: str = "internal",
) -> None:
    write_subject_registry(
        root,
        [
            build_subject_record(
                subject_repo_id=subject_repo_id,
                name="Knowledge topology",
                kind="git",
                location=location,
                default_branch=default_branch,
                head_sha=head_sha,
                visibility=visibility,
                sensitivity=sensitivity,
                created_at=FIXED_SUBJECT_TIME,
                updated_at=FIXED_SUBJECT_TIME,
            )
        ],
    )
