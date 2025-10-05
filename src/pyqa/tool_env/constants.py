# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Cache layout helpers shared across tool environment runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
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
class RuntimeCachePaths:
    """Filesystem locations associated with a cached runtime."""

    cache_dir: Path
    bin_dir: Path
    meta_dir: Path
    work_dir: Path | None = None

    def directories(self) -> tuple[Path, ...]:
        """Return directories that should exist for the runtime cache.

        Returns:
            tuple[Path, ...]: Ordered cache directories for the runtime.
        """

        entries: list[Path] = [self.cache_dir, self.bin_dir, self.meta_dir]
        if self.work_dir is not None:
            entries.append(self.work_dir)
        return tuple(entries)


@dataclass(frozen=True, slots=True)
class ToolCacheLayout:
    """Filesystem layout describing per-run tool cache directories."""

    cache_dir: Path
    _runtime_paths: dict[str, RuntimeCachePaths] = field(init=False)

    def __post_init__(self) -> None:
        """Populate derived cache directory paths for the layout.

        Returns:
            None: Initialisation mutates derived attributes for runtime lookup.
        """

        runtimes = {
            "go": RuntimeCachePaths(
                cache_dir=self.tools_root / GO_SUBDIR,
                bin_dir=self.tools_root / GO_SUBDIR / GO_BIN_SUBDIR,
                meta_dir=self.tools_root / GO_SUBDIR / GO_META_SUBDIR,
                work_dir=self.tools_root / GO_SUBDIR / GO_WORK_SUBDIR,
            ),
            "lua": RuntimeCachePaths(
                cache_dir=self.tools_root / LUA_SUBDIR,
                bin_dir=self.tools_root / LUA_SUBDIR / LUA_BIN_SUBDIR,
                meta_dir=self.tools_root / LUA_SUBDIR / LUA_META_SUBDIR,
                work_dir=self.tools_root / LUA_SUBDIR / LUA_WORK_SUBDIR,
            ),
            "rust": RuntimeCachePaths(
                cache_dir=self.tools_root / RUST_SUBDIR,
                bin_dir=self.tools_root / RUST_SUBDIR / RUST_BIN_SUBDIR,
                meta_dir=self.tools_root / RUST_SUBDIR / RUST_META_SUBDIR,
                work_dir=self.tools_root / RUST_SUBDIR / RUST_WORK_SUBDIR,
            ),
            "perl": RuntimeCachePaths(
                cache_dir=self.tools_root / PERL_SUBDIR,
                bin_dir=self.tools_root / PERL_SUBDIR / PERL_BIN_SUBDIR,
                meta_dir=self.tools_root / PERL_SUBDIR / PERL_META_SUBDIR,
            ),
        }
        object.__setattr__(self, "_runtime_paths", runtimes)

    @property
    def tools_root(self) -> Path:
        """Return the root directory containing cached tool environments."""

        return self.cache_dir / TOOLS_SUBDIR

    @property
    def uv_dir(self) -> Path:
        """Return the directory reserved for the ``uv`` installer."""

        return self.tools_root / UV_SUBDIR

    @property
    def node_cache_dir(self) -> Path:
        """Return the cache directory used for npm/node tooling."""

        return self.tools_root / NODE_SUBDIR

    @property
    def npm_cache_dir(self) -> Path:
        """Return the cache directory used for npm artefacts."""

        return self.tools_root / NPM_SUBDIR

    @property
    def project_marker(self) -> Path:
        """Return the modern project marker file path."""

        return self.tools_root / PROJECT_MARKER_FILENAME

    @property
    def legacy_project_marker(self) -> Path:
        """Return the legacy project marker file path."""

        return self.cache_dir / PROJECT_MARKER_FILENAME

    @property
    def go(self) -> RuntimeCachePaths:
        """Return cache paths for Go tooling."""

        return self._runtime_paths["go"]

    @property
    def lua(self) -> RuntimeCachePaths:
        """Return cache paths for Lua tooling."""

        return self._runtime_paths["lua"]

    @property
    def rust(self) -> RuntimeCachePaths:
        """Return cache paths for Rust tooling."""

        return self._runtime_paths["rust"]

    @property
    def perl(self) -> RuntimeCachePaths:
        """Return cache paths for Perl tooling."""

        return self._runtime_paths["perl"]

    @property
    def directories(self) -> tuple[Path, ...]:
        """Return cache directories that must exist for the layout.

        Returns:
            tuple[Path, ...]: Ordered, unique directories that runtimes rely on
            during tool installation and execution.
        """

        paths: list[Path] = [
            self.tools_root,
            self.uv_dir,
            self.node_cache_dir,
            self.npm_cache_dir,
        ]
        for runtime_paths in self._runtime_paths.values():
            paths.extend(runtime_paths.directories())
        # Deduplicate while preserving order
        seen: set[Path] = set()
        unique: list[Path] = []
        for path in paths:
            if path not in seen:
                unique.append(path)
                seen.add(path)
        return tuple(unique)

    def ensure_directories(self) -> None:
        """Create required cache directories when absent.

        Returns:
            None: This method does not return a value.
        """

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
    "RuntimeCachePaths",
    "ToolCacheLayout",
    "cache_layout",
]
