# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Cache layout helpers shared across tool environment runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

TOOLS_SUBDIR: Final[str] = "tools"
UV_SUBDIR: Final[str] = "uv"
NODE_SUBDIR: Final[str] = "node"
NPM_SUBDIR: Final[str] = "npm"
GO_SUBDIR: Final[str] = "go"
GO_BIN_SUBDIR: Final[str] = "bin"
GO_META_SUBDIR: Final[str] = "meta"
GO_WORK_SUBDIR: Final[str] = "work"
LUA_SUBDIR: Final[str] = "lua"
LUA_BIN_SUBDIR: Final[str] = "bin"
LUA_META_SUBDIR: Final[str] = "meta"
LUA_WORK_SUBDIR: Final[str] = "lua"
RUST_SUBDIR: Final[str] = "rust"
RUST_BIN_SUBDIR: Final[str] = "bin"
RUST_META_SUBDIR: Final[str] = "meta"
RUST_WORK_SUBDIR: Final[str] = "work"
PERL_SUBDIR: Final[str] = "perl"
PERL_BIN_SUBDIR: Final[str] = "bin"
PERL_META_SUBDIR: Final[str] = "meta"
PROJECT_MARKER_FILENAME: Final[str] = "project-installed.json"


@dataclass(frozen=True, slots=True)
class ToolCacheLayout:
    """Filesystem layout describing per-run tool cache directories."""

    cache_dir: Path

    @property
    def tools_root(self) -> Path:
        return self.cache_dir / TOOLS_SUBDIR

    @property
    def uv_dir(self) -> Path:
        return self.tools_root / UV_SUBDIR

    @property
    def node_cache_dir(self) -> Path:
        return self.tools_root / NODE_SUBDIR

    @property
    def npm_cache_dir(self) -> Path:
        return self.tools_root / NPM_SUBDIR

    @property
    def project_marker(self) -> Path:
        return self.tools_root / PROJECT_MARKER_FILENAME

    @property
    def legacy_project_marker(self) -> Path:
        return self.cache_dir / PROJECT_MARKER_FILENAME

    @property
    def go_cache_dir(self) -> Path:
        return self.tools_root / GO_SUBDIR

    @property
    def go_bin_dir(self) -> Path:
        return self.go_cache_dir / GO_BIN_SUBDIR

    @property
    def go_meta_dir(self) -> Path:
        return self.go_cache_dir / GO_META_SUBDIR

    @property
    def go_work_dir(self) -> Path:
        return self.go_cache_dir / GO_WORK_SUBDIR

    @property
    def lua_cache_dir(self) -> Path:
        return self.tools_root / LUA_SUBDIR

    @property
    def lua_bin_dir(self) -> Path:
        return self.lua_cache_dir / LUA_BIN_SUBDIR

    @property
    def lua_meta_dir(self) -> Path:
        return self.lua_cache_dir / LUA_META_SUBDIR

    @property
    def lua_work_dir(self) -> Path:
        return self.lua_cache_dir / LUA_WORK_SUBDIR

    @property
    def rust_cache_dir(self) -> Path:
        return self.tools_root / RUST_SUBDIR

    @property
    def rust_bin_dir(self) -> Path:
        return self.rust_cache_dir / RUST_BIN_SUBDIR

    @property
    def rust_meta_dir(self) -> Path:
        return self.rust_cache_dir / RUST_META_SUBDIR

    @property
    def rust_work_dir(self) -> Path:
        return self.rust_cache_dir / RUST_WORK_SUBDIR

    @property
    def perl_cache_dir(self) -> Path:
        return self.tools_root / PERL_SUBDIR

    @property
    def perl_bin_dir(self) -> Path:
        return self.perl_cache_dir / PERL_BIN_SUBDIR

    @property
    def perl_meta_dir(self) -> Path:
        return self.perl_cache_dir / PERL_META_SUBDIR

    @property
    def directories(self) -> tuple[Path, ...]:
        """Return directories that should exist for the cache layout."""

        paths: list[Path] = [
            self.tools_root,
            self.uv_dir,
            self.node_cache_dir,
            self.npm_cache_dir,
            self.go_cache_dir,
            self.go_bin_dir,
            self.go_meta_dir,
            self.go_work_dir,
            self.lua_cache_dir,
            self.lua_bin_dir,
            self.lua_meta_dir,
            self.lua_work_dir,
            self.rust_cache_dir,
            self.rust_bin_dir,
            self.rust_meta_dir,
            self.rust_work_dir,
            self.perl_cache_dir,
            self.perl_bin_dir,
            self.perl_meta_dir,
        ]
        # Deduplicate while preserving order
        seen: set[Path] = set()
        return tuple(path for path in paths if not (path in seen or seen.add(path)))

    def ensure_directories(self) -> None:
        """Create required cache directories when absent."""

        for path in self.directories:
            path.mkdir(parents=True, exist_ok=True)


def cache_layout(cache_dir: Path) -> ToolCacheLayout:
    """Return the cache layout for ``cache_dir``.

    Args:
        cache_dir: Base cache directory selected for the run.

    Returns:
        ToolCacheLayout: Layout object describing subdirectories.
    """

    return ToolCacheLayout(cache_dir=cache_dir)


__all__ = [
    "PROJECT_MARKER_FILENAME",
    "ToolCacheLayout",
    "cache_layout",
]
