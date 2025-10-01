# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Lua-based tooling via LuaRocks."""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path

from ...process_utils import run_command
from ...tools.base import Tool
from .. import constants as tool_constants
from ..models import PreparedCommand
from ..utils import _slugify, _split_package_spec
from .base import RuntimeContext, RuntimeHandler


class LuaRuntime(RuntimeHandler):
    """Provision Lua tooling using luarocks."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Select project-local Lua binary when present."""

        return self._project_binary(context)

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Install Lua tooling via luarocks into the shared cache."""

        binary_name = Path(context.executable).name
        binary_path = self._ensure_local_tool(context.tool, binary_name)
        cmd = context.command_list()
        cmd[0] = str(binary_path)
        env = self._lua_env(context.root)
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        """Ensure ``binary_name`` is installed for ``tool`` using luarocks."""

        package, version = self._package_spec(tool)
        if not shutil.which("luarocks"):
            raise RuntimeError("luarocks is required to install Lua-based linters")

        slug = _slugify(f"{package}@{version or 'latest'}")
        prefix = tool_constants.LUA_CACHE_DIR / slug
        meta_file = tool_constants.LUA_META_DIR / f"{slug}.json"
        binary = tool_constants.LUA_BIN_DIR / binary_name

        if binary.exists() and meta_file.exists():
            meta = self._load_json(meta_file)
            if meta and meta.get("package") == package and meta.get("version") == version:
                return binary

        prefix.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_META_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_BIN_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_WORK_DIR.mkdir(parents=True, exist_ok=True)

        args = [
            "luarocks",
            "--tree",
            str(prefix),
            "install",
            package,
        ]
        if version:
            args.append(version)
        run_command(args, capture_output=True)
        target = prefix / "bin" / binary_name
        if not target.exists():
            msg = f"Failed to install lua tool '{tool.name}'"
            raise RuntimeError(msg)

        shutil.copy2(target, binary)
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        meta_file.write_text(
            json.dumps({"package": package, "version": version}),
            encoding="utf-8",
        )
        return binary

    @staticmethod
    def _package_spec(tool: Tool) -> tuple[str, str | None]:
        """Return LuaRocks package and version tuple derived from ``tool``."""
        if tool.package:
            package, version = _split_package_spec(tool.package)
            return package, version
        return tool.name, tool.min_version

    @staticmethod
    def _lua_env(root: Path) -> dict[str, str]:
        """Return environment variables required to execute Lua tools."""
        return RuntimeHandler._prepend_path_environment(bin_dir=tool_constants.LUA_BIN_DIR, root=root)


__all__ = ["LuaRuntime"]
