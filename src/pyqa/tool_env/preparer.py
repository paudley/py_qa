# SPDX-License-Identifier: MIT
"""Facade for preparing commands via appropriate runtime handlers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..tools.base import Tool
from . import constants as tool_constants
from .models import PreparedCommand
from .runtimes.base import RuntimeHandler
from .runtimes.binary import BinaryRuntime
from .runtimes.go import GoRuntime
from .runtimes.lua import LuaRuntime
from .runtimes.npm import NpmRuntime
from .runtimes.perl import PerlRuntime
from .runtimes.python import PythonRuntime
from .runtimes.rust import RustRuntime
from .versioning import VersionResolver


class CommandPreparer:
    """Decide whether to use system, project, or vendored tooling."""

    def __init__(self) -> None:
        self._versions = VersionResolver()
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
        handler = self._handlers.get(tool.runtime, self._handlers["binary"])
        project_mode = (
            cache_dir / tool_constants.PROJECT_MARKER.name
        ).is_file() or tool_constants.PROJECT_MARKER.is_file()
        return handler.prepare(
            tool=tool,
            base_cmd=base_cmd,
            root=root,
            cache_dir=cache_dir,
            project_mode=project_mode,
            system_preferred=system_preferred,
            use_local_override=use_local_override,
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


__all__ = ["CommandPreparer"]
