# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for resolving py_qa project paths."""

from __future__ import annotations

import os
from collections.abc import Iterable
from functools import cache
from itertools import chain
from pathlib import Path

from pyqa.core.logging import warn
from pyqa.platform.workspace import is_py_qa_workspace

_PYQA_ROOT_ENV = "PYQA_ROOT"
_REQUIRED_ENTRIES: tuple[str, ...] = ("src/pyqa", "tooling")


@cache
def get_pyqa_root() -> Path:
    """Return the resolved py_qa project root directory.

    The root may be supplied via ``PYQA_ROOT`` or auto-detected by searching
    upwards from the current module location until a valid py_qa workspace is
    located.

    Returns:
        Path: Directory representing the py_qa project root.

    Raises:
        RuntimeError: If no suitable project root can be located.

    """

    env_value = os.environ.get(_PYQA_ROOT_ENV)
    if env_value:
        candidate = Path(env_value).expanduser()
        root = _validate_candidate(candidate)
        _warn_on_suspicious_layout(root, source="environment override")
        return root

    detected = _auto_detect_pyqa_root()
    if detected is None:
        message_parts = [
            "Unable to locate the py_qa project root; set PYQA_ROOT to the",
            "directory containing pyproject.toml.",
        ]
        raise RuntimeError(" ".join(message_parts))
    _warn_on_suspicious_layout(detected, source="auto-detected root")
    return detected


def _auto_detect_pyqa_root() -> Path | None:
    """Return an auto-detected py_qa project root when available.

    Returns:
        Path | None: Resolved project root or ``None`` when detection fails.
    """

    search_start = Path(__file__).resolve().parent
    for candidate in _iter_candidates(search_start):
        try:
            return _validate_candidate(candidate)
        except ValueError:
            continue
    return None


def _iter_candidates(start: Path) -> Iterable[Path]:
    """Yield unique parent directories starting at ``start`` up to root.

    Args:
        start: Directory whose ancestors should be traversed.

    Yields:
        Path: Candidate directories considered during root discovery.

    Returns:
        Iterable[Path]: Iterator producing candidate directories for validation.
    """

    seen: set[Path] = set()
    for candidate in chain([start], start.parents):
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _validate_candidate(path: Path) -> Path:
    """Return ``path`` when it satisfies py_qa root constraints.

    Args:
        path: Candidate directory to evaluate.

    Returns:
        Path: Resolved directory when validation succeeds.

    Raises:
        ValueError: If the candidate fails any validation step.
    """

    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"{resolved} is not a directory")
    if not (resolved / "pyproject.toml").is_file():
        raise ValueError(f"pyproject.toml not found under {resolved}")
    if not is_py_qa_workspace(resolved):
        raise ValueError(f"pyproject.toml at {resolved} does not describe py_qa")
    return resolved


def _warn_on_suspicious_layout(root: Path, *, source: str) -> None:
    """Emit a warning when expected project entries are missing.

    Args:
        root: Candidate project root that may have missing entries.
        source: Human-readable description of the root discovery method.
    """

    missing = [entry for entry in _REQUIRED_ENTRIES if not (root / entry).exists()]
    if missing:
        joined = ", ".join(missing)
        warn(
            (
                f"{source}: py_qa root '{root}' is missing expected entries: {joined}. "
                "The directory will be treated as read-only; ensure the path is correct."
            ),
            use_emoji=False,
        )


__all__ = ["get_pyqa_root"]
