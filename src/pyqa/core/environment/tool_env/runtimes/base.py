# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime abstraction for preparing tool commands."""

from __future__ import annotations

import json
import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from pyqa.core.serialization import JsonValue
from pyqa.tools.base import Tool

from ..constants import ToolCacheLayout
from ..models import PreparedCommand
from ..utils import desired_version
from ..versioning import VersionResolver


@dataclass(frozen=True, slots=True)
class RuntimePreferences:
    """Manage the runtime selection behaviour toggles.

    Attributes:
        project_mode: Whether project-local binaries should be preferred.
        system_preferred: Whether system installations take precedence.
        use_local_override: Whether to force vendored runtimes regardless of availability.
    """

    project_mode: bool
    system_preferred: bool
    use_local_override: bool


@dataclass(frozen=True, slots=True)
class RuntimeEnvironment:
    """Describe the filesystem locations required for runtime execution.

    Attributes:
        root: Project root used when resolving binaries.
        cache_dir: Directory hosting cached runtime assets.
        cache_layout: Structured layout of runtime cache directories.
        pyqa_root: Root of the pyqa installation providing bundled runtimes.
    """

    root: Path
    cache_dir: Path
    cache_layout: ToolCacheLayout
    pyqa_root: Path


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    """Capture the inputs describing how a tool command should be prepared.

    Attributes:
        tool: Tool metadata describing runtime requirements.
        command: Command tuple requested by the caller.
        environment: Filesystem context used during preparation.
        preferences: Runtime strategy preferences to honour.
    """

    tool: Tool
    command: tuple[str, ...]
    environment: RuntimeEnvironment
    preferences: RuntimePreferences


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Maintain the immutable context passed to runtime strategy hooks.

    Attributes:
        tool: Tool metadata describing runtime requirements.
        command: Command tuple requested by the caller.
        root: Project root used when resolving binaries.
        cache_dir: Directory hosting cached runtime assets.
        target_version: Version requirement derived from tool metadata.
        cache_layout: Structured layout of runtime cache directories.
        pyqa_root: Root of the pyqa installation providing bundled runtimes.
    """

    tool: Tool
    command: tuple[str, ...]
    root: Path
    cache_dir: Path
    target_version: str | None
    cache_layout: ToolCacheLayout
    pyqa_root: Path

    def command_list(self) -> list[str]:
        """Return a mutable copy of the command sequence.

        Returns:
            list[str]: Copy of the original command tuple for mutation.
        """

        return list(self.command)

    @property
    def executable(self) -> str:
        """Return the first entry in the command sequence.

        Returns:
            str: Binary name referenced by the command tuple.
        """

        return self.command[0]


class _EnsureBinaryFn(Protocol):
    """Provide the binary provisioning contract for cached runtime commands."""

    def __call__(self, context: RuntimeContext, binary_name: str) -> Path:
        """Return the resolved binary path for ``binary_name``.

        Args:
            context: Runtime context describing command preparation parameters.
            binary_name: Executable name that must be provisioned.

        Returns:
            Path: Filesystem path to the resolved binary.
        """

        del context, binary_name
        return Path()

    @property
    def __name__(self) -> str:
        """Return the qualified name of the binary provider.

        Returns:
            str: Fully qualified name identifying the provider callable.
        """

        return ""


class _BuildEnvFn(Protocol):
    """Provide the environment construction contract for cached runtime commands."""

    def __call__(self, context: RuntimeContext) -> dict[str, str]:
        """Return the environment variables for ``context``.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            dict[str, str]: Environment overrides for the prepared command.
        """

        del context
        return {}

    @property
    def __name__(self) -> str:
        """Return the qualified name of the environment builder.

        Returns:
            str: Fully qualified name identifying the environment builder callable.
        """

        return ""


EnsureBinaryFn = _EnsureBinaryFn
BuildEnvFn = _BuildEnvFn


class RuntimeHandler(ABC):
    """Provide strategy for preparing tool commands per runtime."""

    def __init__(self, versions: VersionResolver) -> None:
        """Initialise the handler with a version resolver dependency.

        Args:
            versions: Resolver used to capture and compare tool versions.
        """

        self._versions = versions

    def prepare(self, request: RuntimeRequest) -> PreparedCommand:
        """Return a command prepared according to ``request`` parameters.

        Args:
            request: Fully populated runtime preparation request.

        Returns:
            PreparedCommand: Command resolved according to runtime strategy.
        """

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
        """Return a descriptive identifier for the runtime handler.

        Returns:
            str: Lower-case identifier derived from the concrete class name.
        """

        return self.__class__.__name__.removesuffix("Runtime").lower()

    def _try_system(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return a system-level command when available.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand | None: Prepared system command when compatible, otherwise ``None``.
        """

        return self._system_binary_with_version(context)

    @abstractmethod
    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return a project-local command when available.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand | None: Prepared project command when found, otherwise ``None``.
        """

    @abstractmethod
    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Provide the vendored command for the runtime.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand: Prepared command pointing to vendored tooling.
        """

    @staticmethod
    def _merge_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
        """Return a merged environment applying overrides to ``os.environ``.

        Args:
            overrides: Mapping of environment overrides to apply.

        Returns:
            dict[str, str]: Environment variables with overrides applied.
        """

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
        """Return a project binary command when ``subdir`` contains the executable.

        Args:
            context: Runtime context describing command preparation parameters.
            subdir: Directory name containing the project binary.

        Returns:
            PreparedCommand | None: Prepared command when the project binary exists, otherwise ``None``.
        """

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
        """Return a system command when the executable exists and matches versions.

        Args:
            context: Runtime context describing command preparation parameters.
            env: Optional environment variable overrides.

        Returns:
            PreparedCommand | None: Prepared command when system tooling satisfies version constraints.
        """

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
        """Compose the environment variables with ``bin_dir`` prefixed to ``PATH``.

        Args:
            bin_dir: Directory containing executables for the runtime.
            root: Project root used for the ``PWD`` environment variable.
            extra: Optional additional environment variables to merge.

        Returns:
            dict[str, str]: Environment containing the updated ``PATH`` value.
        """

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
        ensure_binary: EnsureBinaryFn,
        build_env: BuildEnvFn,
    ) -> PreparedCommand:
        """Return a prepared command after provisioning a cached binary.

        Args:
            context: Runtime execution context.
            ensure_binary: Callback that installs or retrieves the binary path
                for the requested command.
            build_env: Callback returning runtime environment variables for the prepared command.

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
    def _load_json(path: Path) -> dict[str, JsonValue] | None:
        """Return JSON content from ``path`` or ``None`` when parsing fails.

        Args:
            path: File path expected to contain JSON data.

        Returns:
            dict[str, JsonValue] | None: Parsed JSON mapping or ``None``.
        """

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        if isinstance(payload, dict):
            return cast(dict[str, JsonValue], payload)
        return None

    @staticmethod
    def _parse_json(text: str) -> dict[str, JsonValue] | None:
        """Return JSON payload parsed from ``text`` or ``None`` when invalid.

        Args:
            text: JSON text to parse.

        Returns:
            dict[str, JsonValue] | None: Parsed JSON mapping or ``None``.
        """

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return cast(dict[str, JsonValue], payload)
        return None


__all__ = [
    "RuntimeContext",
    "RuntimeEnvironment",
    "RuntimeHandler",
    "RuntimePreferences",
    "RuntimeRequest",
    "EnsureBinaryFn",
    "BuildEnvFn",
]
