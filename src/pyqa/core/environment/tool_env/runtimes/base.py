# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime abstraction for preparing tool commands."""

from __future__ import annotations

import json
import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pyqa.tools.base import Tool

from ..constants import ToolCacheLayout
from ..models import PreparedCommand
from ..utils import desired_version
from ..versioning import VersionResolver


@dataclass(frozen=True, slots=True)
class RuntimePreferences:
    """Toggle switches controlling runtime selection behaviour."""

    project_mode: bool
    system_preferred: bool
    use_local_override: bool


@dataclass(frozen=True, slots=True)
class RuntimeEnvironment:
    """Data describing filesystem locations for runtime execution."""

    root: Path
    cache_dir: Path
    cache_layout: ToolCacheLayout
    pyqa_root: Path


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    """Inputs describing how a tool command should be prepared."""

    tool: Tool
    command: tuple[str, ...]
    environment: RuntimeEnvironment
    preferences: RuntimePreferences


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Immutable context passed to runtime strategy hooks."""

    tool: Tool
    command: tuple[str, ...]
    root: Path
    cache_dir: Path
    target_version: str | None
    cache_layout: ToolCacheLayout
    pyqa_root: Path

    def command_list(self) -> list[str]:
        """Return a mutable copy of the command sequence."""

        return list(self.command)

    @property
    def executable(self) -> str:
        """Return the first entry in the command sequence."""

        return self.command[0]


class RuntimeHandler(ABC):
    """Strategy object responsible for preparing tool commands per runtime."""

    def __init__(self, versions: VersionResolver) -> None:
        self._versions = versions

    def prepare(self, request: RuntimeRequest) -> PreparedCommand:
        """Return a command prepared according to *request* parameters."""

        environment = request.environment
        preferences = request.preferences
        context = RuntimeContext(
            tool=request.tool,
            command=request.command,
            root=environment.root,
            cache_dir=environment.cache_dir,
            cache_layout=environment.cache_layout,
            target_version=desired_version(request.tool),
            pyqa_root=environment.pyqa_root,
        )

        if preferences.use_local_override or request.tool.prefer_local:
            return self._prepare_local(context)

        if preferences.project_mode:
            project_cmd = self._try_project(context)
            if project_cmd is not None:
                return project_cmd

        if preferences.system_preferred:
            system_cmd = self._try_system(context)
            if system_cmd is not None:
                return system_cmd

        fallback_project = self._try_project(context)
        if fallback_project is not None:
            return fallback_project

        return self._prepare_local(context)

    @property
    def kind(self) -> str:
        """Return a descriptive identifier for the runtime handler."""

        return self.__class__.__name__.removesuffix("Runtime").lower()

    def _try_system(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return a system-level command when available."""

        return self._system_binary_with_version(context)

    @abstractmethod
    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return a project-local command when available."""

    @abstractmethod
    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Provision and return a vendored command for the runtime."""

    @staticmethod
    def _merge_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
        """Return a merged environment applying *overrides* to ``os.environ``."""

        env = os.environ.copy()
        if overrides:
            env.update(overrides)
        return env

    def _project_binary(
        self,
        context: RuntimeContext,
        *,
        subdir: str = "bin",
    ) -> PreparedCommand | None:
        """Return a project binary command when ``subdir`` contains the executable."""

        binary_name = Path(context.executable).name
        candidate = context.root / subdir / binary_name
        if not candidate.exists():
            return None
        cmd = context.command_list()
        cmd[0] = str(candidate)
        return PreparedCommand.from_parts(
            cmd=cmd,
            env=None,
            version=None,
            source="project",
        )

    def _system_binary_with_version(
        self,
        context: RuntimeContext,
        *,
        env: Mapping[str, str] | None = None,
    ) -> PreparedCommand | None:
        """Return a system command when the executable exists and matches versions."""

        if not shutil.which(context.executable):
            return None
        version = None
        if context.tool.version_command:
            capture_env = self._merge_env(env) if env else None
            version = self._versions.capture(context.tool.version_command, env=capture_env)
        if not self._versions.is_compatible(version, context.target_version):
            return None
        return PreparedCommand.from_parts(
            cmd=context.command,
            env=env,
            version=version,
            source="system",
        )

    @staticmethod
    def _prepend_path_environment(
        *,
        bin_dir: Path,
        root: Path,
        extra: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Return environment variables with ``bin_dir`` prefixed to ``PATH``."""

        path_value = os.environ.get("PATH", "")
        entries = [str(bin_dir)]
        if path_value:
            entries.append(path_value)
        env = {
            "PATH": os.pathsep.join(entries),
            "PWD": str(root),
        }
        if extra:
            env.update(extra)
        return env

    def _prepare_cached_command(
        self,
        context: RuntimeContext,
        ensure_binary: Callable[[RuntimeContext, str], Path],
        build_env: Callable[[RuntimeContext], dict[str, str]],
    ) -> PreparedCommand:
        """Return a prepared command after provisioning a cached binary.

        Args:
            context: Runtime execution context.
            ensure_binary: Callable that installs or retrieves the binary path
                for the requested command.
            build_env: Callable returning runtime environment variables for the
                prepared command.

        Returns:
            PreparedCommand: Command configured to execute with cached tooling.
        """

        binary_name = Path(context.executable).name
        binary_path = ensure_binary(context, binary_name)
        command = context.command_list()
        command[0] = str(binary_path)
        env = build_env(context)
        version = None
        if context.tool.version_command:
            version = self._versions.capture(
                context.tool.version_command,
                env=self._merge_env(env),
            )
        return PreparedCommand.from_parts(cmd=command, env=env, version=version, source="local")

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any] | None:
        """Return JSON content from *path* or ``None`` when parsing fails."""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        if isinstance(payload, dict):
            return cast(dict[str, Any], payload)
        return None

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        """Return JSON payload parsed from *text* or ``None`` when invalid."""

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return cast(dict[str, Any], payload)
        return None


__all__ = [
    "RuntimeContext",
    "RuntimeEnvironment",
    "RuntimeHandler",
    "RuntimePreferences",
    "RuntimeRequest",
]
