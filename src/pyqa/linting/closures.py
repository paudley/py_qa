# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Flag ad-hoc closures and inline lambdas."""

from __future__ import annotations

import ast
from collections.abc import Iterable

from pyqa.interfaces.linting import PreparedLintState

from ._ast_visitors import BaseAstLintVisitor, VisitorMetadata, run_ast_linter
from .base import InternalLintReport


def run_closure_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Highlight closure factories that should use partials or helpers.

    Args:
        state: Prepared lint execution context describing the workspace.
        emit_to_logger: Compatibility flag retained for legacy callers; ignored
            because diagnostics flow through the orchestrator pipeline.

    Returns:
        ``InternalLintReport`` enumerating closure/lambda misuse incidents.
    """

    _ = emit_to_logger
    metadata = VisitorMetadata(tool="internal-closures", code="internal:closures")
    return run_ast_linter(
        state,
        metadata=metadata,
        visitor_factory=_ClosureVisitor,
    )


class _ClosureVisitor(BaseAstLintVisitor):
    """Detect nested function factories and lambda assignments."""

    def visit_function_def(self, node: ast.FunctionDef) -> None:
        """Inspect synchronous function definitions for factories/lambdas.

        Args:
            node: Function definition node to analyse.
        """

        self._inspect_function(node, node.body, node)

    def visit_async_function_def(self, node: ast.AsyncFunctionDef) -> None:
        """Inspect asynchronous function definitions for factories/lambdas.

        Args:
            node: Async function definition node to analyse.
        """

        self._inspect_function(node, node.body, node)

    def visit_assign(self, node: ast.Assign) -> None:
        """Flag lambda assignments at module scope.

        Args:
            node: Assignment node to analyse for lambda binding.
        """

        if isinstance(node.value, ast.Lambda):
            self.record_issue(
                node.value,
                "Lambda assigned to a name should use functools.partial or itertools helpers",
            )
        self.generic_visit(node)

    def visit_ann_assign(self, node: ast.AnnAssign) -> None:
        """Flag annotated lambda assignments at module scope.

        Args:
            node: Annotated assignment node to analyse for lambda binding.
        """

        if isinstance(node.value, ast.Lambda):
            self.record_issue(
                node.value,
                "Lambda assigned to a name should use functools.partial or itertools helpers",
            )
        self.generic_visit(node)

    def _inspect_function(
        self,
        node: ast.AST,
        statements: Iterable[ast.stmt],
        container: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """Inspect ``container`` for nested factories and lambda assignments.

        Args:
            node: AST node currently being visited (function or async function).
            statements: Body statements contained within ``container``.
            container: Function definition that might host nested factories.
        """

        self._flag_lambda_assignments(statements)
        for inner in statements:
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_factory_function(
                container, inner.name
            ):
                self.record_issue(
                    inner,
                    f"Nested function '{inner.name}' suggests using functools.partial or a helper",
                )
        self.generic_visit(node)

    def _flag_lambda_assignments(self, statements: Iterable[ast.stmt]) -> None:
        """Record lambda assignments found within ``statements``.

        Args:
            statements: Iterable of AST statements to inspect for lambda usage.
        """

        message = "Lambda assigned inside function should leverage functools.partial or itertools utilities"
        for stmt in statements:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Lambda):
                self.record_issue(stmt.value, message)
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Lambda):
                self.record_issue(stmt.value, message)


def _is_factory_function(container: ast.FunctionDef | ast.AsyncFunctionDef, inner_name: str) -> bool:
    """Return ``True`` when ``inner_name`` is returned or assigned in ``container``.

    Args:
        container: Function whose body is inspected for delegation patterns.
        inner_name: Name of the nested function under scrutiny.

    Returns:
        ``True`` if the nested function behaves like a closure factory helper.
    """

    for stmt in container.body:
        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name) and stmt.value.id == inner_name:
            return True
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Name) and stmt.value.id == inner_name:
            return True
    return False


__all__ = ["run_closure_linter"]
