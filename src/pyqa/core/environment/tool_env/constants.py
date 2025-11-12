# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Cache layout helpers shared across tool environment runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

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

RuntimeName = Literal["go", "lua", "rust", "perl"]


@dataclass(frozen=True, slots=True)
class RuntimeCachePaths:
    """Maintain cached runtime filesystem location metadata.

    Attributes:
        cache_dir: Root directory containing runtime-managed cache data.
        bin_dir: Directory holding runnable binaries for the runtime.
        meta_dir: Directory containing metadata artefacts required at runtime.
        work_dir: Optional directory used for workspace state during execution.
    """

    cache_dir: Path
    bin_dir: Path
    meta_dir: Path
    work_dir: Path | None = None

    def directories(self) -> tuple[Path, ...]:
        """Collect directories that must exist for the runtime cache.

        Returns:
            tuple[Path, ...]: Ordered cache directories for the runtime.
        """

        entries: list[Path] = [self.cache_dir, self.bin_dir, self.meta_dir]
        if self.work_dir is not None:
            entries.append(self.work_dir)
        return tuple(entries)


@dataclass(frozen=True, slots=True)
class ToolCacheLayout:
    """Model per-run tool cache directories.

    Attributes:
        cache_dir: Base directory that contains persistent tool cache data.
    """

    cache_dir: Path
    _runtime_paths: dict[RuntimeName, RuntimeCachePaths] = field(init=False)

    def __post_init__(self) -> None:
        """Prepare derived cache directory paths for the layout."""

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
        """Determine the root directory containing cached tool environments.

        Returns:
            Path: Root directory under which tool cache data is stored.
        """

        return self.cache_dir / TOOLS_SUBDIR

    @property
    def uv_dir(self) -> Path:
        """Resolve the directory reserved for the ``uv`` installer.

        Returns:
            Path: Filesystem path for the uv installer cache.
        """

        return self.tools_root / UV_SUBDIR

    @property
    def node_cache_dir(self) -> Path:
        """Resolve the cache directory used for npm/node tooling.

        Returns:
            Path: Filesystem path for Node.js runtime cache data.
        """

        return self.tools_root / NODE_SUBDIR

    @property
    def npm_cache_dir(self) -> Path:
        """Resolve the cache directory used for npm artefacts.

        Returns:
            Path: Filesystem path for npm package cache data.
        """

        return self.tools_root / NPM_SUBDIR

    @property
    def project_marker(self) -> Path:
        """Locate the modern project marker file path.

        Returns:
            Path: File path indicating successful project tool installation.
        """

        return self.tools_root / PROJECT_MARKER_FILENAME

    @property
    def legacy_project_marker(self) -> Path:
        """Locate the legacy project marker file path.

        Returns:
            Path: File path for the legacy tool installation marker.
        """

        return self.cache_dir / PROJECT_MARKER_FILENAME

    @property
    def go(self) -> RuntimeCachePaths:
        """Expose cache paths for Go tooling.

        Returns:
            RuntimeCachePaths: Cache directories associated with Go.
        """

        return self._runtime_paths["go"]

    @property
    def lua(self) -> RuntimeCachePaths:
        """Expose cache paths for Lua tooling.

        Returns:
            RuntimeCachePaths: Cache directories associated with Lua.
        """

        return self._runtime_paths["lua"]

    @property
    def rust(self) -> RuntimeCachePaths:
        """Expose cache paths for Rust tooling.

        Returns:
            RuntimeCachePaths: Cache directories associated with Rust.
        """

        return self._runtime_paths["rust"]

    @property
    def perl(self) -> RuntimeCachePaths:
        """Expose cache paths for Perl tooling.

        Returns:
            RuntimeCachePaths: Cache directories associated with Perl.
        """

        return self._runtime_paths["perl"]

    @property
    def directories(self) -> tuple[Path, ...]:
        """Collect cache directories that must exist for the layout.

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
        """Create required cache directories when absent."""

        for path in self.directories:
            path.mkdir(parents=True, exist_ok=True)


def cache_layout(cache_dir: Path) -> ToolCacheLayout:
    """Create the cache layout for ``cache_dir``.

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
