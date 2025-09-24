# SPDX-License-Identifier: MIT
"""Filesystem locations used by tool environment management."""

from __future__ import annotations

from pathlib import Path
from typing import Final

PYQA_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CACHE_ROOT: Final[Path] = PYQA_ROOT / ".lint-cache" / "tools"
UV_CACHE_DIR: Final[Path] = CACHE_ROOT / "uv"
NODE_CACHE_DIR: Final[Path] = CACHE_ROOT / "node"
NPM_CACHE_DIR: Final[Path] = CACHE_ROOT / "npm"
PROJECT_MARKER: Final[Path] = CACHE_ROOT / "project-installed.json"
GO_CACHE_DIR: Final[Path] = CACHE_ROOT / "go"
GO_BIN_DIR: Final[Path] = GO_CACHE_DIR / "bin"
GO_META_DIR: Final[Path] = GO_CACHE_DIR / "meta"
GO_WORK_DIR: Final[Path] = GO_CACHE_DIR / "work"
LUA_CACHE_DIR: Final[Path] = CACHE_ROOT / "lua"
LUA_BIN_DIR: Final[Path] = LUA_CACHE_DIR / "bin"
LUA_META_DIR: Final[Path] = LUA_CACHE_DIR / "meta"
LUA_WORK_DIR: Final[Path] = LUA_CACHE_DIR / "lua"
RUST_CACHE_DIR: Final[Path] = CACHE_ROOT / "rust"
RUST_BIN_DIR: Final[Path] = RUST_CACHE_DIR / "bin"
RUST_META_DIR: Final[Path] = RUST_CACHE_DIR / "meta"
RUST_WORK_DIR: Final[Path] = RUST_CACHE_DIR / "work"
PERL_CACHE_DIR: Final[Path] = CACHE_ROOT / "perl"
PERL_BIN_DIR: Final[Path] = PERL_CACHE_DIR / "bin"
PERL_META_DIR: Final[Path] = PERL_CACHE_DIR / "meta"

__all__ = [
    "PYQA_ROOT",
    "CACHE_ROOT",
    "UV_CACHE_DIR",
    "NODE_CACHE_DIR",
    "NPM_CACHE_DIR",
    "PROJECT_MARKER",
    "GO_CACHE_DIR",
    "GO_BIN_DIR",
    "GO_META_DIR",
    "GO_WORK_DIR",
    "LUA_CACHE_DIR",
    "LUA_BIN_DIR",
    "LUA_META_DIR",
    "LUA_WORK_DIR",
    "RUST_CACHE_DIR",
    "RUST_BIN_DIR",
    "RUST_META_DIR",
    "RUST_WORK_DIR",
    "PERL_CACHE_DIR",
    "PERL_BIN_DIR",
    "PERL_META_DIR",
]
