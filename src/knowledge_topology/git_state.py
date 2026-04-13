"""Git state inspection helpers."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitStateError(RuntimeError):
    """Raised when Git state cannot be read in strict mode."""


@dataclass(frozen=True)
class GitState:
    root: Path
    head_sha: str | None
    dirty: bool


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def read_git_state(root: str | Path, *, strict: bool = False) -> GitState:
    path = Path(root).expanduser().resolve()
    inside = _git(path, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0:
        if strict:
            raise GitStateError(inside.stderr.strip() or "not a git repository")
        return GitState(path, None, False)
    head = _git(path, "rev-parse", "HEAD")
    if head.returncode != 0:
        if strict:
            raise GitStateError(head.stderr.strip() or "cannot read HEAD")
        head_sha = None
    else:
        head_sha = head.stdout.strip()
    status = _git(path, "status", "--porcelain")
    if status.returncode != 0 and strict:
        raise GitStateError(status.stderr.strip() or "cannot read git status")
    return GitState(path, head_sha, bool(status.stdout.strip()))
