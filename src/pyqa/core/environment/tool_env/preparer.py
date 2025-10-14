# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Facade for preparing commands via appropriate runtime handlers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyqa.platform.paths import get_pyqa_root
from pyqa.tools.base import Tool

from .constants import ToolCacheLayout, cache_layout
from .models import PreparedCommand
from .runtimes.base import (
    RuntimeEnvironment,
    RuntimeHandler,
    RuntimePreferences,
    RuntimeRequest,
)
from .runtimes.binary import BinaryRuntime
from .runtimes.go import GoRuntime
from .runtimes.lua import LuaRuntime
from .runtimes.npm import NpmRuntime
from .runtimes.perl import PerlRuntime
from .runtimes.python import PythonRuntime
from .runtimes.rust import RustRuntime
from .versioning import VersionResolver


@dataclass(frozen=True, slots=True)
class CommandPreparationRequest:
    """Inputs required to prepare a tool command."""

    tool: Tool
    command: tuple[str, ...]
    root: Path
    cache_dir: Path
    system_preferred: bool
    use_local_override: bool


class CommandPreparer:
    """Decide whether to use system, project, or vendored tooling."""

    def __init__(self) -> None:
        self._versions: VersionResolver = VersionResolver()
        self._handlers: dict[str, RuntimeHandler] = {
            "python": PythonRuntime(self._versions),
            "npm": NpmRuntime(self._versions),
            "go": GoRuntime(self._versions),
            "lua": LuaRuntime(self._versions),
            "perl": PerlRuntime(self._versions),
            "rust": RustRuntime(self._versions),
            "binary": BinaryRuntime(self._versions),
        }
        self._ensured_roots: set[Path] = set()
        self._pyqa_root: Path = get_pyqa_root()

    @property
    def available_runtimes(self) -> tuple[str, ...]:
        """Return the runtime identifiers managed by this preparer.

        Returns:
            tuple[str, ...]: Runtime identifiers recognised by the preparer.
        """

        return tuple(self._handlers)

    def prepare(
        self,
        request: CommandPreparationRequest | None = None,
        legacy_kwargs: LegacyCommandMapping | None = None,
    ) -> PreparedCommand:
        """Return a prepared command for *request* or legacy keyword arguments.

        Args:
            request: Fully populated command preparation request. When ``None``
                the deprecated mapping-based path is used.
            legacy_kwargs: Legacy keyword arguments accepted by the previous
                API shape.

        Returns:
            PreparedCommand: Command ready to execute with required tooling.

        Raises:
            TypeError: If both ``request`` and ``legacy_kwargs`` are provided or
                when required legacy arguments are missing.
        """

        legacy_mapping: dict[str, LegacyCommandValue] = dict(legacy_kwargs or {})
        if request is None:
            request = self._from_legacy_kwargs(legacy_mapping)
        elif legacy_mapping:
            raise TypeError("CommandPreparer.prepare() received unexpected legacy arguments")

        handler = self._handlers.get(request.tool.runtime, self._handlers["binary"])
        layout = cache_layout(request.cache_dir)
        self._ensure_dirs(layout)
        project_mode = layout.legacy_project_marker.is_file() or layout.project_marker.is_file()
        environment = RuntimeEnvironment(
            root=request.root,
            cache_dir=request.cache_dir,
            cache_layout=layout,
            pyqa_root=self._pyqa_root,
        )
        preferences = RuntimePreferences(
            project_mode=project_mode,
            system_preferred=request.system_preferred,
            use_local_override=request.use_local_override,
        )
        runtime_request = RuntimeRequest(
            tool=request.tool,
            command=request.command,
            environment=environment,
            preferences=preferences,
        )
        return handler.prepare(runtime_request)

    def _from_legacy_kwargs(self, legacy_kwargs: dict[str, LegacyCommandValue]) -> CommandPreparationRequest:
        """Build a request object from the legacy keyword-call style.

        Args:
            legacy_kwargs: Mapping of legacy keyword arguments.

        Returns:
            CommandPreparationRequest: Normalised request derived from legacy inputs.

        Raises:
            TypeError: If required arguments are missing or unexpected keys are supplied.
        """

        required_keys = (
            "tool",
            "base_cmd",
            "root",
            "cache_dir",
            "system_preferred",
            "use_local_override",
        )
        missing = [key for key in required_keys if key not in legacy_kwargs]
        if missing:  # pragma: no cover - mirrors legacy call expectations
            raise TypeError(f"Missing required legacy argument(s): {', '.join(sorted(missing))}")

        tool_value = legacy_kwargs.pop("tool")
        command_value = legacy_kwargs.pop("base_cmd")
        root_value = legacy_kwargs.pop("root")
        cache_dir_value = legacy_kwargs.pop("cache_dir")
        system_preferred_value = legacy_kwargs.pop("system_preferred")
        use_local_override_value = legacy_kwargs.pop("use_local_override")
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unexpected legacy arguments in prepare(): {unexpected}")
        if not isinstance(command_value, Sequence):
            raise TypeError("base_cmd must be a sequence of strings")
        command_seq = tuple(str(part) for part in command_value)
        root_path = root_value if isinstance(root_value, Path) else Path(str(root_value))
        cache_path = cache_dir_value if isinstance(cache_dir_value, Path) else Path(str(cache_dir_value))
        if not isinstance(tool_value, Tool):
            raise TypeError("tool must be an instance of Tool")
        return CommandPreparationRequest(
            tool=tool_value,
            command=command_seq,
            root=root_path,
            cache_dir=cache_path,
            system_preferred=bool(system_preferred_value),
            use_local_override=bool(use_local_override_value),
        )

    def _ensure_dirs(self, layout: ToolCacheLayout) -> None:
        """Ensure cache directories for ``layout`` exist exactly once."""

        root = layout.tools_root.resolve()
        if root in self._ensured_roots:
            return
        layout.ensure_directories()
        self._ensured_roots.add(root)

    def prepare_request(self, request: CommandPreparationRequest) -> PreparedCommand:
        """Prepare a command described by ``request``.

        Args:
            request: Fully normalised command preparation request.

        Returns:
            PreparedCommand: Command ready for execution.
        """

        return self.prepare(request=request)

    def prepare_from_mapping(self, legacy_kwargs: LegacyCommandMapping) -> PreparedCommand:
        """Prepare a command using the legacy keyword argument contract."""

        return self.prepare(legacy_kwargs=legacy_kwargs)


__all__ = [
    "CommandPreparationRequest",
    "CommandPreparer",
    "LegacyCommandMapping",
]

LegacyCommandValue = Tool | Sequence[str] | Path | bool
LegacyCommandMapping = Mapping[str, LegacyCommandValue]
