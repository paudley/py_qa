# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utilities for normalising reported filesystem paths."""

from __future__ import annotations

from pathlib import Path


def normalize_reported_path(
    path: str | Path | None,
    *,
    root: Path | None = None,
    cwd: Path | None = None,
) -> str | None:
    """Return a stable, project-relative representation of *path*.

    The value is resolved against *root* when provided, falling back to the
    current working directory for relative inputs. Absolute paths are resolved
    directly to collapse any ``..`` entries. The final representation is made
    relative to the caller-provided *cwd* (or the real current working
    directory) when possible so downstream logic operates on canonical strings.
    """
    if path is None:
        return None

    candidate = Path(path)
    base_cwd = cwd or Path.cwd()
    try:
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            base = (root or base_cwd).resolve()
            resolved = (base / candidate).resolve()
    except (OSError, RuntimeError):  # RuntimeError covers symlink loops
        return candidate.as_posix()

    try:
        return resolved.relative_to(base_cwd.resolve()).as_posix()
    except (OSError, ValueError):
        return resolved.as_posix()


__all__ = ["normalize_reported_path"]
