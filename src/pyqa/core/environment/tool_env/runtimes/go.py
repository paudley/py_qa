# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Go-based tooling."""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

from pyqa.core.runtime.process import CommandOptions, run_command
from pyqa.tools.base import Tool

from ..models import PreparedCommand
from ..utils import _slugify, _split_package_spec
from .base import RuntimeContext, RuntimeHandler


class GoRuntime(RuntimeHandler):
    """Provision Go tooling by installing modules into a dedicated cache."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Reuse project ``bin`` directory when a tool-specific binary exists."""

        return self._project_binary(context)

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Install Go tooling into the shared cache and return the command."""

        if not shutil.which("go"):
            raise RuntimeError("Go toolchain is required to install go-based linters")
        return self._prepare_cached_command(
            context,
            self._ensure_local_tool,
            self._go_env,
        )

    def _ensure_local_tool(self, context: RuntimeContext, binary_name: str) -> Path:
        """Install or reuse a cached Go binary for ``tool``."""
        tool = context.tool
        module, version_spec = self._module_spec(tool)
        if not version_spec:
            version_spec = "latest"
        requirement = f"{module}@{version_spec}"
        slug = _slugify(requirement)
        layout = context.cache_layout
        meta_file = layout.go.meta_dir / f"{slug}.json"
        binary = layout.go.bin_dir / binary_name

        if binary.exists() and meta_file.exists():
            meta = self._load_json(meta_file)
            if meta and meta.get("requirement") == requirement:
                return binary

        layout.go.meta_dir.mkdir(parents=True, exist_ok=True)
        layout.go.bin_dir.mkdir(parents=True, exist_ok=True)
        work_root = layout.go.work_dir
        if work_root is None:  # pragma: no cover - defensive safeguard
            raise RuntimeError("Go runtime cache layout is missing a work directory")
        (work_root / "gopath").mkdir(parents=True, exist_ok=True)
        (work_root / "gocache").mkdir(parents=True, exist_ok=True)
        (work_root / "modcache").mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.setdefault("GOBIN", str(layout.go.bin_dir))
        env.setdefault("GOCACHE", str(work_root / "gocache"))
        env.setdefault("GOMODCACHE", str(work_root / "modcache"))
        env.setdefault("GOPATH", str(work_root / "gopath"))

        run_command(
            ["go", "install", requirement],
            options=CommandOptions(capture_output=True, env=env),
        )

        if not binary.exists():
            msg = f"Failed to install go tool '{tool.name}'"
            raise RuntimeError(msg)

        meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary

    @staticmethod
    def _module_spec(tool: Tool) -> tuple[str, str | None]:
        """Return module and version specifiers derived from ``tool`` metadata."""
        if tool.package:
            module, version = _split_package_spec(tool.package)
            return module, version
        return tool.name, tool.min_version

    @staticmethod
    def _go_env(context: RuntimeContext) -> dict[str, str]:
        """Return environment variables required for executing Go tools."""
        return RuntimeHandler._prepend_path_environment(
            bin_dir=context.cache_layout.go.bin_dir,
            root=context.root,
        )


__all__ = ["GoRuntime"]
