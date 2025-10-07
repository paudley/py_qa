# SPDX-License-Identifier: MIT
"""Linter that flags ad-hoc closures and inline lambdas."""

from __future__ import annotations

import ast
from pathlib import Path

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.core.models import Diagnostic, ToolOutcome, ToolExitCategory
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport
from .utils import collect_python_files


def run_closure_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Highlight closure factories that should use partials or helpers."""

    logger = state.logger
    files = collect_python_files(state)
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []

    for file_path in files:
        source = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        visitor = _ClosureVisitor(file_path, state, emit_to_logger)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)
        stdout_lines.extend(visitor.stdout)

    return InternalLintReport(
        outcome=ToolOutcome(
            tool="internal-closures",
            action="check",
            returncode=1 if diagnostics else 0,
            stdout=stdout_lines,
            stderr=[],
            diagnostics=diagnostics,
            exit_category=ToolExitCategory.DIAGNOSTIC if diagnostics else ToolExitCategory.SUCCESS,
        ),
        files=tuple(files),
    )


class _ClosureVisitor(ast.NodeVisitor):
    """Detect nested function factories and lambda assignments."""

    def __init__(self, path: Path, state: PreparedLintState, emit: bool) -> None:
        self._path = path
        self._state = state
        self._emit = emit
        self._logger = state.logger
        self.diagnostics: list[Diagnostic] = []
        self.stdout: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: D401 - visitor signature
        self._flag_lambda_assignments(node.body)
        for inner in node.body:
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_factory_function(node, inner.name):
                    self._record(inner, f"Nested function '{inner.name}' suggests using functools.partial or a helper")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: D401 - visitor signature
        self.visit_FunctionDef(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: D401 - visitor signature
        if isinstance(node.value, ast.Lambda):
            self._record(node.value, "Lambda assigned to a name should use functools.partial or a helper function")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: D401 - visitor signature
        if isinstance(node.value, ast.Lambda):
            self._record(node.value, "Lambda assigned to a name should use functools.partial or a helper function")
        self.generic_visit(node)

    def _flag_lambda_assignments(self, statements: list[ast.stmt]) -> None:
        for stmt in statements:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Lambda):
                self._record(stmt.value, "Lambda assigned inside function should leverage functools.partial or itertools utilities")
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Lambda):
                self._record(stmt.value, "Lambda assigned inside function should leverage functools.partial or itertools utilities")

    def _record(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", 1)
        normalized = normalize_path_key(self._path, base_dir=self._state.root)
        diagnostic = Diagnostic(
            file=normalized,
            line=line,
            column=getattr(node, "col_offset", None),
            severity=Severity.WARNING,
            message=message,
            tool="internal-closures",
            code="internal:closures",
        )
        self.diagnostics.append(diagnostic)
        formatted = f"{normalized}:{line}: {message}"
        self.stdout.append(formatted)
        if self._emit:
            self._logger.fail(formatted)


def _is_factory_function(container: ast.FunctionDef | ast.AsyncFunctionDef, inner_name: str) -> bool:
    for stmt in container.body:
        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name) and stmt.value.id == inner_name:
            return True
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Name) and stmt.value.id == inner_name:
            return True
    return False


__all__ = ["run_closure_linter"]
