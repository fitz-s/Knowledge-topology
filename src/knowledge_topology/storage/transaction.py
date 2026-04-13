"""Filesystem transaction helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator
import os


@contextmanager
def atomic_writer(target: str | Path) -> Iterator[Path]:
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp = NamedTemporaryFile("wb", delete=False, dir=target_path.parent, prefix=f".{target_path.name}.", suffix=".tmp")
    temp_path = Path(temp.name)
    try:
        temp.close()
        yield temp_path
        os.replace(temp_path, target_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(target: str | Path, text: str) -> None:
    with atomic_writer(target) as temp_path:
        temp_path.write_text(text, encoding="utf-8")
