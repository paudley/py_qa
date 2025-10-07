# SPDX-License-Identifier: MIT
"""Warn when ``functools.lru_cache`` is used directly."""

from __future__ import annotations

import ast
from pathlib import Path

from pyqa.cli.commands.lint.preparation import PreparedLintState

from ._ast_visitors import BaseAstLintVisitor, VisitorMetadata, run_ast_linter
from .base import InternalLintReport

_FUNCTOOLS_MODULE = "functools"
_LRU_CACHE_NAME = "lru_cache"


def run_cache_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Flag direct ``functools.lru_cache`` usage to enforce internal cache wrappers.

    Args:
        state: Prepared lint execution context describing the workspace.
        emit_to_logger: Compatibility flag; internal tools emit diagnostics via
            the orchestrator rather than direct logging so the flag is ignored.

    Returns:
        ``InternalLintReport`` with diagnostics for every forbidden decorator.
    """

    _ = emit_to_logger
    metadata = VisitorMetadata(tool="internal-cache", code="internal:cache")
    return run_ast_linter(
        state,
        metadata=metadata,
        visitor_factory=_CacheVisitor,
    )


class _CacheVisitor(BaseAstLintVisitor):
    """Detect references to ``lru_cache`` decorators."""

    def __init__(self, path: Path, state: PreparedLintState, metadata: VisitorMetadata) -> None:
        """Initialise visitor state and alias registries.

        Args:
            path: File currently under analysis.
            state: Prepared lint execution context.
            metadata: Tool descriptor for diagnostics emitted by this visitor.
        """

        super().__init__(path, state, metadata)
        self._functools_aliases: set[str] = set()
        self._lru_aliases: set[str] = {_LRU_CACHE_NAME}

    def visit_import_from(self, node: ast.ImportFrom) -> None:
        """Track ``lru_cache`` names imported from functools.

        Args:
            node: AST node describing the ``from x import`` statement.
        """

        if node.module == _FUNCTOOLS_MODULE:
            for alias in node.names:
                name = alias.asname or alias.name
                if alias.name == _LRU_CACHE_NAME:
                    self._lru_aliases.add(name)
        self.generic_visit(node)

    def visit_import(self, node: ast.Import) -> None:
        """Track aliases referencing the ``functools`` module.

        Args:
            node: AST node describing the import statement.
        """

        for alias in node.names:
            if alias.name == _FUNCTOOLS_MODULE:
                name = alias.asname or alias.name
                self._functools_aliases.add(name)
        self.generic_visit(node)

    def visit_function_def(self, node: ast.FunctionDef) -> None:
        """Inspect decorators on synchronous function definitions.

        Args:
            node: Function definition node to analyse.
        """

        self._check_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_async_function_def(self, node: ast.AsyncFunctionDef) -> None:
        """Inspect decorators on asynchronous function definitions.

        Args:
            node: Async function definition node to analyse.
        """

        self._check_decorators(node.decorator_list)
        self.generic_visit(node)

    def _check_decorators(self, decorators: list[ast.expr]) -> None:
        """Emit diagnostics when ``decorators`` reference banned cache usage.

        Args:
            decorators: Decorator expressions applied to the target function.
        """

        for decorator in decorators:
            if self._is_banned_decorator(decorator):
                self.record_issue(
                    decorator,
                    "Use pyqa.cache helpers instead of functools.lru_cache",
                )

    def _is_banned_decorator(self, expr: ast.expr) -> bool:
        """Return ``True`` when ``expr`` resolves to ``functools.lru_cache``.

        Args:
            expr: Decorator expression to evaluate.

        Returns:
            ``True`` if the expression refers to the prohibited decorator.
        """

        if isinstance(expr, ast.Name):
            return expr.id in self._lru_aliases
        if isinstance(expr, ast.Attribute):
            value = expr.value
            if isinstance(value, ast.Name) and value.id in self._functools_aliases and expr.attr == _LRU_CACHE_NAME:
                return True
        if isinstance(expr, ast.Call):
            return self._is_banned_decorator(expr.func)
        return False


__all__ = ["run_cache_linter"]
