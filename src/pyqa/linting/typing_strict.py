# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Discourage ``Any``/``object`` annotations."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final, cast

from pyqa.cli.commands.lint.preparation import PreparedLintState

from ._ast_visitors import BaseAstLintVisitor, VisitorMetadata, run_ast_linter
from .base import InternalLintReport

_BANNED_NAMES: Final[set[str]] = {"Any", "object"}
_BANNED_QUALIFIED: Final[set[str]] = {"typing.Any", "builtins.object"}


def run_typing_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Detect banned annotations across the targeted files.

    Args:
        state: Prepared lint execution context describing the workspace.
        emit_to_logger: Compatibility flag retained for legacy callers; output
            is routed through the orchestrator so this flag is ignored.

    Returns:
        ``InternalLintReport`` collecting diagnostics for disallowed types.
    """

    _ = emit_to_logger
    metadata = VisitorMetadata(tool="internal-types", code="internal:typing")

    def _on_parse_error(path: Path, exc: SyntaxError) -> str:
        """Return the warning message emitted when ``path`` fails to parse.

        Args:
            path: File whose contents produced a syntax error.
            exc: Syntax error raised during parsing.

        Returns:
            String describing the failure for stdout emission.
        """

        return f"Syntax error while analysing annotations in {path}: {exc.msg}"

    return run_ast_linter(
        state,
        metadata=metadata,
        visitor_factory=_AnnotationVisitor,
        parse_error_handler=_on_parse_error,
    )


class _AnnotationVisitor(BaseAstLintVisitor):
    """AST visitor that records banned annotations."""

    # Function/method definitions -------------------------------------------------

    def visit_function_def(self, node: ast.FunctionDef) -> None:
        """Inspect synchronous function definitions for banned annotations.

        Args:
            node: Function definition node to analyse.
        """

        self._check_arguments(node.args)
        if node.returns is not None and _contains_banned_annotation(node.returns):
            self.record_issue(node.returns, "Return annotation uses banned Any/object type")
        self.generic_visit(node)

    def visit_async_function_def(self, node: ast.AsyncFunctionDef) -> None:
        """Inspect asynchronous function definitions for banned annotations.

        Args:
            node: Async function definition node to analyse.
        """

        self.visit_function_def(cast(ast.FunctionDef, node))

    # Assignments ----------------------------------------------------------------

    def visit_ann_assign(self, node: ast.AnnAssign) -> None:
        """Inspect annotated assignments for banned annotations.

        Args:
            node: Annotated assignment node to analyse.
        """

        if node.annotation is not None and _contains_banned_annotation(node.annotation):
            self.record_issue(node.annotation, "Variable annotation uses banned Any/object type")
        self.generic_visit(node)

    # Helpers --------------------------------------------------------------------

    def _check_arguments(self, args: ast.arguments) -> None:
        """Inspect ``args`` for banned annotations.

        Args:
            args: Function arguments node containing annotations.
        """

        for argument in list(getattr(args, "posonlyargs", ())) + list(args.args) + list(args.kwonlyargs):
            if argument.annotation is not None and _contains_banned_annotation(argument.annotation):
                self.record_issue(argument, "Parameter annotation uses banned Any/object type")
        if args.vararg and args.vararg.annotation and _contains_banned_annotation(args.vararg.annotation):
            self.record_issue(args.vararg, "*args annotation uses banned Any/object type")
        if args.kwarg and args.kwarg.annotation and _contains_banned_annotation(args.kwarg.annotation):
            self.record_issue(args.kwarg, "**kwargs annotation uses banned Any/object type")


def _contains_banned_annotation(node: ast.AST) -> bool:
    """Return ``True`` when ``node`` references a banned annotation.

    Args:
        node: AST node representing an annotation.

    Returns:
        ``True`` if the annotation uses ``Any`` or ``object`` in any form.
    """

    if isinstance(node, ast.Name):
        return node.id in _BANNED_NAMES
    if isinstance(node, ast.Attribute):
        return _attribute_to_name(node) in _BANNED_QUALIFIED
    if isinstance(node, ast.Subscript):
        return any(_contains_banned_annotation(target) for target in (node.value, node.slice))
    if isinstance(node, ast.Tuple):
        return any(_contains_banned_annotation(elt) for elt in node.elts)
    if isinstance(node, ast.Constant):
        return False
    return any(_contains_banned_annotation(child) for child in ast.iter_child_nodes(node))


def _attribute_to_name(node: ast.Attribute) -> str:
    """Return dotted name reconstructed from ``node``.

    Args:
        node: Attribute node forming part of an annotation.

    Returns:
        Fully qualified dotted name extracted from the attribute chain.
    """

    if isinstance(node.value, ast.Attribute):
        prefix = _attribute_to_name(node.value)
    elif isinstance(node.value, ast.Name):
        prefix = node.value.id
    else:
        prefix = ""
    return f"{prefix}.{node.attr}" if prefix else node.attr


__all__ = ["run_typing_linter"]
