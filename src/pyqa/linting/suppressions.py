# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Linter that flags discouraged lint suppression directives."""

from __future__ import annotations

import re
import tokenize
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport, build_internal_report
from .utils import collect_python_files

if TYPE_CHECKING:  # pragma: no cover
    from pyqa.cli.commands.lint.preparation import PreparedLintState


@dataclass(slots=True)
class ValidSuppressionContext:
    """Context describing a validated suppression entry."""

    diagnostics: list[Diagnostic]
    stdout: list[str]
    file_path: Path
    state: PreparedLintState
    line_number: int
    reason: str


_SUPPRESSION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"#.*?(noqa|pylint:|mypy:|type:\s*ignore|nosec|pyright:|suppression_valid:)",
    re.IGNORECASE,
)
_SUPPRESSION_VALID_MARKER: Final[str] = "suppression_valid:"
_MIN_REASON_WORDS: Final[int] = 6
_DEFAULT_TEST_SEGMENT: Final[str] = "tests"
_ALLOWED_HINTS: Final[tuple[str, ...]] = (
    "lint:",
    "nosec B601",
    "nosec B602",
    "nosec B603",
    "nosec B604",
    "nosec B607",
)
_LINT_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\blint=([A-Za-z0-9_.:-]+)\b")


@dataclass(frozen=True, slots=True)
class SuppressionEntry:
    """Represent a validated suppression directive."""

    line: int
    lints: frozenset[str]
    reason: str


