"""Checksum utilities for catalog contents."""

from __future__ import annotations

import hashlib
from pathlib import Path
from collections.abc import Sequence


def compute_catalog_checksum(catalog_root: Path, paths: Sequence[Path]) -> str:
    """Return a deterministic checksum for *paths* relative to *catalog_root*."""

    hasher = hashlib.sha256()
    for path in paths:
        relative_path = path.relative_to(catalog_root).as_posix().encode("utf-8")
        hasher.update(relative_path)
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


__all__ = ["compute_catalog_checksum"]
