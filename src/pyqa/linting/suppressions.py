# SPDX-License-Identifier: MIT
"""Linter that flags discouraged lint suppression directives."""

from __future__ import annotations

import re

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.core.models import Diagnostic, ToolExitCategory, ToolOutcome
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport
from .utils import collect_python_files

_SUPPRESSION_PATTERN = re.compile(r"#.*?(noqa|pylint:|mypy:|type:\s*ignore|nosec|pyright:)", re.IGNORECASE)


def run_suppression_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Detect suppression directives that require manual review."""

    _ = emit_to_logger
    files = collect_python_files(state)
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    for file_path in files:
        try:
            relative_parts = file_path.relative_to(state.root).parts
        except ValueError:
            relative_parts = file_path.parts
        if "tests" in relative_parts:
            continue
        text = file_path.read_text(encoding="utf-8")
        for idx, line in enumerate(text.splitlines(), start=1):
            if _SUPPRESSION_PATTERN.search(line):
                normalized = normalize_path_key(file_path, base_dir=state.root)
                message = (
                    f"Suppression directive on line {idx} violates the coding rules; "
                    "provide a justification or refactor the code instead."
                )
                diagnostics.append(
                    Diagnostic(
                        file=normalized,
                        line=idx,
                        column=None,
                        severity=Severity.WARNING,
                        message=message,
                        tool="internal-suppressions",
                        code="internal:suppressions",
                    ),
                )
                stdout_lines.append(f"{normalized}:{idx}: {message}")

    return InternalLintReport(
        outcome=ToolOutcome(
            tool="internal-suppressions",
            action="check",
            returncode=1 if diagnostics else 0,
            stdout=stdout_lines,
            stderr=stderr_lines,
            diagnostics=diagnostics,
            exit_category=ToolExitCategory.DIAGNOSTIC if diagnostics else ToolExitCategory.SUCCESS,
        ),
        files=tuple(files),
    )


__all__ = ["run_suppression_linter"]
