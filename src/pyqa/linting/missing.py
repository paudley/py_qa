# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Internal linter that flags markers for missing functionality."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport, build_internal_report
from .utils import collect_target_files

if TYPE_CHECKING:  # pragma: no cover - type checking import
    from pyqa.cli.commands.lint.preparation import PreparedLintState

_GENERIC_MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:TODO|FIXME|TBD|XXX|PENDING|STUB)\b",
    re.IGNORECASE,
)
_NOT_IMPLEMENTED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bnot[\s_-]?implemented\b",
    re.IGNORECASE,
)
_RUST_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:todo|unimplemented)\s*!",
    re.IGNORECASE,
)
_CS_NOT_IMPLEMENTED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bthrow\s+new\s+NotImplementedException\b",
    re.IGNORECASE,
)
_CS_NOT_SUPPORTED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bthrow\s+new\s+NotSupportedException\b",
    re.IGNORECASE,
)
_PYTHON_NOT_IMPLEMENTED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\braise\s+NotImplementedError\b",
    re.IGNORECASE,
)
_PYTHON_SUFFIXES: Final[frozenset[str]] = frozenset({".py", ".pyi"})


@dataclass(frozen=True, slots=True)
class _Finding:
    """Represent a missing-functionality finding discovered in a file."""

    file: Path
    line: int
    message: str
    code: str


def run_missing_linter(
    state: "PreparedLintState",
    *,
    emit_to_logger: bool,
) -> InternalLintReport:
    """Execute the missing functionality linter and return its report.

    Args:
        state: Prepared lint state describing the current invocation.
        emit_to_logger: Unused compatibility flag for the internal runner API.

    Returns:
        InternalLintReport: Aggregated diagnostics describing missing work.
    """

    _ = emit_to_logger
    findings: list[_Finding] = []
    target_files = collect_target_files(state)
    for file_path in target_files:
        findings.extend(_scan_file(file_path, root=state.root))

    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    for finding in findings:
        normalized = normalize_path_key(finding.file, base_dir=state.root)
        diagnostics.append(
            Diagnostic(
                file=normalized,
                line=finding.line,
                column=None,
                severity=Severity.ERROR,
                message=finding.message,
                tool="missing",
                code=finding.code,
            ),
        )
        stdout_lines.append(f"{normalized}:{finding.line}: {finding.message}")

    return build_internal_report(
        tool="missing",
        stdout=stdout_lines,
        diagnostics=diagnostics,
        files=tuple(sorted(target_files)),
    )


def _scan_file(path: Path, *, root: Path) -> list[_Finding]:
    """Return findings detected in ``path``."""

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    findings: list[_Finding] = []
    suffix = path.suffix.lower()
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        generic_marker = _match_generic_marker(line)
        if generic_marker is not None:
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message=f"Marker '{generic_marker}' indicates missing implementation.",
                    code="missing:marker",
                ),
            )
            continue

        if _NOT_IMPLEMENTED_PATTERN.search(line):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Line references 'not implemented', suggesting incomplete functionality.",
                    code="missing:not-implemented-text",
                ),
            )
            continue

        if _RUST_PLACEHOLDER_PATTERN.search(line):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Placeholder macro indicates missing implementation.",
                    code="missing:placeholder-macro",
                ),
            )
            continue

        if _CS_NOT_IMPLEMENTED_PATTERN.search(line) or _CS_NOT_SUPPORTED_PATTERN.search(line):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Throwing NotImplemented/NotSupported exception signals missing functionality.",
                    code="missing:not-implemented-exception",
                ),
            )
            continue

        if suffix in _PYTHON_SUFFIXES and _PYTHON_NOT_IMPLEMENTED_PATTERN.search(line):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Raising NotImplementedError indicates missing functionality.",
                    code="missing:not-implemented-error",
                ),
            )
    return findings


def _match_generic_marker(line: str) -> str | None:
    """Return the matched missing-work marker when present."""

    marker_match = _GENERIC_MARKER_PATTERN.search(line)
    if marker_match is not None:
        return marker_match.group(0)
    return None


__all__ = ["run_missing_linter"]
