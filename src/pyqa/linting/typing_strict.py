# SPDX-License-Identifier: MIT
"""Linter that discourages ``Any``/``object`` annotations."""

from __future__ import annotations

import ast
from pathlib import Path

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.core.models import Diagnostic, ToolOutcome, ToolExitCategory
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport
from .utils import collect_python_files

_BANNED_NAMES = {"Any", "object"}
_BANNED_QUALIFIED = {"typing.Any", "builtins.object"}


def run_typing_linter(state: PreparedLintState, *, emit_to_logger: bool = True) -> InternalLintReport:
    """Detect banned annotations across the targeted files."""

    logger = state.logger
    files = collect_python_files(state)
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []

    for file_path in files:
        source = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            message = f"Syntax error while analysing annotations: {exc.msg}"
            stdout_lines.append(message)
            if emit_to_logger:
                logger.warn(message)
            continue
        visitor = _AnnotationVisitor(file_path, state, emit_to_logger)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)
        stdout_lines.extend(visitor.stdout)

    return InternalLintReport(
        outcome=ToolOutcome(
            tool="internal-types",
            action="check",
            returncode=1 if diagnostics else 0,
            stdout=stdout_lines,
            stderr=[],
            diagnostics=diagnostics,
            exit_category=ToolExitCategory.DIAGNOSTIC if diagnostics else ToolExitCategory.SUCCESS,
        ),
        files=tuple(files),
    )


class _AnnotationVisitor(ast.NodeVisitor):
    """AST visitor that records banned annotations."""

    def __init__(self, path: Path, state: PreparedLintState, emit: bool) -> None:
        self._path = path
        self._state = state
        self._emit = emit
        self._logger = state.logger
        self.diagnostics: list[Diagnostic] = []
        self.stdout: list[str] = []

    def _record(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", 1)
        normalized = normalize_path_key(self._path, base_dir=self._state.root)
        diagnostic = Diagnostic(
            file=normalized,
            line=line,
            column=getattr(node, "col_offset", None),
            severity=Severity.WARNING,
            message=message,
            tool="internal-types",
            code="internal:typing",
        )
        self.diagnostics.append(diagnostic)
        formatted = f"{normalized}:{line}: {message}"
        self.stdout.append(formatted)
        if self._emit:
            self._logger.fail(formatted)

    # Function/method definitions -------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: D401 - standard visitor signature
        self._check_arguments(node.args)
        if node.returns is not None and _contains_banned_annotation(node.returns):
            self._record(node.returns, "Return annotation uses banned Any/object type")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: D401 - standard visitor signature
        self.visit_FunctionDef(node)

    # Assignments ----------------------------------------------------------------

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: D401 - standard visitor signature
        if node.annotation is not None and _contains_banned_annotation(node.annotation):
            self._record(node.annotation, "Variable annotation uses banned Any/object type")
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:  # noqa: D401 - standard visitor signature
        # ``visit_FunctionDef`` handles argument annotations via args helper.
        return

    # Helpers --------------------------------------------------------------------

    def _check_arguments(self, args: ast.arguments) -> None:
        for argument in (
            list(getattr(args, "posonlyargs", ()))
            + list(args.args)
            + list(args.kwonlyargs)
        ):
            if argument.annotation is not None and _contains_banned_annotation(argument.annotation):
                self._record(argument, "Parameter annotation uses banned Any/object type")
        if args.vararg and args.vararg.annotation and _contains_banned_annotation(args.vararg.annotation):
            self._record(args.vararg, "*args annotation uses banned Any/object type")
        if args.kwarg and args.kwarg.annotation and _contains_banned_annotation(args.kwarg.annotation):
            self._record(args.kwarg, "**kwargs annotation uses banned Any/object type")


def _contains_banned_annotation(node: ast.AST) -> bool:
    """Return ``True`` when *node* references a banned annotation."""

    if isinstance(node, ast.Name):
        return node.id in _BANNED_NAMES
    if isinstance(node, ast.Attribute):
        dotted = _attribute_to_name(node)
        return dotted in _BANNED_QUALIFIED
    if isinstance(node, ast.Subscript):
        return _contains_banned_annotation(node.value) or _contains_banned_annotation(node.slice)
    if isinstance(node, ast.Tuple):
        return any(_contains_banned_annotation(elt) for elt in node.elts)
    if hasattr(ast, "Constant") and isinstance(node, ast.Constant):
        return False
    for child in ast.iter_child_nodes(node):
        if _contains_banned_annotation(child):
            return True
    return False


def _attribute_to_name(node: ast.Attribute) -> str:
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return ".".join(parts)


__all__ = ["run_typing_linter"]
