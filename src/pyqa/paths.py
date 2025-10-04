# SPDX-License-Identifier: MIT
"""Helpers for resolving py_qa project paths."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import Iterable

from .logging import warn
from .workspace import is_py_qa_workspace

_PYQA_ROOT_ENV = "PYQA_ROOT"
_REQUIRED_ENTRIES: tuple[str, ...] = ("src/pyqa", "tooling")


@cache
def get_pyqa_root() -> Path:
    """Return the resolved py_qa project root directory.

    The root may be supplied via ``PYQA_ROOT`` or auto-detected by searching
    upwards from the current module location until a valid py_qa workspace is
    located.

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
        raise RuntimeError(
            "Unable to locate the py_qa project root; set PYQA_ROOT to the directory "
            "containing pyproject.toml."
        )
    _warn_on_suspicious_layout(detected, source="auto-detected root")
    return detected


def _auto_detect_pyqa_root() -> Path | None:
    search_start = Path(__file__).resolve().parent
    for candidate in _iter_candidates(search_start):
        try:
            return _validate_candidate(candidate)
        except ValueError:
            continue
    return None


def _iter_candidates(start: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    current = start
    while True:
        if current in seen:
            break
        seen.add(current)
        yield current
        if current.parent == current:
            break
        current = current.parent


def _validate_candidate(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"{resolved} is not a directory")
    if not (resolved / "pyproject.toml").is_file():
        raise ValueError(f"pyproject.toml not found under {resolved}")
    if not is_py_qa_workspace(resolved):
        raise ValueError(f"pyproject.toml at {resolved} does not describe py_qa")
    return resolved


def _warn_on_suspicious_layout(root: Path, *, source: str) -> None:
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
