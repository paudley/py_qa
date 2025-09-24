# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared helpers for CLI commands."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from ..process_utils import SubprocessExecutionError, run_command
from ..tool_env import VersionResolver
from ..tools.base import Tool

PYQA_ROOT = Path(__file__).resolve().parent.parent


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


def installed_packages() -> set[str]:
    """Return the set of installed packages within the project environment."""

    try:
        completed = run_command(
            ["uv", "pip", "list", "--format=json"],
            check=True,
            capture_output=True,
            cwd=PYQA_ROOT,
        )
    except (OSError, SubprocessExecutionError):
        return set()
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return set()
    return {
        str(item.get("name", "")).lower()
        for item in data
        if isinstance(item, dict) and item.get("name")
    }


def run_uv(args: List[str], *, check: bool = True) -> None:
    """Invoke ``uv`` with *args* relative to the project root."""

    run_command(args, check=check, cwd=PYQA_ROOT)


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
        runtime_note = (
            f"Runtime '{tool.runtime}' can vend this tool on demand."
            if tool.runtime != "binary"
            else ""
        )
        notes = (
            f"Executable '{version_cmd[0]}' not found on PATH. {runtime_note}".strip()
        )
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

    output = (completed.stdout or "") + (
        "\n" + completed.stderr if completed.stderr else ""
    )
    output = output.strip()
    version = resolver.normalize(output.splitlines()[0] if output else None)

    if completed.returncode != 0:
        status = "not ok"
        notes = output or f"Exited with status {completed.returncode}."
    else:
        status = "ok"
        notes = output.splitlines()[0] if output else ""
        if (
            tool.min_version
            and version
            and not resolver.is_compatible(version, tool.min_version)
        ):
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
