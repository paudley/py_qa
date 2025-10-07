# SPDX-License-Identifier: MIT
"""Flag wide function signatures."""

from __future__ import annotations

import ast

from pyqa.cli.commands.lint.preparation import PreparedLintState

from ._ast_visitors import BaseAstLintVisitor, VisitorMetadata, run_ast_linter
from .base import InternalLintReport

_PARAMETER_THRESHOLD = 5


def run_signature_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Flag functions exceeding the parameter threshold or using ``**kwargs``.

    Args:
        state: Prepared lint execution context describing the workspace.
        emit_to_logger: Compatibility flag retained for historical callers;
            ignored because diagnostics route through the orchestrator.

    Returns:
        ``InternalLintReport`` describing all non-compliant signatures.
    """

    _ = emit_to_logger
    metadata = VisitorMetadata(tool="internal-signatures", code="internal:signatures")
    return run_ast_linter(
        state,
        metadata=metadata,
        visitor_factory=_SignatureVisitor,
    )


class _SignatureVisitor(BaseAstLintVisitor):
    """Analyse function definitions for signature width."""

    def visit_function_def(self, node: ast.FunctionDef) -> None:
        """Inspect synchronous function definitions for width and kwargs.

        Args:
            node: Function definition node to analyse.
        """

        self._evaluate_signature(node)
        self.generic_visit(node)

    def visit_async_function_def(self, node: ast.AsyncFunctionDef) -> None:
        """Inspect asynchronous function definitions for width and kwargs.

        Args:
            node: Async function definition node to analyse.
        """

        self._evaluate_signature(node)
        self.generic_visit(node)

    def _evaluate_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Emit diagnostics when ``node`` breaches parameter width expectations.

        Args:
            node: Function definition node to evaluate.
        """

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
            message = (
                "Function signature exceeds "
                f"{_PARAMETER_THRESHOLD} parameters or relies on **kwargs; introduce a parameter object."
            )
            self.record_issue(node, message)


__all__ = ["run_signature_linter"]
