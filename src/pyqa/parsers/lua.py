# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for Lua tooling output."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from pyqa.core.severity import Severity

from ..core.models import RawDiagnostic
from ..tools.base import ToolContext
from .base import (
    DiagnosticDetails,
    DiagnosticLocation,
    append_diagnostic,
    iter_pattern_matches,
)

LUALINT_PATTERN = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?:\*\*\*\s*)?(?P<message>.+)$")
LUALINT_TOOL_NAME: Final[str] = "lualint"
LUACHECK_TOOL_NAME: Final[str] = "luacheck"


def parse_lualint(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse lualint text output into diagnostics.

    Args:
        stdout: Sequence of lines returned by lualint.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics flagged by lualint.
    """

    del context
    results: list[RawDiagnostic] = []
    for match in iter_pattern_matches(stdout, LUALINT_PATTERN, skip_prefixes=("Usage",)):
        location = DiagnosticLocation(
            file=match.group("file"),
            line=int(match.group("line")),
            column=None,
        )
        details = _build_lua_details(
            LUALINT_TOOL_NAME,
            match.group("message"),
            Severity.WARNING,
        )
        append_diagnostic(results, location=location, details=details)
    return results


LUACHECK_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<column>\d+):\s+\((?P<code>[A-Z]\d+)\)\s+(?P<message>.+)$",
)


def parse_luacheck(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse luacheck plain formatter output into diagnostics.

    Args:
        stdout: Sequence of luacheck output lines.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing luacheck findings.
    """

    del context
    results: list[RawDiagnostic] = []
    for match in iter_pattern_matches(stdout, LUACHECK_PATTERN, skip_prefixes=("Total:",)):
        code = match.group("code")
        severity = Severity.ERROR if code.startswith("E") else Severity.WARNING
        location = DiagnosticLocation(
            file=match.group("file"),
            line=int(match.group("line")),
            column=int(match.group("column")),
        )
        details = _build_lua_details(
            LUACHECK_TOOL_NAME,
            match.group("message"),
            severity,
            code,
        )
        append_diagnostic(results, location=location, details=details)
    return results


def _build_lua_details(
    tool: str,
    message: str,
    severity: Severity,
    code: str | None = None,
) -> DiagnosticDetails:
    """Return diagnostic metadata for Lua tooling."""

    normalized_message = message.strip()
    normalized_code = code.upper() if code and tool == LUACHECK_TOOL_NAME else code
    return DiagnosticDetails(
        severity=severity,
        message=normalized_message,
        tool=tool,
        code=normalized_code,
    )


__all__ = [
    "parse_luacheck",
    "parse_lualint",
]
