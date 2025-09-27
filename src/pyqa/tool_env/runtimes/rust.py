# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Rust-based tooling."""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Sequence
from pathlib import Path

from ...process_utils import run_command
from ...tools.base import Tool
from .. import constants as tool_constants
from ..models import PreparedCommand
from ..utils import slugify, split_package_spec
from .base import RuntimeHandler


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
        return PreparedCommand.from_parts(cmd=base_cmd, env=None, version=version, source="system")

    def _try_project(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        del cache_dir, target_version
        binary_name = Path(base_cmd[0]).name
        candidate = root / "bin" / binary_name
        if not candidate.exists():
            return None
        cmd = list(base_cmd)
        cmd[0] = str(candidate)
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        return PreparedCommand.from_parts(
            cmd=cmd,
            env=None,
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
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        crate, version_spec = self._crate_spec(tool)
        if crate.startswith("rustup:"):
            component = crate.split(":", 1)[1]
            requirement = f"rustup:{component}"
            slug = slugify(requirement)
            meta_file = tool_constants.RUST_META_DIR / f"{slug}.json"
            meta_file.parent.mkdir(parents=True, exist_ok=True)
            if not meta_file.exists():
                self._install_rustup_component(component)
                meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
            cargo_path = shutil.which("cargo")
            if not cargo_path:
                raise RuntimeError("cargo executable not found for rust tool")
            return Path(cargo_path)

        requirement = f"{crate}@{version_spec}" if version_spec else crate
        slug = slugify(requirement)
        prefix = tool_constants.RUST_CACHE_DIR / slug
        binary = prefix / "bin" / binary_name
        meta_file = tool_constants.RUST_META_DIR / f"{slug}.json"

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

        run_command(install_cmd, capture_output=True, env=env)

        if not binary.exists():
            raise RuntimeError(f"Failed to install rust tool '{tool.name}'")

        meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary

    @staticmethod
    def _crate_spec(tool: Tool) -> tuple[str, str | None]:
        if tool.package:
            crate, version = split_package_spec(tool.package)
            if version is None:
                version = tool.min_version
            return crate, version
        return tool.name, tool.min_version

    def _install_rustup_component(self, component: str) -> None:
        if not shutil.which("rustup"):
            raise RuntimeError("rustup is required to install rustup components")
        run_command(["rustup", "component", "add", component], capture_output=True)


__all__ = ["RustRuntime"]
