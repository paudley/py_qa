# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Node-based tooling."""

from __future__ import annotations

import json
import os
import shlex
import shutil as _shutil
from collections.abc import Mapping
from pathlib import Path

from ...environments import inject_node_defaults
from ...process_utils import SubprocessExecutionError, run_command
from ...tools.base import Tool
from ..models import PreparedCommand
from ..utils import _slugify, _split_package_spec, desired_version
from .base import RuntimeContext, RuntimeHandler

shutil = _shutil


class NpmRuntime(RuntimeHandler):
    """Provision Node-based tooling with cached installations."""

    META_FILE = ".pyqa-meta.json"

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Use a project-local Node binary located under ``node_modules/.bin``."""

        bin_dir = context.root / "node_modules" / ".bin"
        executable = bin_dir / context.executable
        if not executable.exists():
            return None
        env_overrides = self._project_env(context, bin_dir)
        version = None
        if context.tool.version_command:
            version = self._versions.capture(
                context.tool.version_command,
                env=self._merge_env(env_overrides),
            )
        if not self._versions.is_compatible(version, context.target_version):
            return None
        cmd = context.command_list()
        cmd[0] = str(executable)
        return PreparedCommand.from_parts(
            cmd=cmd,
            env=env_overrides,
            version=version,
            source="project",
        )

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Install npm packages into the cache and return the local command."""

        prefix, cached_version = self._ensure_local_package(context)
        bin_dir = prefix / "node_modules" / ".bin"
        executable = bin_dir / context.executable
        cmd = context.command_list()
        cmd[0] = str(executable)
        env = self._local_env(context, bin_dir, prefix)
        version = cached_version
        if version is None and context.tool.version_command:
            version = self._versions.capture(context.tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_package(self, context: RuntimeContext) -> tuple[Path, str | None]:
        tool = context.tool
        layout = context.cache_layout
        requirement = self._npm_requirement(tool)
        packages = shlex.split(requirement)
        if not packages:
            raise RuntimeError("No npm packages specified for tool")
        slug = _slugify(" ".join(packages))
        prefix = layout.node_cache_dir / slug
        meta_path = prefix / self.META_FILE
        bin_dir = prefix / "node_modules" / ".bin"
        if meta_path.is_file() and bin_dir.exists():
            data = self._load_json(meta_path)
            if data and data.get("requirement") == requirement:
                return prefix, data.get("version")

        prefix.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        inject_node_defaults(env)
        env.setdefault("NPM_CONFIG_CACHE", str(layout.npm_cache_dir))
        env.setdefault("npm_config_cache", str(layout.npm_cache_dir))
        env.setdefault("NPM_CONFIG_PREFIX", str(prefix))
        env.setdefault("npm_config_prefix", str(prefix))
        run_command(
            ["npm", "install", "--prefix", str(prefix), *packages],
            capture_output=True,
            env=env,
        )
        version = self._resolve_installed_version(prefix, tool, env)
        meta_path.write_text(
            json.dumps({"requirement": requirement, "version": version}),
            encoding="utf-8",
        )
        return prefix, version

    def _resolve_installed_version(
        self,
        prefix: Path,
        tool: Tool,
        env: Mapping[str, str],
    ) -> str | None:
        requirement = self._npm_requirement(tool)
        packages = shlex.split(requirement)
        if not packages:
            return None
        package_name, _ = _split_package_spec(packages[0])
        try:
            result = run_command(
                [
                    "npm",
                    "ls",
                    package_name,
                    "--prefix",
                    str(prefix),
                    "--depth",
                    "0",
                    "--json",
                ],
                capture_output=True,
                env=dict(env),
            )
        except (OSError, SubprocessExecutionError):
            return None
        payload = self._parse_json(result.stdout)
        if payload is None:
            return None
        deps = payload.get("dependencies") or {}
        entry = deps.get(package_name)
        if isinstance(entry, dict):
            return self._versions.normalize(entry.get("version"))
        return None

    @staticmethod
    def _project_env(context: RuntimeContext, bin_dir: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        combined = f"{bin_dir}{os.pathsep}{path_value}" if path_value else str(bin_dir)
        return {
            "PATH": combined,
            "PWD": str(context.root),
            "NPM_CONFIG_CACHE": str(context.cache_layout.npm_cache_dir),
            "npm_config_cache": str(context.cache_layout.npm_cache_dir),
        }

    @staticmethod
    def _local_env(context: RuntimeContext, bin_dir: Path, prefix: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        combined = f"{bin_dir}{os.pathsep}{path_value}" if path_value else str(bin_dir)
        return {
            "PATH": combined,
            "PWD": str(context.root),
            "NPM_CONFIG_CACHE": str(context.cache_layout.npm_cache_dir),
            "npm_config_cache": str(context.cache_layout.npm_cache_dir),
            "NPM_CONFIG_PREFIX": str(prefix),
            "npm_config_prefix": str(prefix),
        }

    def _npm_requirement(self, tool: Tool) -> str:
        if tool.package:
            return tool.package
        target = desired_version(tool)
        if target:
            return f"{tool.name}@{target}"
        return tool.name


__all__ = ["NpmRuntime"]
