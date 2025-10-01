# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Facade for preparing commands via appropriate runtime handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast
from collections.abc import Sequence

from ..tools.base import Tool
from . import constants as tool_constants
from .models import PreparedCommand
from .runtimes.base import RuntimeHandler, RuntimeRequest
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
        self._ensure_dirs()

    @property
    def available_runtimes(self) -> tuple[str, ...]:
        """Return the runtime identifiers managed by this preparer."""

        return tuple(self._handlers)

    def prepare(
        self,
        request: CommandPreparationRequest | None = None,
        **legacy_kwargs: object,
    ) -> PreparedCommand:
        """Return a prepared command for *request* or legacy keyword args."""

        if request is None:
            request = self._from_legacy_kwargs(legacy_kwargs)
        elif legacy_kwargs:
            raise TypeError("CommandPreparer.prepare() received unexpected legacy arguments")

        handler = self._handlers.get(request.tool.runtime, self._handlers["binary"])
        project_mode = (
            request.cache_dir / tool_constants.PROJECT_MARKER.name
        ).is_file() or tool_constants.PROJECT_MARKER.is_file()
        runtime_request = RuntimeRequest(
            tool=request.tool,
            command=request.command,
            root=request.root,
            cache_dir=request.cache_dir,
            project_mode=project_mode,
            system_preferred=request.system_preferred,
            use_local_override=request.use_local_override,
        )
        return handler.prepare(runtime_request)

    def _from_legacy_kwargs(self, legacy_kwargs: dict[str, object]) -> CommandPreparationRequest:
        """Build a request object from the legacy keyword-call style."""

        try:
            tool = legacy_kwargs.pop("tool")
            command = legacy_kwargs.pop("base_cmd")
            root = legacy_kwargs.pop("root")
            cache_dir = legacy_kwargs.pop("cache_dir")
            system_preferred = legacy_kwargs.pop("system_preferred")
            use_local_override = legacy_kwargs.pop("use_local_override")
        except KeyError as exc:  # pragma: no cover - mirrors legacy call expectations
            missing = exc.args[0]
            raise TypeError(f"Missing required legacy argument '{missing}'") from exc
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unexpected legacy arguments in prepare(): {unexpected}")
        if not isinstance(command, (tuple, list)):
            raise TypeError("base_cmd must be a sequence of strings")
        return CommandPreparationRequest(
            tool=cast(Tool, tool),
            command=tuple(cast("Sequence[str]", command)),
            root=cast(Path, root),
            cache_dir=cast(Path, cache_dir),
            system_preferred=bool(system_preferred),
            use_local_override=bool(use_local_override),
        )

    def _ensure_dirs(self) -> None:
        tool_constants.UV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.NODE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.NPM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.GO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.GO_BIN_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_BIN_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_META_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.RUST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.RUST_BIN_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.RUST_META_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.PERL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.PERL_BIN_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.PERL_META_DIR.mkdir(parents=True, exist_ok=True)


__all__ = ["CommandPreparationRequest", "CommandPreparer"]
