"""Digest model output adapter boundary."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Any


class DigestProviderError(ValueError):
    """Raised when a digest provider cannot produce raw digest JSON."""


class DigestModelAdapter(Protocol):
    """Loads a model-produced digest payload without applying business rules."""

    def load_output(self) -> dict[str, Any]:
        """Return raw digest JSON payload."""


class JsonFileDigestAdapter:
    """Digest adapter for already-produced JSON fixture/model output."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_output(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("digest model output must be a JSON object")
        return payload


class DictDigestAdapter:
    """Digest adapter for already-loaded provider output."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def load_output(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class DigestModelRequest:
    """Sanitized request passed to a digest provider."""

    source_id: str
    digest_depth: str
    prompt: str
    source_packet: dict[str, Any]
    source_text: str | None
    source_text_kind: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "digest_depth": self.digest_depth,
            "prompt": self.prompt,
            "source_packet": self.source_packet,
            "source_text": self.source_text,
            "source_text_kind": self.source_text_kind,
        }


class DigestProviderAdapter(Protocol):
    """Generates raw digest JSON from a sanitized request."""

    def generate(self, request: DigestModelRequest) -> dict[str, Any]:
        """Return raw digest JSON payload."""


class JsonDirectoryDigestProviderAdapter:
    """Provider adapter that maps source_id to a JSON file in a fixture directory."""

    def __init__(self, directory: str | Path, *, root: str | Path | None = None):
        self.directory = Path(directory)
        self.root = Path(root).resolve() if root is not None else None

    def generate(self, request: DigestModelRequest) -> dict[str, Any]:
        path = self._fixture_path(request.source_id)
        return JsonFileDigestAdapter(path).load_output()

    def _fixture_path(self, source_id: str) -> Path:
        directory = self.directory
        self._check_directory_path(directory)
        if self.root is not None:
            self._check_path_under_root(directory)
        if not directory.exists() or not directory.is_dir() or directory.is_symlink():
            raise DigestProviderError("model-output-dir must be a real directory")
        path = directory / f"{source_id}.json"
        if self.root is not None:
            self._check_path_under_root(path)
        if not path.exists():
            raise DigestProviderError(f"model output fixture not found for source_id: {source_id}")
        if path.is_symlink() or not path.is_file():
            raise DigestProviderError("model output fixture must be a regular non-symlink file")
        return path

    def _check_directory_path(self, directory: Path) -> None:
        if ".." in directory.parts:
            raise DigestProviderError("model-output-dir must not contain traversal")

    def _check_path_under_root(self, path: Path) -> None:
        if self.root is None:
            return
        absolute = path if path.is_absolute() else self.root / path
        try:
            relative = absolute.relative_to(self.root)
        except ValueError as exc:
            raise DigestProviderError("model output path must stay under topology root") from exc
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise DigestProviderError("model output path parent must not be a symlink")


class CommandDigestProviderAdapter:
    """Provider adapter that executes a local argv command with request JSON on stdin."""

    DEFAULT_STDOUT_LIMIT = 1024 * 1024
    DEFAULT_ERROR_LIMIT = 4096
    SAFE_ENV_NAMES = {
        "PATH",
        "HOME",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
    }

    def __init__(
        self,
        command: str,
        *,
        cwd: str | Path,
        timeout_seconds: int = 120,
        stdout_limit: int = DEFAULT_STDOUT_LIMIT,
        error_limit: int = DEFAULT_ERROR_LIMIT,
    ):
        self.argv = shlex.split(command)
        if not self.argv:
            raise DigestProviderError("provider command must not be empty")
        self.cwd = Path(cwd)
        self.timeout_seconds = timeout_seconds
        self.stdout_limit = stdout_limit
        self.error_limit = error_limit

    def generate(self, request: DigestModelRequest) -> dict[str, Any]:
        stdin = json.dumps(request.to_dict(), sort_keys=True)
        try:
            result = subprocess.run(
                self.argv,
                input=stdin,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                env=self.safe_env(),
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DigestProviderError(f"provider command timed out after {self.timeout_seconds}s") from exc
        if len(result.stdout.encode("utf-8")) > self.stdout_limit:
            raise DigestProviderError("provider stdout exceeded size limit")
        if result.returncode != 0:
            stderr = self.bound_text(result.stderr)
            raise DigestProviderError(f"provider command failed with exit {result.returncode}: {stderr}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise DigestProviderError(f"provider stdout was not valid JSON: {self.bound_text(result.stdout)}") from exc
        if not isinstance(payload, dict):
            raise DigestProviderError("provider stdout JSON must be an object")
        return payload

    def safe_env(self) -> dict[str, str]:
        return {name: os.environ[name] for name in self.SAFE_ENV_NAMES if name in os.environ}

    def bound_text(self, value: str) -> str:
        compact = " ".join(value.split())
        return compact[: self.error_limit]
