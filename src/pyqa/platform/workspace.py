# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utilities for reasoning about the active project workspace."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import TypeAlias, cast

from pyqa.core.config.constants import PY_QA_DIR_NAME

try:  # Python 3.11+ includes tomllib in the stdlib; fallback unsupported.
    import tomllib
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
        data = cast(PyProjectPayload, tomllib.loads(pyproject.read_text(encoding="utf-8")))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    name = _extract_project_name(data)
    if name not in _PY_QA_NAME_VARIANTS:
        return False
    return _has_required_entries(root)


TomlValue: TypeAlias = str | int | float | bool | None | Sequence["TomlValue"] | Mapping[str, "TomlValue"]
PyProjectPayload: TypeAlias = Mapping[str, TomlValue]


def _extract_project_name(payload: PyProjectPayload) -> str | None:
    project = payload.get("project")
    if isinstance(project, Mapping):
        candidate = project.get("name")
        if isinstance(candidate, str):
            return candidate
    tool = payload.get("tool")
    if isinstance(tool, Mapping):
        poetry = tool.get("poetry")
        if isinstance(poetry, Mapping):
            candidate = poetry.get("name")
            if isinstance(candidate, str):
                return candidate
    return None


_PY_QA_NAME_VARIANTS = {PY_QA_DIR_NAME, PY_QA_DIR_NAME.replace("_", "")}
_SENTINEL_DIRECTORIES = ("src/pyqa", "docs", "tooling")
_SENTINEL_FILES = ("REORG_PLAN.md",)


def _has_required_entries(root: Path) -> bool:
    for relative in _SENTINEL_DIRECTORIES:
        candidate = root / relative
        if not candidate.is_dir():
            return False
    for relative in _SENTINEL_FILES:
        candidate = root / relative
        if not candidate.is_file():
            return False
    init_file = root / "src" / "pyqa" / "__init__.py"
    return init_file.is_file()


__all__ = ["is_py_qa_workspace"]
