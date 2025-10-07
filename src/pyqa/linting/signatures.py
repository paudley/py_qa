# SPDX-License-Identifier: MIT
"""Linter that flags wide function signatures."""

from __future__ import annotations

import ast
from pathlib import Path

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.core.models import Diagnostic, ToolExitCategory, ToolOutcome
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport
from .utils import collect_python_files

_PARAMETER_THRESHOLD = 5


def run_signature_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Flag functions exceeding the parameter threshold or using ``**kwargs``."""

    _ = emit_to_logger
    files = collect_python_files(state)
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []

    for file_path in files:
        source = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        visitor = _SignatureVisitor(file_path, state)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)
        stdout_lines.extend(visitor.stdout)

    return InternalLintReport(
        outcome=ToolOutcome(
            tool="internal-signatures",
            action="check",
            returncode=1 if diagnostics else 0,
            stdout=stdout_lines,
            stderr=[],
            diagnostics=diagnostics,
            exit_category=ToolExitCategory.DIAGNOSTIC if diagnostics else ToolExitCategory.SUCCESS,
        ),
        files=tuple(files),
    )


class _SignatureVisitor(ast.NodeVisitor):
    """Analyse function definitions for signature width."""

    def __init__(self, path: Path, state: PreparedLintState) -> None:
        self._path = path
        self._state = state
        self.diagnostics: list[Diagnostic] = []
        self.stdout: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: D401 - visitor signature
        self._evaluate_signature(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: D401 - visitor signature
        self._evaluate_signature(node)
        self.generic_visit(node)

    def _evaluate_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        count = (
            len(getattr(args, "posonlyargs", ()))
            + len(args.args)
            + len(args.kwonlyargs)
            + (1 if args.vararg else 0)
            + (1 if args.kwarg else 0)
        )
        needs_dataclass = count > _PARAMETER_THRESHOLD or args.kwarg is not None
        if needs_dataclass:
            normalized = normalize_path_key(self._path, base_dir=self._state.root)
            line = node.lineno
            message = (
                "Function signature exceeds "
                f"{_PARAMETER_THRESHOLD} parameters or relies on **kwargs; introduce a parameter object."
            )
            diagnostic = Diagnostic(
                file=normalized,
                line=line,
                column=None,
                severity=Severity.WARNING,
                message=message,
                tool="internal-signatures",
                code="internal:signatures",
            )
            self.diagnostics.append(diagnostic)
            formatted = f"{normalized}:{line}: {message}"
            self.stdout.append(formatted)


__all__ = ["run_signature_linter"]
