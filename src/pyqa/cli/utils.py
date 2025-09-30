# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared helpers for CLI commands."""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from ..constants import PY_QA_DIR_NAME
from ..filesystem.paths import display_relative_path, normalize_path
from ..process_utils import run_command
from ..tool_env import VersionResolver
from ..tools.base import Tool
from ..workspace import is_py_qa_workspace


class ToolAvailability(str, Enum):
    """Enumerate high-level availability states for CLI tooling."""

    UNKNOWN = "unknown"
    VENDORED = "vendored"
    UNINSTALLED = "uninstalled"
    NOT_OK = "not ok"
    OK = "ok"
    OUTDATED = "outdated"


@dataclass(slots=True)
class ToolVersionStatus:
    """Captured version metadata for a CLI tool."""

    detected: str | None
    minimum: str | None


@dataclass(slots=True)
class ToolExecutionDetails:
    """Captured executable details and exit metadata for a CLI tool."""

    executable: str | None
    path: str | None
    returncode: int | None


BINARY_RUNTIME: Final[str] = "binary"


@dataclass(slots=True)
class ToolStatus:
    """Aggregated status information for doctor-style tooling checks."""

    name: str
    availability: ToolAvailability
    notes: str
    version: ToolVersionStatus
    execution: ToolExecutionDetails
    raw_output: str | None


def check_tool_status(tool: Tool) -> ToolStatus:
    """Return ``ToolStatus`` describing availability and version information for a tool.

    Args:
        tool: Tool instance describing the command to probe.

    Returns:
        ToolStatus: Collected status, version, and execution metadata.

    """

    version_cmd: Sequence[str] | None = tool.version_command
    executable = version_cmd[0] if version_cmd else None
    path = shutil.which(executable) if executable else None
    resolver = VersionResolver()

    if not version_cmd:
        notes = "Tool does not define a version command; status derived from runtime availability."
        availability = ToolAvailability.UNKNOWN
        if tool.runtime != BINARY_RUNTIME:
            availability = ToolAvailability.VENDORED
            notes = f"Provisioned via runtime '{tool.runtime}' when needed."
        return ToolStatus(
            name=tool.name,
            availability=availability,
            notes=notes,
            version=ToolVersionStatus(detected=None, minimum=tool.min_version),
            execution=ToolExecutionDetails(executable=None, path=None, returncode=None),
            raw_output=None,
        )

    try:
        completed = run_command(
            list(version_cmd),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        availability = ToolAvailability.VENDORED if tool.runtime != BINARY_RUNTIME else ToolAvailability.UNINSTALLED
        runtime_note = (
            f"Runtime '{tool.runtime}' can vend this tool on demand." if tool.runtime != BINARY_RUNTIME else ""
        )
        notes = f"Executable '{version_cmd[0]}' not found on PATH. {runtime_note}".strip()
        return ToolStatus(
            name=tool.name,
            availability=availability,
            notes=notes,
            version=ToolVersionStatus(detected=None, minimum=tool.min_version),
            execution=ToolExecutionDetails(executable=version_cmd[0], path=None, returncode=None),
            raw_output=None,
        )

    output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    output = output.strip()
    version = resolver.normalize(output.splitlines()[0] if output else None)

    availability = ToolAvailability.OK
    notes = output.splitlines()[0] if output else ""
    if completed.returncode != 0:
        availability = ToolAvailability.NOT_OK
        notes = output or f"Exited with status {completed.returncode}."
    elif tool.min_version and version and not resolver.is_compatible(version, tool.min_version):
        availability = ToolAvailability.OUTDATED
        notes = f"Detected {version}; requires ≥ {tool.min_version}."

    return ToolStatus(
        name=tool.name,
        availability=availability,
        notes=notes,
        version=ToolVersionStatus(detected=version, minimum=tool.min_version),
        execution=ToolExecutionDetails(
            executable=version_cmd[0],
            path=path,
            returncode=completed.returncode,
        ),
        raw_output=output or None,
    )


def filter_py_qa_paths(paths: Iterable[Path], root: Path) -> tuple[list[Path], list[str]]:
    """Drop py_qa paths when operating outside the py_qa workspace.

    Args:
        paths: Iterable of filesystem paths provided by the caller.
        root: Root directory against which relative paths are resolved.

    Returns:
        tuple[list[Path], list[str]]: Pair of kept paths and ignored display
        strings for reporting.

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
    """Safely resolve ``path`` relative to ``root`` while handling errors.

    Args:
        path: Path candidate supplied by the caller.
        root: Optional base directory for relative resolution.

    Returns:
        Path | None: Resolved path or ``None`` when resolution fails.

    """
    base = root.resolve() if root is not None else Path.cwd()
    try:
        normalised = normalize_path(path, base_dir=base)
    except (ValueError, OSError):
        try:
            return path.resolve()
        except OSError:
            return None
    if normalised.is_absolute():
        try:
            return normalised.resolve()
        except OSError:
            return normalised
    try:
        return (base / normalised).resolve()
    except OSError:
        return (base / normalised).absolute()
