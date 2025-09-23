# SPDX-License-Identifier: MIT
"""Parsers for Lua tooling output."""

from __future__ import annotations

import re
from typing import Sequence

from ..models import RawDiagnostic
from ..severity import Severity
from ..tools.base import ToolContext

LUALINT_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?:\*\*\*\s*)?(?P<message>.+)$"
)


def parse_lualint(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse lualint text output."""

    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Usage"):
            continue
        match = LUALINT_PATTERN.match(line)
        if not match:
            continue
        results.append(
            RawDiagnostic(
                file=match.group("file"),
                line=int(match.group("line")),
                column=None,
                severity=Severity.WARNING,
                message=match.group("message").strip(),
                code=None,
                tool="lualint",
            )
        )
    return results


LUACHECK_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<column>\d+):\s+\((?P<code>[A-Z]\d+)\)\s+(?P<message>.+)$"
)


def parse_luacheck(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse luacheck plain formatter output."""

    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Total:"):
            continue
        match = LUACHECK_PATTERN.match(line)
        if not match:
            continue
        code = match.group("code")
        severity = Severity.ERROR if code.startswith("E") else Severity.WARNING
        results.append(
            RawDiagnostic(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                severity=severity,
                message=match.group("message").strip(),
                code=code,
                tool="luacheck",
            )
        )
    return results


__all__ = [
    "parse_lualint",
    "parse_luacheck",
]
