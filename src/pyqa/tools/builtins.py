# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Compatibility wrapper exposing built-in tool registration and exports."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from pathlib import Path

    from .base import Tool

    ActionlintCommand = _ActionlintCommand
    BanditCommand = _BanditCommand
    BlackCommand = _BlackCommand
    CheckmakeCommand = _CheckmakeCommand
    CpplintCommand = _CpplintCommand
    DockerfilelintCommand = _DockerfilelintCommand
    DotenvLinterCommand = _DotenvLinterCommand
    EslintCommand = _EslintCommand
    GolangciLintCommand = _GolangciLintCommand
    GtsCommand = _GtsCommand
    HadolintCommand = _HadolintCommand
    IsortCommand = _IsortCommand
    KubeLinterCommand = _KubeLinterCommand
    LuacheckCommand = _LuacheckCommand
    LualintCommand = _LualintCommand
    MypyCommand = _MypyCommand
    PerlCriticCommand = _PerlCriticCommand
    PerltidyCommand = _PerltidyCommand
    PhplintCommand = _PhplintCommand
    PrettierCommand = _PrettierCommand
    PyrightCommand = _PyrightCommand
    RemarkCommand = _RemarkCommand
    RuffCommand = _RuffCommand
    RuffFormatCommand = _RuffFormatCommand
    SeleneCommand = _SeleneCommand
    ShfmtCommand = _ShfmtCommand
    SpeccyCommand = _SpeccyCommand
    SqlfluffCommand = _SqlfluffCommand
    StylelintCommand = _StylelintCommand
    TombiCommand = _TombiCommand
    TscCommand = _TscCommand
    YamllintCommand = _YamllintCommand


def builtin_tools() -> Iterable[Tool]:
    """Yield all built-in tool definitions."""
    yield from python_tools()
    yield from misc_tools()


def _builtin_tools() -> Iterable[Tool]:
    """Backward-compatible alias for :func:`builtin_tools`."""
    yield from builtin_tools()


_COMMAND_ALIASES = {
    "ActionlintCommand": _ActionlintCommand,
    "BanditCommand": _BanditCommand,
    "BlackCommand": _BlackCommand,
    "CheckmakeCommand": _CheckmakeCommand,
    "CpplintCommand": _CpplintCommand,
    "DockerfilelintCommand": _DockerfilelintCommand,
    "DotenvLinterCommand": _DotenvLinterCommand,
    "EslintCommand": _EslintCommand,
    "GolangciLintCommand": _GolangciLintCommand,
    "GtsCommand": _GtsCommand,
    "HadolintCommand": _HadolintCommand,
    "IsortCommand": _IsortCommand,
    "KubeLinterCommand": _KubeLinterCommand,
    "LuacheckCommand": _LuacheckCommand,
    "LualintCommand": _LualintCommand,
    "MypyCommand": _MypyCommand,
    "PerlCriticCommand": _PerlCriticCommand,
    "PerltidyCommand": _PerltidyCommand,
    "PhplintCommand": _PhplintCommand,
    "PrettierCommand": _PrettierCommand,
    "PyrightCommand": _PyrightCommand,
    "RemarkCommand": _RemarkCommand,
    "RuffCommand": _RuffCommand,
    "RuffFormatCommand": _RuffFormatCommand,
    "SeleneCommand": _SeleneCommand,
    "ShfmtCommand": _ShfmtCommand,
    "SpeccyCommand": _SpeccyCommand,
    "SqlfluffCommand": _SqlfluffCommand,
    "StylelintCommand": _StylelintCommand,
    "TombiCommand": _TombiCommand,
    "TscCommand": _TscCommand,
    "YamllintCommand": _YamllintCommand,
}

globals().update(_COMMAND_ALIASES)

_COMMAND_EXPORTS = sorted(_COMMAND_ALIASES)
_LEGACY_COMMAND_EXPORTS = sorted(command.__name__ for command in _COMMAND_ALIASES.values())

__all__ = sorted(
    [
        "ACTIONLINT_VERSION_DEFAULT",
        "HADOLINT_VERSION_DEFAULT",
        "builtin_tools",
        "ensure_actionlint",
        "ensure_hadolint",
        "ensure_lualint",
        "register_builtin_tools",
        "_builtin_tools",
        "_ensure_actionlint",
        "_ensure_hadolint",
        "_ensure_lualint",
        *_COMMAND_EXPORTS,
        *_LEGACY_COMMAND_EXPORTS,
    ],
)


def ensure_actionlint(version: str, cache_root: Path) -> Path:
    """Public wrapper exposing the actionlint installer."""
    return _ensure_actionlint(version, cache_root)


def ensure_hadolint(version: str, cache_root: Path) -> Path:
    """Public wrapper exposing the hadolint installer."""
    return _ensure_hadolint(version, cache_root)


def ensure_lualint(cache_root: Path) -> Path:
    """Public wrapper exposing the lualint installer."""
    return _ensure_lualint(cache_root)
