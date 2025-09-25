# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Compatibility wrapper exposing built-in tool registration and exports."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .base import Tool
from .builtin_catalog_misc import misc_tools
from .builtin_catalog_python import python_tools
from .builtin_commands import (
    _ActionlintCommand,
    _BanditCommand,
    _BlackCommand,
    _CheckmakeCommand,
    _CpplintCommand,
    _DockerfilelintCommand,
    _DotenvLinterCommand,
    _EslintCommand,
    _GolangciLintCommand,
    _GtsCommand,
    _HadolintCommand,
    _IsortCommand,
    _KubeLinterCommand,
    _LuacheckCommand,
    _LualintCommand,
    _MypyCommand,
    _PerlCriticCommand,
    _PerltidyCommand,
    _PhplintCommand,
    _PrettierCommand,
    _PyrightCommand,
    _RemarkCommand,
    _RuffCommand,
    _RuffFormatCommand,
    _SeleneCommand,
    _ShfmtCommand,
    _SpeccyCommand,
    _SqlfluffCommand,
    _StylelintCommand,
    _TombiCommand,
    _TscCommand,
    _YamllintCommand,
)
from .builtin_helpers import (
    ACTIONLINT_VERSION_DEFAULT,
    HADOLINT_VERSION_DEFAULT,
    _ensure_actionlint,
    _ensure_hadolint,
    _ensure_lualint,
)
from .builtin_registry import register_builtin_tools


def _builtin_tools() -> Iterable[Tool]:
    """Yield all built-in tool definitions (legacy helper)."""
    yield from python_tools()
    yield from misc_tools()


__all__ = [
    "ACTIONLINT_VERSION_DEFAULT",
    "HADOLINT_VERSION_DEFAULT",
    "_ActionlintCommand",
    "_BanditCommand",
    "_BlackCommand",
    "_CheckmakeCommand",
    "_CpplintCommand",
    "_DockerfilelintCommand",
    "_DotenvLinterCommand",
    "_EslintCommand",
    "_GolangciLintCommand",
    "_GtsCommand",
    "_HadolintCommand",
    "_IsortCommand",
    "_KubeLinterCommand",
    "_LuacheckCommand",
    "_LualintCommand",
    "_MypyCommand",
    "_PerlCriticCommand",
    "_PerltidyCommand",
    "_PhplintCommand",
    "_PrettierCommand",
    "_PyrightCommand",
    "_RemarkCommand",
    "_RuffCommand",
    "_RuffFormatCommand",
    "_SeleneCommand",
    "_ShfmtCommand",
    "_SpeccyCommand",
    "_SqlfluffCommand",
    "_StylelintCommand",
    "_TombiCommand",
    "_TscCommand",
    "_YamllintCommand",
    "_builtin_tools",
    "_ensure_actionlint",
    "_ensure_hadolint",
    "_ensure_lualint",
    "ensure_actionlint",
    "ensure_hadolint",
    "ensure_lualint",
    "register_builtin_tools",
]


def ensure_actionlint(version: str, cache_root: Path) -> Path:
    """Public wrapper exposing the actionlint installer."""
    return _ensure_actionlint(version, cache_root)


def ensure_hadolint(version: str, cache_root: Path) -> Path:
    """Public wrapper exposing the hadolint installer."""
    return _ensure_hadolint(version, cache_root)


def ensure_lualint(cache_root: Path) -> Path:
    """Public wrapper exposing the lualint installer."""
    return _ensure_lualint(cache_root)