def run_suppression_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Detect suppression directives that require manual review.

    Args:
        state: Prepared lint execution context describing the workspace.
        emit_to_logger: Compatibility flag retained for legacy callers; ignored
            because diagnostic output is routed through the orchestrator.

    Returns:
        ``InternalLintReport`` detailing suppression findings in production code.
    """

    _ = emit_to_logger
    files = collect_python_files(state)
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []

    for file_path in files:
        try:
            relative_parts = file_path.relative_to(state.root).parts
        except ValueError:
            relative_parts = file_path.parts
        if _DEFAULT_TEST_SEGMENT in relative_parts:
            continue
        entries, issues = _parse_suppressions_for_file(file_path, state)
        diagnostics.extend(issues.diagnostics)
        stdout_lines.extend(issues.stdout)
        if not state.meta.show_valid_suppressions:
            continue
        for entry in entries:
            context = ValidSuppressionContext(
                diagnostics=diagnostics,
                stdout=stdout_lines,
                file_path=file_path,
                state=state,
                line_number=entry.line,
                reason=entry.reason,
            )
            _append_valid_suppression(context)

    return build_internal_report(
        tool="internal-suppressions",
        stdout=stdout_lines,
        diagnostics=diagnostics,
        files=files,
    )


def _parse_suppression_reason(comment: str) -> tuple[bool, bool, str, frozenset[str]]:
    """Return marker details extracted from ``comment``.

    Args:
        comment: Comment text containing a potential suppression directive.

    Returns:
        tuple[bool, bool, str, frozenset[str]]: Marker presence flag, validity flag,
        cleaned justification, and targeted lint identifiers.
    """

    lower = comment.lower()
    index = lower.find(_SUPPRESSION_VALID_MARKER)
    if index == -1:
        return False, False, "", frozenset()

    raw_reason = comment[index + len(_SUPPRESSION_VALID_MARKER) :].strip()
    cleaned = raw_reason.lstrip("-: ").strip()
    lint_ids = frozenset(match for match in _LINT_TOKEN_RE.findall(cleaned))
    if lint_ids:
        cleaned = _LINT_TOKEN_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return True, False, "", lint_ids

    if len(cleaned.split()) >= _MIN_REASON_WORDS:
        return True, True, cleaned, lint_ids

    return True, False, cleaned, lint_ids


def _append_valid_suppression(context: ValidSuppressionContext) -> None:
    """Record an informational diagnostic describing an accepted suppression.

    Args:
        context: Context object containing suppression metadata and buffers to update.
    """

    normalized = normalize_path_key(context.file_path, base_dir=context.state.root)
    message = f"Valid suppression justification on line {context.line_number}: {context.reason}"
    context.diagnostics.append(
        Diagnostic(
            file=normalized,
            line=context.line_number,
            column=None,
            severity=Severity.NOTICE,
            message=message,
            tool="internal-suppressions",
            code="internal:suppressions-valid",
        ),
    )
    context.stdout.append(f"{normalized}:{context.line_number}: {message}")


@dataclass(slots=True)
class _SuppressionIssues:
    """Collect diagnostics and stdout lines emitted during suppression parsing."""

    diagnostics: list[Diagnostic]
    stdout: list[str]


@dataclass(frozen=True, slots=True)
class _CommentEvaluation:
    """Aggregate results produced while evaluating a suppression comment."""

    entries: tuple[SuppressionEntry, ...]
    diagnostics: tuple[Diagnostic, ...]
    stdout: tuple[str, ...]


class SuppressionRegistry:
    """Lazy accessor for validated ``suppression_valid`` directives."""

    def __init__(self, root: Path) -> None:
        """Initialise the registry cache.

        Args:
            root: Repository root used to normalise stored paths.
        """

        self._root = root
        self._cache: dict[Path, tuple[SuppressionEntry, ...]] = {}

    def entries_for(self, path: Path) -> tuple[SuppressionEntry, ...]:
        """Return cached suppression entries for ``path``.

        Args:
            path: File path whose suppressions should be retrieved.

        Returns:
            tuple[SuppressionEntry, ...]: Cached suppression entries for the file.
        """

        resolved = path.resolve()
        try:
            return self._cache[resolved]
        except KeyError:
            entries, _ = _parse_suppressions_for_file(resolved, None, root=self._root)
            self._cache[resolved] = entries
            return entries

    def should_suppress(self, path: Path, line: int, *, tool: str, code: str) -> bool:
        """Return ``True`` when a diagnostic should be suppressed.

        Args:
            path: File containing the diagnostic.
            line: Line number of the diagnostic (1-indexed).
            tool: Tool identifier associated with the diagnostic.
            code: Diagnostic code emitted by the tool.

        Returns:
            bool: ``True`` when a matching suppression directive exists.
        """

        candidates = self.entries_for(path)
        if not candidates:
            return False
        tool_key = tool.lower()
        code_key = code.lower()
        for entry in candidates:
            if not _line_matches(line, entry.line):
                continue
            if not entry.lints:
                return True
            lower_targets = {target.lower() for target in entry.lints}
            if tool_key in lower_targets or code_key in lower_targets:
                return True
        return False


def _line_matches(diagnostic_line: int, suppression_line: int) -> bool:
    """Return ``True`` when a suppression comment applies to the diagnostic line.

    Args:
        diagnostic_line: Line number reported by the diagnostic.
        suppression_line: Line where the suppression directive is present.

    Returns:
        bool: ``True`` when the suppression applies to the diagnostic.
    """

    if diagnostic_line == suppression_line:
        return True
    return diagnostic_line - suppression_line == 1


def _parse_suppressions_for_file(
    file_path: Path,
    state: PreparedLintState | None,
    *,
    root: Path | None = None,
) -> tuple[tuple[SuppressionEntry, ...], _SuppressionIssues]:
    """Return validated suppression entries and any parsing issues.

    Args:
        file_path: Path to the Python source file under inspection.
        state: Prepared lint state used for diagnostics; ``None`` when only entries are required.
        root: Optional repository root used to normalise diagnostic paths.

    Returns:
        tuple[tuple[SuppressionEntry, ...], _SuppressionIssues]: Parsed suppression entries
        alongside any diagnostics and stdout lines emitted during parsing.
    """

    entries: list[SuppressionEntry] = []
    diagnostics: list[Diagnostic] = []
    stdout: list[str] = []
    base_dir = root or (state.root if state is not None else file_path.parent)

    text = file_path.read_text(encoding="utf-8")
    for token in tokenize.generate_tokens(StringIO(text).readline):
        if token.type != tokenize.COMMENT:
            continue
        comment = token.string
        evaluation = _evaluate_suppression_comment(
            comment=comment,
            token=token,
            file_path=file_path,
            base_dir=base_dir,
            state=state,
        )
        entries.extend(evaluation.entries)
        diagnostics.extend(evaluation.diagnostics)
        stdout.extend(evaluation.stdout)

    return tuple(entries), _SuppressionIssues(diagnostics=diagnostics, stdout=stdout)


def _evaluate_suppression_comment(
    *,
    comment: str,
    token: tokenize.TokenInfo,
    file_path: Path,
    base_dir: Path,
    state: PreparedLintState | None,
) -> _CommentEvaluation:
    """Inspect ``comment`` and return parsed suppression artefacts.

    Args:
        comment: Comment text extracted from the token stream.
        token: Token describing the original comment location.
        file_path: Path to the source file containing the comment.
        base_dir: Base directory used to normalise diagnostic paths.
        state: Prepared lint state or ``None`` when diagnostics are not required.

    Returns:
        _CommentEvaluation: Evaluation results containing entries, diagnostics, and stdout lines.
    """

    if not _SUPPRESSION_PATTERN.search(comment):
        return _CommentEvaluation(entries=(), diagnostics=(), stdout=())
    if any(hint in comment for hint in _ALLOWED_HINTS):
        return _CommentEvaluation(entries=(), diagnostics=(), stdout=())

    marker_present, valid_reason, reason, lint_ids = _parse_suppression_reason(comment)
    line_number = token.start[0]
    if marker_present and valid_reason:
        entry = SuppressionEntry(line=line_number, lints=lint_ids, reason=reason)
        return _CommentEvaluation(entries=(entry,), diagnostics=(), stdout=())
    if state is None:
        return _CommentEvaluation(entries=(), diagnostics=(), stdout=())

    normalized = normalize_path_key(file_path, base_dir=base_dir)
    message = (
        f"Suppression justification must provide at least {_MIN_REASON_WORDS} words after"
        " 'suppression_valid:'; refactor or expand the explanation."
        if marker_present and not valid_reason
        else (
            "Suppression directive on line "
            f"{line_number} violates the coding rules; provide a justification or refactor the code instead."
        )
    )
    diagnostic = Diagnostic(
        file=normalized,
        line=line_number,
        column=None,
        severity=Severity.WARNING,
        message=message,
        tool="internal-suppressions",
        code="internal:suppressions",
    )
    stdout_line = f"{normalized}:{line_number}: {message}"
    return _CommentEvaluation(entries=(), diagnostics=(diagnostic,), stdout=(stdout_line,))


__all__ = ["run_suppression_linter", "SuppressionRegistry"]
