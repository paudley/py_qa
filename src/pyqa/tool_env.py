# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Determine how to execute tooling commands based on environment preferences."""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404 - subprocess used for controlled version checks
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from packaging.version import InvalidVersion, Version

from .tools.base import Tool

PYQA_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = PYQA_ROOT / ".tool-cache"
UV_CACHE_DIR = CACHE_ROOT / "uv"
NPM_CACHE_DIR = CACHE_ROOT / "npm"
NPM_PREFIX_DIR = CACHE_ROOT / "npm-prefix"
PROJECT_MARKER = CACHE_ROOT / "project-installed.json"


@dataclass(slots=True)
class PreparedCommand:
    """Command ready for execution including environment metadata."""

    cmd: list[str]
    env: dict[str, str]
    version: str | None
    source: str  # system | local | project


class CommandPreparer:
    """Decide whether to use system, project, or vendored tooling."""

    def __init__(self) -> None:
        self._ensure_dirs()

    def prepare(
        self,
        *,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        system_preferred: bool,
        use_local_override: bool,
    ) -> PreparedCommand:
        """Compute the concrete command used to execute *tool*."""

        project_mode = (
            cache_dir / PROJECT_MARKER.name
        ).is_file() or PROJECT_MARKER.is_file()
        env: dict[str, str] = {}

        if use_local_override or tool.prefer_local:
            source = "local"
        elif project_mode:
            source = "project"
        else:
            system_ok, version = self._system_version(tool)
            if system_preferred and system_ok:
                return PreparedCommand(
                    cmd=list(base_cmd), env={}, version=version, source="system"
                )
            source = "local"

        if source == "project":
            version = None
            if tool.version_command:
                version = self._capture_version(tool.version_command)
            return PreparedCommand(
                cmd=list(base_cmd), env={}, version=version, source="project"
            )

        if tool.runtime == "python":
            cmd = self._python_local_command(tool, base_cmd)
            env.update(self._python_env())
        elif tool.runtime == "npm":
            cmd = self._npm_local_command(tool, base_cmd)
            env.update(self._npm_env(root))
        else:
            cmd = list(base_cmd)

        if tool.version_command:
            version = self._capture_version(tool.version_command)
        else:
            version = None

        return PreparedCommand(cmd=cmd, env=env, version=version, source="local")

    def _python_local_command(self, tool: Tool, base_cmd: Sequence[str]) -> list[str]:
        requirement = tool.package or tool.name
        if tool.min_version:
            requirement = f"{requirement}=={tool.min_version}"
        return [
            "uv",
            "--project",
            str(PYQA_ROOT),
            "run",
            "--with",
            requirement,
            *base_cmd,
        ]

    def _python_env(self) -> dict[str, str]:
        return {
            "UV_CACHE_DIR": str(UV_CACHE_DIR),
            "UV_PROJECT": str(PYQA_ROOT),
        }

    def _npm_local_command(self, tool: Tool, base_cmd: Sequence[str]) -> list[str]:
        package = tool.package or tool.name
        args = list(base_cmd)
        tail = args[1:]
        return ["npx", "--yes", package, *tail]

    def _npm_env(self, root: Path) -> dict[str, str]:
        env = {
            "NPM_CONFIG_CACHE": str(NPM_CACHE_DIR),
            "NPM_CONFIG_PREFIX": str(NPM_PREFIX_DIR),
        }
        path_entries = [str(NPM_PREFIX_DIR / "bin")]
        path_entries.extend(os.environ.get("PATH", "").split(os.pathsep))
        env["PATH"] = os.pathsep.join(path_entries)
        env.setdefault("PWD", str(root))
        return env

    def _system_version(self, tool: Tool) -> tuple[bool, str | None]:
        if tool.version_command is None:
            executable = tool.name
            if shutil.which(executable):
                return True, None
            return False, None
        command = list(tool.version_command)
        if not shutil.which(command[0]):
            return False, None
        output = self._capture_version(command)
        if tool.min_version and not output:
            return False, None
        if tool.min_version and output:
            try:
                if Version(self._normalize_version(output)) < Version(tool.min_version):
                    return False, output
            except InvalidVersion:
                return False, output
        return True, output

    def _capture_version(self, command: Sequence[str]) -> str | None:
        try:
            completed = subprocess.run(  # nosec B603
                list(command),
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        text = completed.stdout.strip() or completed.stderr.strip()
        return text.splitlines()[0] if text else None

    def _normalize_version(self, raw: str) -> str:
        match = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
        return match.group(1) if match else raw

    def _ensure_dirs(self) -> None:
        UV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        NPM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (NPM_PREFIX_DIR / "bin").mkdir(parents=True, exist_ok=True)
