# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Determine how to execute tooling commands based on environment preferences."""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404 - subprocess used for controlled version checks
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from packaging.version import InvalidVersion, Version

import json
import shlex

from .environments import inject_node_defaults
from .tools.base import Tool

PYQA_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = PYQA_ROOT / ".tool-cache"
UV_CACHE_DIR = CACHE_ROOT / "uv"
NODE_CACHE_DIR = CACHE_ROOT / "node"
NPM_CACHE_DIR = CACHE_ROOT / "npm"
PROJECT_MARKER = CACHE_ROOT / "project-installed.json"
GO_CACHE_DIR = CACHE_ROOT / "go"
GO_BIN_DIR = GO_CACHE_DIR / "bin"
GO_META_DIR = GO_CACHE_DIR / "meta"
GO_WORK_DIR = GO_CACHE_DIR / "work"
LUA_CACHE_DIR = CACHE_ROOT / "lua"
LUA_BIN_DIR = LUA_CACHE_DIR / "bin"
LUA_META_DIR = LUA_CACHE_DIR / "meta"
LUA_WORK_DIR = LUA_CACHE_DIR / "lua"
RUST_CACHE_DIR = CACHE_ROOT / "rust"
RUST_BIN_DIR = RUST_CACHE_DIR / "bin"
RUST_META_DIR = RUST_CACHE_DIR / "meta"
RUST_WORK_DIR = RUST_CACHE_DIR / "work"
PERL_CACHE_DIR = CACHE_ROOT / "perl"
PERL_BIN_DIR = PERL_CACHE_DIR / "bin"
PERL_META_DIR = PERL_CACHE_DIR / "meta"


@dataclass(slots=True)
class PreparedCommand:
    """Command ready for execution including environment metadata."""

    cmd: list[str]
    env: dict[str, str]
    version: str | None
    source: str  # system | local | project


