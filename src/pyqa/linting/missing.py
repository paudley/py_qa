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
_DOC_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".markdown", ".rst"})
_ESCAPE_CHAR: Final[str] = "\\"
_SINGLE_QUOTE: Final[str] = "'"
_DOUBLE_QUOTE: Final[str] = '"'
_BACKTICK: Final[str] = "`"
_INTERFACES_SEGMENT: Final[str] = "interfaces"


@dataclass(frozen=True, slots=True)
class _Finding:
    """Represent a missing-functionality finding discovered in a file."""

    file: Path
    line: int
    message: str
    code: str


def run_missing_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
) -> InternalLintReport:
    """Execute the missing functionality linter and return its report.

    Args:
        state: Prepared lint state describing the current invocation. Markdown
            and other documentation files are ignored automatically.
        emit_to_logger: Unused compatibility flag for the internal runner API.

    Returns:
        InternalLintReport: Aggregated diagnostics describing missing work.
    """

    _ = emit_to_logger
    findings: list[_Finding] = []
    target_files = collect_target_files(state)
    for file_path in target_files:
        if file_path.suffix.lower() in _DOC_SUFFIXES:
            continue
        findings.extend(_scan_file(file_path))

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


def _scan_file(path: Path) -> list[_Finding]:
    """Collect missing-functionality findings from ``path``.

    Args:
        path: File path under inspection.

    Returns:
        list[_Finding]: Findings detected within the file.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    findings: list[_Finding] = []
    suffix = path.suffix.lower()
    skip_not_implemented = _INTERFACES_SEGMENT in path.parts
    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        generic_marker = _match_generic_marker(raw_line)
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

        python_match = _PYTHON_NOT_IMPLEMENTED_PATTERN.search(raw_line) if suffix in _PYTHON_SUFFIXES else None
        if (
            python_match is not None
            and not skip_not_implemented
            and not _is_within_string(raw_line, python_match.start())
        ):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Raising NotImplementedError indicates missing functionality.",
                    code="missing:not-implemented-error",
                ),
            )
            continue

        cs_match = _CS_NOT_IMPLEMENTED_PATTERN.search(raw_line) or _CS_NOT_SUPPORTED_PATTERN.search(raw_line)
        if cs_match is not None and not _is_within_string(raw_line, cs_match.start()):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Throwing NotImplemented/NotSupported exception signals missing functionality.",
                    code="missing:not-implemented-exception",
                ),
            )
            continue

        if _RUST_PLACEHOLDER_PATTERN.search(stripped):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Placeholder macro indicates missing implementation.",
                    code="missing:placeholder-macro",
                ),
            )
            continue

        not_impl_match = _NOT_IMPLEMENTED_PATTERN.search(raw_line)
        if (
            not_impl_match is not None
            and not skip_not_implemented
            and not _is_within_string(raw_line, not_impl_match.start())
        ):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Line references 'not implemented', suggesting incomplete functionality.",
                    code="missing:not-implemented-text",
                ),
            )
            continue
    return findings


def _match_generic_marker(line: str) -> str | None:
    """Identify the missing-work marker present within ``line``.

    Args:
        line: Line of source text to inspect.

    Returns:
        str | None: Matched marker text when detected; otherwise ``None``.
    """

    marker_match = _GENERIC_MARKER_PATTERN.search(line)
    if marker_match is not None and not _is_within_string(line, marker_match.start()):
        return marker_match.group(0)
    return None


def _is_within_string(line: str, index: int) -> bool:
    """Determine whether ``index`` is located within a string literal.

    Args:
        line: Source line containing potential string delimiters.
        index: Character index to evaluate for string membership.

    Returns:
        bool: ``True`` when ``index`` resides within a quoted string region.
    """

    in_single = False
    in_double = False
    in_backtick = False
    escape = False
    for position, char in enumerate(line):
        if position == index:
            return in_single or in_double or in_backtick
        if escape:
            escape = False
            continue
        if char == _ESCAPE_CHAR:
            escape = True
            continue
        if char == _SINGLE_QUOTE and not in_double and not in_backtick:
            in_single = not in_single
            continue
        if char == _DOUBLE_QUOTE and not in_single and not in_backtick:
            in_double = not in_double
            continue
        if char == _BACKTICK and not in_single and not in_double:
            in_backtick = not in_backtick
    return in_single or in_double or in_backtick


__all__ = ["run_missing_linter"]
