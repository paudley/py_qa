# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Lua-based tooling via LuaRocks."""

from __future__ import annotations

import json
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from pyqa.core.runtime.process import CommandOptions, run_command
from pyqa.tools.base import Tool

from ..constants import RuntimeCachePaths
from ..models import PreparedCommand
from ..utils import _slugify, _split_package_spec
from .base import RuntimeContext, RuntimeHandler


@dataclass(frozen=True, slots=True)
class LuaInstallPaths:
    """Describe the filesystem paths used during Lua tool installation."""

    prefix: Path
    meta_file: Path
    binary: Path
    work_dir: Path


def _lua_install_paths(paths: RuntimeCachePaths, slug: str, binary_name: str) -> LuaInstallPaths:
    """Return the installation paths for the given slug and binary name.

    Args:
        paths: Runtime cache paths associated with Lua tooling.
        slug: Cache slug derived from the package requirement.
        binary_name: Target binary name produced by luarocks.

    Returns:
        LuaInstallPaths: Structured collection of installation directories.

    Raises:
        RuntimeError: If the cached runtime lacks a work directory.

    """

    if paths.work_dir is None:
        raise RuntimeError("Lua runtime cache layout is missing a work directory")
    return LuaInstallPaths(
        prefix=paths.cache_dir / slug,
        meta_file=paths.meta_dir / f"{slug}.json",
        binary=paths.bin_dir / binary_name,
        work_dir=paths.work_dir,
    )


class LuaRuntime(RuntimeHandler):
    """Provide the runtime for Lua tooling using LuaRocks."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return the project command when a Lua binary exists in the project.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand | None: Prepared project command, or ``None`` when absent.
        """

        return self._project_binary(context)

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Return the command after installing Lua tooling via LuaRocks.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand: Prepared command referencing the cached Lua binary.
        """
        return self._prepare_cached_command(
            context,
            self._ensure_local_tool,
            self._lua_env,
        )

    def _ensure_local_tool(self, context: RuntimeContext, binary_name: str) -> Path:
        """Ensure the binary ``binary_name`` is installed for the requested tool using LuaRocks.

        Args:
            context: Runtime context describing command preparation parameters.
            binary_name: Executable name expected in the Lua cache.

        Returns:
            Path: Filesystem path to the installed Lua binary.

        Raises:
            RuntimeError: If the binary cannot be installed or located.
        """

        tool = context.tool
        package, version = self._package_spec(tool)
        if not shutil.which("luarocks"):
            raise RuntimeError("luarocks is required to install Lua-based linters")

        slug = _slugify(f"{package}@{version or 'latest'}")
        lua_paths = _lua_install_paths(context.cache_layout.lua, slug, binary_name)

        if lua_paths.binary.exists() and lua_paths.meta_file.exists():
            metadata = self._load_json(lua_paths.meta_file)
            if metadata is not None:
                package_match = metadata.get("package") == package
                version_match = metadata.get("version") == version
                if package_match and version_match:
                    return lua_paths.binary

        lua_paths.prefix.mkdir(parents=True, exist_ok=True)
        lua_paths.meta_file.parent.mkdir(parents=True, exist_ok=True)
        lua_paths.binary.parent.mkdir(parents=True, exist_ok=True)
        lua_paths.work_dir.mkdir(parents=True, exist_ok=True)

        args = [
            "luarocks",
            "--tree",
            str(lua_paths.prefix),
            "install",
            package,
        ]
        if version:
            args.append(version)
        run_command(args, options=CommandOptions(capture_output=True))
        target = lua_paths.prefix / "bin" / binary_name
        if not target.exists():
            msg = f"Failed to install lua tool '{tool.name}'"
            raise RuntimeError(msg)

        shutil.copy2(target, lua_paths.binary)
        current_mode = lua_paths.binary.stat().st_mode
        lua_paths.binary.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        lua_paths.meta_file.write_text(
            json.dumps({"package": package, "version": version}),
            encoding="utf-8",
        )
        return lua_paths.binary

    @staticmethod
    def _package_spec(tool: Tool) -> tuple[str, str | None]:
        """Return the LuaRocks package and version tuple derived from the tool.

        Args:
            tool: Tool metadata describing the Lua package requirement.

        Returns:
            tuple[str, str | None]: Package name and optional version string.
        """
        if tool.package:
            package, version = _split_package_spec(tool.package)
            return package, version
        return tool.name, tool.min_version

    @staticmethod
    def _lua_env(context: RuntimeContext) -> dict[str, str]:
        """Return the environment variables required to execute Lua tools.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            dict[str, str]: Environment variables enabling the cached Lua runtime.
        """
        return RuntimeHandler._prepend_path_environment(
            bin_dir=context.cache_layout.lua.bin_dir,
            root=context.root,
        )


__all__ = ["LuaRuntime"]
