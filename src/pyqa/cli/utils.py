# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared helpers for CLI commands."""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..constants import PY_QA_DIR_NAME
from ..process_utils import run_command
from ..tool_env import VersionResolver
from ..tools.base import Tool
from ..workspace import is_py_qa_workspace


@dataclass(slots=True)
class ToolStatus:
    """Status information for a tool as discovered by doctor/tool-info commands."""

    name: str
    status: str
    version: str | None
    min_version: str | None
    executable: str | None
    path: str | None
    notes: str
    returncode: int | None
    raw_output: str | None


def check_tool_status(tool: Tool) -> ToolStatus:
    """Return ``ToolStatus`` describing availability and version information for *tool*."""
    version_cmd: Sequence[str] | None = tool.version_command
    executable = version_cmd[0] if version_cmd else None
    path = shutil.which(executable) if executable else None
    resolver = VersionResolver()

    if not version_cmd:
        notes = "Tool does not define a version command; status derived from runtime availability."
        status = "unknown"
        if tool.runtime != "binary":
            status = "vendored"
            notes = f"Provisioned via runtime '{tool.runtime}' when needed."
        return ToolStatus(
            name=tool.name,
            status=status,
            version=None,
            min_version=tool.min_version,
            executable=None,
            path=None,
            notes=notes,
            returncode=None,
            raw_output=None,
        )

    try:
        completed = run_command(
            list(version_cmd),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        status = "vendored" if tool.runtime != "binary" else "uninstalled"
        runtime_note = f"Runtime '{tool.runtime}' can vend this tool on demand." if tool.runtime != "binary" else ""
        notes = f"Executable '{version_cmd[0]}' not found on PATH. {runtime_note}".strip()
        return ToolStatus(
            name=tool.name,
            status=status,
            version=None,
            min_version=tool.min_version,
            executable=version_cmd[0],
            path=None,
            notes=notes,
            returncode=None,
            raw_output=None,
        )

    output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    output = output.strip()
    version = resolver.normalize(output.splitlines()[0] if output else None)

    if completed.returncode != 0:
        status = "not ok"
        notes = output or f"Exited with status {completed.returncode}."
    else:
        status = "ok"
        notes = output.splitlines()[0] if output else ""
        if tool.min_version and version and not resolver.is_compatible(version, tool.min_version):
            status = "outdated"
            notes = f"Detected {version}; requires ≥ {tool.min_version}."

    return ToolStatus(
        name=tool.name,
        status=status,
        version=version,
        min_version=tool.min_version,
        executable=version_cmd[0],
        path=path,
        notes=notes,
        returncode=completed.returncode,
        raw_output=output or None,
    )


def display_relative_path(path: Path, root: Path) -> str:
    """Return a stable display string for ``path`` relative to ``root`` when possible."""

    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        try:
            return str(path.resolve())
        except OSError:
            return str(path)


def filter_py_qa_paths(paths: Iterable[Path], root: Path) -> tuple[list[Path], list[str]]:
    """Drop py_qa paths when operating outside the py_qa workspace.

    Returns a tuple of ``(kept_paths, ignored_display_strings)``. Paths are
    resolved relative to ``root`` when necessary so callers can forward them to
    downstream logic without additional normalization.
    """

    root_resolved = root.resolve()
    if is_py_qa_workspace(root_resolved):
        return [(_maybe_resolve(path)) for path in paths], []

    kept: list[Path] = []
    ignored_display: list[str] = []
    for original in paths:
        resolved = _maybe_resolve(original, root_resolved)
        if resolved is None:
            continue
        if PY_QA_DIR_NAME in resolved.parts:
            ignored_display.append(display_relative_path(resolved, root_resolved))
            continue
        kept.append(resolved)
    return kept, ignored_display


def _maybe_resolve(path: Path, root: Path | None = None) -> Path | None:
    try:
        if path.is_absolute():
            return path.resolve()
        base = root if root is not None else Path.cwd()
        return (base / path).resolve()
    except OSError:
        base = root if root is not None else Path.cwd()
        return path if path.is_absolute() else base / path
