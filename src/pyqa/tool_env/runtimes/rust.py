# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Rust-based tooling."""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

from ...process_utils import run_command
from ...tools.base import Tool
from ..models import PreparedCommand
from ..utils import _slugify, _split_package_spec
from .base import RuntimeContext, RuntimeHandler


class RustRuntime(RuntimeHandler):
    """Provision Rust tooling using ``cargo install`` with caching."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Reuse project ``bin`` directory for Rust tooling when available."""

        project_cmd = self._project_binary(context)
        if project_cmd is None:
            return None
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command)
        project_cmd.version = version
        return project_cmd

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Install Rust tooling via cargo and return the cached command."""

        if not shutil.which("cargo"):
            raise RuntimeError("Cargo toolchain is required to install rust-based linters")

        binary_name = Path(context.executable).name
        binary_path = self._ensure_local_tool(context, binary_name)
        cmd = context.command_list()
        cmd[0] = str(binary_path)

        env: dict[str, str] = {}
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command)
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, context: RuntimeContext, binary_name: str) -> Path:
        """Install or reuse a cargo-installed binary for ``tool``."""
        tool = context.tool
        layout = context.cache_layout
        crate, version_spec = self._crate_spec(tool)
        if crate.startswith("rustup:"):
            component = crate.split(":", 1)[1]
            requirement = f"rustup:{component}"
            slug = _slugify(requirement)
            meta_file = layout.rust_meta_dir / f"{slug}.json"
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
        prefix = layout.rust_cache_dir / slug
        binary = prefix / "bin" / binary_name
        meta_file = layout.rust_meta_dir / f"{slug}.json"

        if binary.exists() and meta_file.exists():
            meta = self._load_json(meta_file)
            if meta and meta.get("requirement") == requirement:
                return binary

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
        """Return crate name and version derived from ``tool`` metadata."""
        if tool.package:
            crate, version = _split_package_spec(tool.package)
            if version is None:
                version = tool.min_version
            return crate, version
        return tool.name, tool.min_version

    def _install_rustup_component(self, component: str) -> None:
        """Install a rustup component required by a tool."""
        if not shutil.which("rustup"):
            raise RuntimeError("rustup is required to install rustup components")
        run_command(["rustup", "component", "add", component], capture_output=True)


__all__ = ["RustRuntime"]
