# SPDX-License-Identifier: MIT
"""Linter that warns when ``functools.lru_cache`` is used directly."""

from __future__ import annotations

import ast
from pathlib import Path

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.core.models import Diagnostic, ToolOutcome, ToolExitCategory
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport
from .utils import collect_python_files


def run_cache_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Flag direct ``functools.lru_cache`` usage to enforce internal cache wrappers."""

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
        visitor = _CacheVisitor(file_path, state, emit_to_logger)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)
        stdout_lines.extend(visitor.stdout)

    return InternalLintReport(
        outcome=ToolOutcome(
            tool="internal-cache",
            action="check",
            returncode=1 if diagnostics else 0,
            stdout=stdout_lines,
            stderr=[],
            diagnostics=diagnostics,
            exit_category=ToolExitCategory.DIAGNOSTIC if diagnostics else ToolExitCategory.SUCCESS,
        ),
        files=tuple(files),
    )


class _CacheVisitor(ast.NodeVisitor):
    """Detect references to ``lru_cache`` decorators."""

    def __init__(self, path: Path, state: PreparedLintState, emit: bool) -> None:
        self._path = path
        self._state = state
        self._emit = emit
        self._logger = state.logger
        self.diagnostics: list[Diagnostic] = []
        self.stdout: list[str] = []
        self._functools_aliases: set[str] = set()
        self._lru_aliases: set[str] = {"lru_cache"}

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: D401 - visitor signature
        if node.module == "functools":
            for alias in node.names:
                name = alias.asname or alias.name
                if alias.name == "lru_cache":
                    self._lru_aliases.add(name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: D401 - visitor signature
        for alias in node.names:
            if alias.name == "functools":
                name = alias.asname or alias.name
                self._functools_aliases.add(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: D401 - visitor signature
        self._check_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: D401 - visitor signature
        self._check_decorators(node.decorator_list)
        self.generic_visit(node)

    def _check_decorators(self, decorators: list[ast.expr]) -> None:
        for decorator in decorators:
            if self._is_banned_decorator(decorator):
                self._record(decorator, "Use pyqa.cache helpers instead of functools.lru_cache")

    def _is_banned_decorator(self, expr: ast.expr) -> bool:
        if isinstance(expr, ast.Name):
            return expr.id in self._lru_aliases
        if isinstance(expr, ast.Attribute):
            value = expr.value
            if isinstance(value, ast.Name) and value.id in self._functools_aliases and expr.attr == "lru_cache":
                return True
        if isinstance(expr, ast.Call):
            return self._is_banned_decorator(expr.func)
        return False

    def _record(self, node: ast.AST, message: str) -> None:
        normalized = normalize_path_key(self._path, base_dir=self._state.root)
        line = getattr(node, "lineno", 1)
        diagnostic = Diagnostic(
            file=normalized,
            line=line,
            column=getattr(node, "col_offset", None),
            severity=Severity.WARNING,
            message=message,
            tool="internal-cache",
            code="internal:cache",
        )
        self.diagnostics.append(diagnostic)
        formatted = f"{normalized}:{line}: {message}"
        self.stdout.append(formatted)
        if self._emit:
            self._logger.fail(formatted)


__all__ = ["run_cache_linter"]
