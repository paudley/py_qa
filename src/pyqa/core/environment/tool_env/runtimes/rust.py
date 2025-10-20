# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Rust-based tooling."""

from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from pyqa.core.runtime.process import CommandOptions, run_command
from pyqa.tools.base import Tool

from ..constants import ToolCacheLayout
from ..models import PreparedCommand
from ..utils import _slugify, _split_package_spec
from .base import BuildEnvFn, RuntimeContext, RuntimeHandler


@dataclass(frozen=True, slots=True)
class RustInstallPlan:
    """Describe the filesystem layout for a cached Rust tool installation."""

    layout: ToolCacheLayout
    slug: str
    binary_name: str
    prefix: Path = field(init=False)
    binary: Path = field(init=False)
    meta_file: Path = field(init=False)

    def __post_init__(self) -> None:
        """Prepare the derived paths for the installation plan.

        Returns:
            None: Initialisation mutates frozen attributes via ``object.__setattr__``.
        """

        rust_paths = self.layout.rust
        prefix = rust_paths.cache_dir / self.slug
        object.__setattr__(self, "prefix", prefix)
        object.__setattr__(self, "binary", prefix / "bin" / self.binary_name)
        object.__setattr__(self, "meta_file", rust_paths.meta_dir / f"{self.slug}.json")


@dataclass(frozen=True, slots=True)
class CargoRequirement:
    """Describe a cargo installation requirement extracted from the catalog."""

    crate: str
    version_spec: str | None
    requirement: str
    tool_name: str


class RustRuntime(RuntimeHandler):
    """Provide the runtime for Rust tooling using ``cargo install`` with caching."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return the project command when the Rust binary exists.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand | None: Prepared project command, or ``None`` when absent.
        """

        project_cmd = self._project_binary(context)
        if project_cmd is None:
            return None
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command)
        project_cmd.version = version
        return project_cmd

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Return the command after installing Rust tooling via cargo.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand: Prepared command referencing the cached Rust binary.

        Raises:
            RuntimeError: If the cargo toolchain is unavailable.
        """

        if not shutil.which("cargo"):
            raise RuntimeError("Cargo toolchain is required to install rust-based linters")

        return self._prepare_cached_command(
            context,
            self._ensure_local_tool,
            cast(BuildEnvFn, self._rust_env),
        )

    def _ensure_local_tool(self, context: RuntimeContext, binary_name: str) -> Path:
        """Ensure the cargo-installed binary for the requested tool exists.

        Args:
            context: Runtime context describing command preparation parameters.
            binary_name: Executable name expected in the Rust cache.

        Returns:
            Path: Filesystem path to the installed Rust binary.
        """
        tool = context.tool
        layout = context.cache_layout
        crate, version_spec = self._crate_spec(tool)
        if crate.startswith("rustup:"):
            component = crate.split(":", 1)[1]
            return self._ensure_rustup_tool(layout, component)

        requirement = f"{crate}@{version_spec}" if version_spec else crate
        plan = RustInstallPlan(layout=layout, slug=_slugify(requirement), binary_name=binary_name)
        if self._is_existing_binary(plan, requirement):
            return plan.binary

        spec = CargoRequirement(
            crate=crate,
            version_spec=version_spec,
            requirement=requirement,
            tool_name=tool.name,
        )
        self._install_cargo_tool(plan, spec)
        return plan.binary

    @staticmethod
    def _crate_spec(tool: Tool) -> tuple[str, str | None]:
        """Return the crate name and version derived from tool metadata.

        Args:
            tool: Tool metadata describing the Rust crate requirement.

        Returns:
            tuple[str, str | None]: Crate name and optional version specification.
        """
        if tool.package:
            crate, version = _split_package_spec(tool.package)
            if version is None:
                version = tool.min_version
            return crate, version
        return tool.name, tool.min_version

    def _install_rustup_component(self, component: str) -> None:
        """Install the rustup component required by a tool.

        Args:
            component: Rustup component identifier to install.

        Raises:
            RuntimeError: If rustup is unavailable to perform the installation.
        """
        if not shutil.which("rustup"):
            raise RuntimeError("rustup is required to install rustup components")
        run_command(
            ["rustup", "component", "add", component],
            options=CommandOptions(capture_output=True),
        )

    def _ensure_rustup_tool(self, layout: ToolCacheLayout, component: str) -> Path:
        """Return the cargo executable after ensuring a rustup component exists.

        Args:
            layout: Cache layout used to persist metadata.
            component: Rustup component identifier to install when missing.

        Returns:
            Path: Resolved cargo executable path after ensuring dependencies.
        """

        requirement = f"rustup:{component}"
        slug = _slugify(requirement)
        meta_file = layout.rust.meta_dir / f"{slug}.json"
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        if not meta_file.exists():
            self._install_rustup_component(component)
            meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        cargo_path = shutil.which("cargo")
        if not cargo_path:
            raise RuntimeError("cargo executable not found for rust tool")
        return Path(cargo_path)

    def _is_existing_binary(self, plan: RustInstallPlan, requirement: str) -> bool:
        """Return whether ``plan`` already satisfies the installation requirement.

        Args:
            plan: Installation plan describing cached filesystem paths.
            requirement: Requirement string previously recorded for the tool.

        Returns:
            bool: ``True`` when the cached binary exists and metadata matches.
        """

        if not (plan.binary.exists() and plan.meta_file.exists()):
            return False
        metadata = self._load_json(plan.meta_file)
        return bool(metadata and metadata.get("requirement") == requirement)

    def _install_cargo_tool(self, plan: RustInstallPlan, spec: CargoRequirement) -> None:
        """Install the crate into the cached tool environment described by ``plan``.

        Args:
            plan: Installation plan describing the cache layout.
            spec: Cargo requirement metadata for the requested tool.

        Returns:
            None: This method raises if installation fails and otherwise
            completes silently.
        """

        plan.meta_file.parent.mkdir(parents=True, exist_ok=True)
        plan.binary.parent.mkdir(parents=True, exist_ok=True)
        cargo_home = plan.prefix / "cargo"
        target_dir = plan.prefix / "target"
        cargo_home.mkdir(parents=True, exist_ok=True)
        target_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.setdefault("CARGO_HOME", str(cargo_home))
        env.setdefault("CARGO_TARGET_DIR", str(target_dir))

        install_cmd = [
            "cargo",
            "install",
            spec.crate,
            "--root",
            str(plan.prefix),
            "--locked",
        ]
        if spec.version_spec:
            install_cmd.extend(["--version", str(spec.version_spec)])

        run_command(install_cmd, options=CommandOptions(capture_output=True, env=env))

        if not plan.binary.exists():
            raise RuntimeError(f"Failed to install rust tool '{spec.tool_name}'")

        plan.meta_file.write_text(
            json.dumps({"requirement": spec.requirement}),
            encoding="utf-8",
        )
        plan.binary.chmod(plan.binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    @staticmethod
    def _rust_env(_: RuntimeContext) -> dict[str, str]:
        """Return environment variables for Rust tools (none required).

        Args:
            _: Runtime context parameter (unused for Rust tooling).

        Returns:
            dict[str, str]: Empty mapping because Rust commands rely on
            inherited environment variables.
        """

        return {}


__all__ = ["RustRuntime"]
