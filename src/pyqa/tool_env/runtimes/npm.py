# SPDX-License-Identifier: MIT
"""Runtime handler for Node-based tooling."""

from __future__ import annotations

import json
import os
import shlex
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from ...environments import inject_node_defaults
from ...process_utils import SubprocessExecutionError, run_command
from ...tools.base import Tool
from .. import constants as tool_constants
from ..models import PreparedCommand
from ..utils import _slugify, _split_package_spec, desired_version
from .base import RuntimeHandler


class NpmRuntime(RuntimeHandler):
    """Provision Node-based tooling with cached installations."""

    META_FILE = ".pyqa-meta.json"

    def _try_system(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        executable = shutil.which(base_cmd[0])
        if not executable:
            return None
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        if not self._versions.is_compatible(version, target_version):
            return None
        return PreparedCommand.from_parts(cmd=base_cmd, env=None, version=version, source="system")

    def _try_project(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        bin_dir = root / "node_modules" / ".bin"
        executable = bin_dir / base_cmd[0]
        if not executable.exists():
            return None
        env_overrides = self._project_env(bin_dir, root)
        version = None
        if tool.version_command:
            version = self._versions.capture(
                tool.version_command,
                env=self._merge_env(env_overrides),
            )
        if not self._versions.is_compatible(version, target_version):
            return None
        cmd = list(base_cmd)
        cmd[0] = str(executable)
        return PreparedCommand.from_parts(
            cmd=cmd,
            env=env_overrides,
            version=version,
            source="project",
        )

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        prefix, cached_version = self._ensure_local_package(tool)
        bin_dir = prefix / "node_modules" / ".bin"
        executable = bin_dir / base_cmd[0]
        cmd = list(base_cmd)
        cmd[0] = str(executable)
        env = self._local_env(bin_dir, prefix, root)
        version = cached_version
        if version is None and tool.version_command:
            version = self._versions.capture(tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_package(self, tool: Tool) -> tuple[Path, str | None]:
        requirement = self._npm_requirement(tool)
        packages = shlex.split(requirement)
        if not packages:
            raise RuntimeError("No npm packages specified for tool")
        slug = _slugify(" ".join(packages))
        prefix = tool_constants.NODE_CACHE_DIR / slug
        meta_path = prefix / self.META_FILE
        bin_dir = prefix / "node_modules" / ".bin"
        if meta_path.is_file() and bin_dir.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                if data.get("requirement") == requirement:
                    return prefix, data.get("version")
            except json.JSONDecodeError:
                pass

        prefix.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        inject_node_defaults(env)
        env.setdefault("NPM_CONFIG_CACHE", str(tool_constants.NPM_CACHE_DIR))
        env.setdefault("npm_config_cache", str(tool_constants.NPM_CACHE_DIR))
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
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        deps = payload.get("dependencies") or {}
        entry = deps.get(package_name)
        if isinstance(entry, dict):
            return self._versions.normalize(entry.get("version"))
        return None

    @staticmethod
    def _project_env(bin_dir: Path, root: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        combined = f"{bin_dir}{os.pathsep}{path_value}" if path_value else str(bin_dir)
        return {
            "PATH": combined,
            "PWD": str(root),
            "NPM_CONFIG_CACHE": str(tool_constants.NPM_CACHE_DIR),
            "npm_config_cache": str(tool_constants.NPM_CACHE_DIR),
        }

    @staticmethod
    def _local_env(bin_dir: Path, prefix: Path, root: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        combined = f"{bin_dir}{os.pathsep}{path_value}" if path_value else str(bin_dir)
        return {
            "PATH": combined,
            "PWD": str(root),
            "NPM_CONFIG_CACHE": str(tool_constants.NPM_CACHE_DIR),
            "npm_config_cache": str(tool_constants.NPM_CACHE_DIR),
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