class VersionResolver:
    """Capture and compare tool versions using standardized semantics."""

    VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)+)")

    def capture(self, command: Sequence[str], *, env: Mapping[str, str] | None = None) -> str | None:
        """Return the normalized version string from ``command`` if available."""

        try:
            completed = subprocess.run(  # nosec B603 - controlled command
                list(command),
                capture_output=True,
                text=True,
                check=True,
                env=dict(env) if env else None,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        output = completed.stdout.strip() or completed.stderr.strip()
        if not output:
            return None
        first_line = output.splitlines()[0].strip()
        return self.normalize(first_line)

    def normalize(self, raw: str | None) -> str | None:
        if not raw:
            return None
        match = self.VERSION_PATTERN.search(raw)
        candidate = match.group(1) if match else raw.strip()
        try:
            Version(candidate)
        except InvalidVersion:
            return None
        return candidate

    def is_compatible(self, actual: str | None, expected: str | None) -> bool:
        if expected is None:
            return True
        if actual is None:
            return False
        try:
            return Version(actual) >= Version(expected)
        except InvalidVersion:
            return False


class RuntimeHandler(ABC):
    """Strategy object responsible for preparing tool commands per runtime."""

    def __init__(self, versions: VersionResolver) -> None:
        self._versions = versions

    def prepare(
        self,
        *,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        project_mode: bool,
        system_preferred: bool,
        use_local_override: bool,
    ) -> PreparedCommand:
        target_version = desired_version(tool)

        if use_local_override or tool.prefer_local:
            return self._prepare_local(tool, base_cmd, root, cache_dir, target_version)

        if project_mode:
            project_cmd = self._try_project(tool, base_cmd, root, cache_dir, target_version)
            if project_cmd:
                return project_cmd

        if system_preferred:
            system_cmd = self._try_system(tool, base_cmd, root, cache_dir, target_version)
            if system_cmd:
                return system_cmd

        # Opportunistically re-check project installs even if not in explicit project mode.
        project_cmd = self._try_project(tool, base_cmd, root, cache_dir, target_version)
        if project_cmd:
            return project_cmd

        return self._prepare_local(tool, base_cmd, root, cache_dir, target_version)

    def _try_system(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        return None

    def _try_project(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        return None

    @abstractmethod
    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        ...

    @staticmethod
    def _merge_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        if overrides:
            env.update(overrides)
        return env


class PythonRuntime(RuntimeHandler):
    """Provision Python tools via uv with system/project fallbacks."""

    def _try_system(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        executable = base_cmd[0]
        if not shutil.which(executable):
            return None
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        if not self._versions.is_compatible(version, target_version):
            return None
        return PreparedCommand(cmd=list(base_cmd), env={}, version=version, source="system")

    def _try_project(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        if version is None and target_version is not None:
            return None
        if not self._versions.is_compatible(version, target_version):
            return None
        return PreparedCommand(cmd=list(base_cmd), env={}, version=version, source="project")

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        requirement = tool.package or tool.name
        if tool.min_version:
            requirement = f"{requirement}=={tool.min_version}"
        cmd = [
            "uv",
            "--project",
            str(PYQA_ROOT),
            "run",
            "--with",
            requirement,
            *base_cmd,
        ]
        env = {
            "UV_CACHE_DIR": str(UV_CACHE_DIR),
            "UV_PROJECT": str(PYQA_ROOT),
        }
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        return PreparedCommand(cmd=cmd, env=env, version=version, source="local")


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
        return PreparedCommand(cmd=list(base_cmd), env={}, version=version, source="system")

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
            version = self._versions.capture(tool.version_command, env=self._merge_env(env_overrides))
        if not self._versions.is_compatible(version, target_version):
            return None
        cmd = list(base_cmd)
        cmd[0] = str(executable)
        return PreparedCommand(cmd=cmd, env=env_overrides, version=version, source="project")

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
        return PreparedCommand(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_package(self, tool: Tool) -> tuple[Path, str | None]:
        requirement = self._npm_requirement(tool)
        packages = shlex.split(requirement)
        if not packages:
            raise RuntimeError("No npm packages specified for tool")
        slug = _slugify(" ".join(packages))
        prefix = NODE_CACHE_DIR / slug
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
        env.setdefault("NPM_CONFIG_CACHE", str(NPM_CACHE_DIR))
        env.setdefault("npm_config_cache", str(NPM_CACHE_DIR))
        env.setdefault("NPM_CONFIG_PREFIX", str(prefix))
        env.setdefault("npm_config_prefix", str(prefix))
        subprocess.run(  # nosec B603 - controlled installation
            ["npm", "install", "--prefix", str(prefix), *packages],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        version = self._resolve_installed_version(prefix, tool, env)
        meta_path.write_text(
            json.dumps({"requirement": requirement, "version": version}),
            encoding="utf-8",
        )
        return prefix, version

    def _resolve_installed_version(self, prefix: Path, tool: Tool, env: Mapping[str, str]) -> str | None:
        requirement = self._npm_requirement(tool)
        packages = shlex.split(requirement)
        if not packages:
            return None
        package_name, _ = _split_package_spec(packages[0])
        try:
            result = subprocess.run(  # nosec B603 - controlled query
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
                text=True,
                check=True,
                env=dict(env),
            )
        except (OSError, subprocess.CalledProcessError):
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
            "NPM_CONFIG_CACHE": str(NPM_CACHE_DIR),
            "npm_config_cache": str(NPM_CACHE_DIR),
        }

    @staticmethod
    def _local_env(bin_dir: Path, prefix: Path, root: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        combined = f"{bin_dir}{os.pathsep}{path_value}" if path_value else str(bin_dir)
        return {
            "PATH": combined,
            "PWD": str(root),
            "NPM_CONFIG_CACHE": str(NPM_CACHE_DIR),
            "npm_config_cache": str(NPM_CACHE_DIR),
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


class GoRuntime(RuntimeHandler):
    """Provision Go tooling by installing modules into a dedicated cache."""

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
        return PreparedCommand(cmd=list(base_cmd), env={}, version=version, source="system")

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        if not shutil.which("go"):
            raise RuntimeError("Go toolchain is required to install go-based linters")

        binary_name = Path(base_cmd[0]).name
        binary_path = self._ensure_local_tool(tool, binary_name)

        cmd = list(base_cmd)
        cmd[0] = str(binary_path)

        env = self._go_env(root)
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command, env=self._merge_env(env))
        return PreparedCommand(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        module, version_spec = self._module_spec(tool)
        if not version_spec:
            version_spec = "latest"
        requirement = f"{module}@{version_spec}"
        slug = _slugify(requirement)
        meta_file = GO_META_DIR / f"{slug}.json"
        binary = GO_BIN_DIR / binary_name

        if binary.exists() and meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("requirement") == requirement:
                    return binary
            except json.JSONDecodeError:
                pass

        GO_META_DIR.mkdir(parents=True, exist_ok=True)
        GO_BIN_DIR.mkdir(parents=True, exist_ok=True)
        (GO_WORK_DIR / "gopath").mkdir(parents=True, exist_ok=True)
        (GO_WORK_DIR / "gocache").mkdir(parents=True, exist_ok=True)
        (GO_WORK_DIR / "modcache").mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.setdefault("GOBIN", str(GO_BIN_DIR))
        env.setdefault("GOCACHE", str(GO_WORK_DIR / "gocache"))
        env.setdefault("GOMODCACHE", str(GO_WORK_DIR / "modcache"))
        env.setdefault("GOPATH", str(GO_WORK_DIR / "gopath"))

        subprocess.run(  # nosec B603 - controlled go install
            ["go", "install", requirement],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )

        if not binary.exists():
            raise RuntimeError(f"Failed to install go tool '{tool.name}'")

        meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary

    @staticmethod
    def _module_spec(tool: Tool) -> tuple[str, str | None]:
        if tool.package:
            module, version = _split_package_spec(tool.package)
            return module, version
        return tool.name, tool.min_version

    @staticmethod
    def _go_env(root: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        entries = [str(GO_BIN_DIR)]
        if path_value:
            entries.append(path_value)
        return {
            "PATH": os.pathsep.join(entries),
            "PWD": str(root),
        }


class LuaRuntime(RuntimeHandler):
    """Provision Lua tooling using luarocks."""

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
        return PreparedCommand(cmd=list(base_cmd), env={}, version=version, source="system")

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        if not shutil.which("luarocks"):
            raise RuntimeError("luarocks is required to install Lua-based linters")

        binary_name = Path(base_cmd[0]).name
        binary_path = self._ensure_local_tool(tool, binary_name)
        cmd = list(base_cmd)
        cmd[0] = str(binary_path)

        env = self._lua_env(binary_path.parent)
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command, env=self._merge_env(env))
        return PreparedCommand(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        package, version_spec = self._package_spec(tool)
        requirement = f"{package}@{version_spec}" if version_spec else package
        slug = _slugify(requirement)
        prefix = LUA_CACHE_DIR / slug
        binary = prefix / "bin" / binary_name
        meta_file = LUA_META_DIR / f"{slug}.json"

        if binary.exists() and meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("requirement") == requirement:
                    return binary
            except json.JSONDecodeError:
                pass

        meta_file.parent.mkdir(parents=True, exist_ok=True)
        (prefix / "bin").mkdir(parents=True, exist_ok=True)

        install_cmd = ["luarocks", "install", package]
        if version_spec:
            install_cmd.append(str(version_spec))
        install_cmd.extend(["--tree", str(prefix)])

        subprocess.run(  # nosec B603 - controlled luarocks install
            install_cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        if not binary.exists():
            raise RuntimeError(f"Failed to install Lua tool '{tool.name}'")

        meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary

    @staticmethod
    def _package_spec(tool: Tool) -> tuple[str, str | None]:
        if tool.package:
            package, version = _split_package_spec(tool.package)
            if version is None:
                version = tool.min_version
            return package, version
        return tool.name, tool.min_version

    @staticmethod
    def _lua_env(bin_dir: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        entries = [str(bin_dir)]
        if path_value:
            entries.append(path_value)
        return {
            "PATH": os.pathsep.join(entries),
        }


class PerlRuntime(RuntimeHandler):
    """Provision Perl tooling using cpanm into a local cache."""

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
        return PreparedCommand(cmd=list(base_cmd), env={}, version=version, source="system")

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        if not shutil.which("cpanm"):
            raise RuntimeError("cpanm is required to install Perl-based tools")

        binary_name = Path(base_cmd[0]).name
        binary_path = self._ensure_local_tool(tool, binary_name)
        cmd = list(base_cmd)
        cmd[0] = str(binary_path)

        env = self._perl_env(binary_path.parent)
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command, env=self._merge_env(env))
        return PreparedCommand(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        package, version_spec = self._package_spec(tool)
        requirement = f"{package}@{version_spec}" if version_spec else package
        slug = _slugify(requirement)
        prefix = PERL_CACHE_DIR / slug
        binary = prefix / "bin" / binary_name
        meta_file = PERL_META_DIR / f"{slug}.json"

        if binary.exists() and meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("requirement") == requirement:
                    return binary
            except json.JSONDecodeError:
                pass

        meta_file.parent.mkdir(parents=True, exist_ok=True)
        (prefix / "bin").mkdir(parents=True, exist_ok=True)

        install_cmd = [
            "cpanm",
            "--quiet",
            "--notest",
            "--local-lib",
            str(prefix),
            package,
        ]
        if version_spec:
            install_cmd.append(str(version_spec))

        subprocess.run(  # nosec B603 - controlled cpanm install
            install_cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        if not binary.exists():
            raise RuntimeError(f"Failed to install Perl tool '{tool.name}'")

        meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary

    @staticmethod
    def _package_spec(tool: Tool) -> tuple[str, str | None]:
        if tool.package:
            package, version = _split_package_spec(tool.package)
            return package, version
        return tool.name, tool.min_version

    @staticmethod
    def _perl_env(bin_dir: Path) -> dict[str, str]:
        lib_dir = bin_dir.parent / "lib" / "perl5"
        env = {
            "PATH": os.pathsep.join([str(bin_dir)] + os.environ.get("PATH", "").split(os.pathsep)),
            "PERL5LIB": str(lib_dir),
            "PERL_LOCAL_LIB_ROOT": str(bin_dir.parent),
        }
        return env
class RustRuntime(RuntimeHandler):
    """Provision Rust tooling using ``cargo install`` with caching."""

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
        return PreparedCommand(cmd=list(base_cmd), env={}, version=version, source="system")

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        if not shutil.which("cargo"):
            raise RuntimeError("Cargo toolchain is required to install rust-based linters")

        binary_name = Path(base_cmd[0]).name
        binary_path = self._ensure_local_tool(tool, binary_name)
        cmd = list(base_cmd)
        cmd[0] = str(binary_path)

        env: dict[str, str] = {}
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        return PreparedCommand(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        crate, version_spec = self._crate_spec(tool)
        if crate.startswith("rustup:"):
            component = crate.split(":", 1)[1]
            requirement = f"rustup:{component}"
            slug = _slugify(requirement)
            meta_file = RUST_META_DIR / f"{slug}.json"
            meta_file.parent.mkdir(parents=True, exist_ok=True)
            if not meta_file.exists():
                self._install_rustup_component(component)
                meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
            cargo_path = shutil.which("cargo")
            if not cargo_path:
                raise RuntimeError("cargo executable not found for rust tool")
            return Path(cargo_path)

        requirement = f"{crate}@{version_spec}" if version_spec else crate
        slug = _slugify(requirement)
        prefix = RUST_CACHE_DIR / slug
        binary = prefix / "bin" / binary_name
        meta_file = RUST_META_DIR / f"{slug}.json"

        if binary.exists() and meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("requirement") == requirement:
                    return binary
            except json.JSONDecodeError:
                pass

        meta_file.parent.mkdir(parents=True, exist_ok=True)
        (prefix / "bin").mkdir(parents=True, exist_ok=True)
        (prefix / "cargo").mkdir(parents=True, exist_ok=True)
        (prefix / "target").mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.setdefault("CARGO_HOME", str(prefix / "cargo"))
        env.setdefault("CARGO_TARGET_DIR", str(prefix / "target"))

        install_cmd = [
            "cargo",
            "install",
            crate,
            "--root",
            str(prefix),
            "--locked",
        ]
        if version_spec:
            install_cmd.extend(["--version", str(version_spec)])

        subprocess.run(  # nosec B603 - controlled cargo install
            install_cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )

        if not binary.exists():
            raise RuntimeError(f"Failed to install rust tool '{tool.name}'")

        meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary

    @staticmethod
    def _crate_spec(tool: Tool) -> tuple[str, str | None]:
        if tool.package:
            crate, version = _split_package_spec(tool.package)
            if version is None:
                version = tool.min_version
            return crate, version
        return tool.name, tool.min_version

    def _install_rustup_component(self, component: str) -> None:
        if not shutil.which("rustup"):
            raise RuntimeError("rustup is required to install rustup components")
        subprocess.run(  # nosec B603 - controlled rustup call
            ["rustup", "component", "add", component],
            capture_output=True,
            text=True,
            check=True,
        )


class BinaryRuntime(RuntimeHandler):
    """Fallback runtime for tools executed directly as system binaries."""

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        return PreparedCommand(cmd=list(base_cmd), env={}, version=version, source="system")


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
        project_mode = (cache_dir / PROJECT_MARKER.name).is_file() or PROJECT_MARKER.is_file()
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
        UV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        NODE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        NPM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        GO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        GO_BIN_DIR.mkdir(parents=True, exist_ok=True)
        LUA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        LUA_BIN_DIR.mkdir(parents=True, exist_ok=True)
        LUA_META_DIR.mkdir(parents=True, exist_ok=True)
        RUST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        RUST_BIN_DIR.mkdir(parents=True, exist_ok=True)
        RUST_META_DIR.mkdir(parents=True, exist_ok=True)
        PERL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        PERL_BIN_DIR.mkdir(parents=True, exist_ok=True)
        PERL_META_DIR.mkdir(parents=True, exist_ok=True)


def _split_package_spec(spec: str) -> tuple[str, str | None]:
    if spec.startswith("git+") or spec.startswith("file:") or spec.startswith("http"):
        return spec, None
    if spec.startswith("@"):
        if spec.count("@") >= 2:
            name, version = spec.rsplit("@", 1)
            return name, version
        return spec, None
    if "@" in spec:
        name, version = spec.rsplit("@", 1)
        return name, version
    return spec, None


def _slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value)


def _extract_version(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)+)", text)
    return match.group(1) if match else None


def desired_version(tool: Tool) -> str | None:
    """Determine the target version expected for *tool*."""

    if tool.package:
        _, specified = _split_package_spec(tool.package)
        extracted = _extract_version(specified)
        if extracted:
            return extracted
    if tool.min_version:
        return tool.min_version
    return None
