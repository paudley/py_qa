# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Linter that flags discouraged lint suppression directives."""

from __future__ import annotations

import re
import tokenize
from io import StringIO
from typing import Final

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport, build_internal_report
from .utils import collect_python_files

_SUPPRESSION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"#.*?(noqa|pylint:|mypy:|type:\s*ignore|nosec|pyright:)",
    re.IGNORECASE,
)
_DEFAULT_TEST_SEGMENT: Final[str] = "tests"
_ALLOWED_HINTS: Final[tuple[str, ...]] = (
    "lint:",
    "nosec B601",
    "nosec B602",
    "nosec B603",
    "nosec B604",
    "nosec B607",
)


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
        text = file_path.read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(StringIO(text).readline):
            if token.type != tokenize.COMMENT:
                continue
            comment = token.string
            if not _SUPPRESSION_PATTERN.search(comment):
                continue
            if any(hint in comment for hint in _ALLOWED_HINTS):
                continue
            normalized = normalize_path_key(file_path, base_dir=state.root)
            message = (
                f"Suppression directive on line {token.start[0]} violates the coding rules; "
                "provide a justification or refactor the code instead."
            )
            diagnostics.append(
                Diagnostic(
                    file=normalized,
                    line=token.start[0],
                    column=None,
                    severity=Severity.WARNING,
                    message=message,
                    tool="internal-suppressions",
                    code="internal:suppressions",
                ),
            )
            stdout_lines.append(f"{normalized}:{token.start[0]}: {message}")

    return build_internal_report(
        tool="internal-suppressions",
        stdout=stdout_lines,
        diagnostics=diagnostics,
        files=files,
    )


__all__ = ["run_suppression_linter"]
