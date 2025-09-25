# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utilities for reasoning about the active project workspace."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

from .constants import PY_QA_DIR_NAME

try:  # Python 3.11+ includes tomllib in the stdlib; fallback unsupported.
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError as exc:  # pragma: no cover - environment invariant
    raise RuntimeError("tomllib is required to inspect project metadata") from exc


def is_py_qa_workspace(root: Path) -> bool:
    """Return ``True`` when *root* appears to be the py_qa project itself."""
    try:
        resolved = root.resolve()
    except OSError:
        return False
    return _is_py_qa_workspace_cached(str(resolved))


@cache
def _is_py_qa_workspace_cached(root_str: str) -> bool:
    root = Path(root_str)
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    name = _extract_project_name(data)
    return name in _PY_QA_NAME_VARIANTS


def _extract_project_name(payload: dict[str, Any]) -> str | None:
    project = payload.get("project")
    if isinstance(project, dict):
        candidate = project.get("name")
        if isinstance(candidate, str):
            return candidate
    tool = payload.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            candidate = poetry.get("name")
            if isinstance(candidate, str):
                return candidate
    return None


_PY_QA_NAME_VARIANTS = {PY_QA_DIR_NAME, PY_QA_DIR_NAME.replace("_", "")}


__all__ = ["is_py_qa_workspace"]
