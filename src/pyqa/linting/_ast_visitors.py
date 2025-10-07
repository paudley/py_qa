# SPDX-License-Identifier: MIT
"""Shared AST visitor utilities for internal linters."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.core.models import Diagnostic, ToolExitCategory, ToolOutcome
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport
from .utils import collect_python_files


@dataclass(frozen=True)
class VisitorMetadata:
    """Metadata describing tool identity for AST visitors."""

    tool: str
    code: str
    severity: Severity = Severity.WARNING


_VISIT_METHOD_NAME: Final[str] = "visit"


def _dispatch_alias(name: str) -> str:
    """Return the CamelCase dispatch name used by ``ast.NodeVisitor``.

    Args:
        name: Original snake_case visitor name (e.g. ``visit_import_from``).

    Returns:
        The camel-cased variant required for ``NodeVisitor`` dispatch
        (``visit_ImportFrom`` for the previous example).
    """

    prefix, _, remainder = name.partition("_")
    if not remainder:
        return name
    camel = "".join(part.capitalize() for part in remainder.split("_"))
    return f"{prefix}_{camel}"


class BaseAstLintVisitor(ast.NodeVisitor):
    """Common functionality for AST-based internal lint visitors."""

    def __init_subclass__(cls) -> None:
        """Create CamelCase aliases so subclasses can stay lint-friendly.

        ``ast.NodeVisitor`` expects dispatch methods like ``visit_ImportFrom``;
        pylint, however, insists on snake_case.  Subclasses can therefore define
        snake_case helpers (``visit_import_from``) and this hook mirrors them to
        the CamelCase names required by ``NodeVisitor`` while preserving custom
        implementations.
        """

        super().__init_subclass__()
        for attr, value in list(vars(cls).items()):
            if not callable(value) or not attr.startswith("visit_") or attr == _VISIT_METHOD_NAME:
                continue
            if any(ch.isupper() for ch in attr):
                continue
            alias = _dispatch_alias(attr)
            if not hasattr(cls, alias):
                setattr(cls, alias, value)

    def __init__(self, path: Path, state: PreparedLintState, metadata: VisitorMetadata) -> None:
        self._path = path
        self._state = state
        self._metadata = metadata
        self.diagnostics: list[Diagnostic] = []
        self.stdout: list[str] = []

    def record_issue(self, node: ast.AST, message: str) -> None:
        """Append a diagnostic and stdout entry anchored to ``node``.

        Args:
            node: AST node responsible for triggering the diagnostic.
            message: Human-readable description of the lint failure.
        """

        normalized = normalize_path_key(self._path, base_dir=self._state.root)
        line = getattr(node, "lineno", 1)
        diagnostic = Diagnostic(
            file=normalized,
            line=line,
            column=getattr(node, "col_offset", None),
            severity=self._metadata.severity,
            message=message,
            tool=self._metadata.tool,
            code=self._metadata.code,
        )
        self.diagnostics.append(diagnostic)
        self.stdout.append(f"{normalized}:{line}: {message}")


def run_ast_linter(
    state: PreparedLintState,
    *,
    metadata: VisitorMetadata,
    visitor_factory: Callable[[Path, PreparedLintState, VisitorMetadata], BaseAstLintVisitor],
    parse_error_handler: Callable[[Path, SyntaxError], str] | None = None,
) -> InternalLintReport:
    """Execute an AST-based internal linter.

    Args:
        state: Prepared lint context providing root paths and configuration.
        metadata: Descriptor describing the tool identity and diagnostic code.
        visitor_factory: Callable that creates a concrete visitor for a file.
        parse_error_handler: Optional callable emitting a message when a file
            fails to parse; returning the rendered warning for stdout.

    Returns:
        ``InternalLintReport`` capturing diagnostics, stdout, and the scanned
        file set so the orchestrator can merge the result into the standard
        tooling pipeline.
    """

    files = collect_python_files(state)
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []

    for file_path in files:
        source = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            if parse_error_handler is not None:
                stdout_lines.append(parse_error_handler(file_path, exc))
            continue
        visitor = visitor_factory(file_path, state, metadata)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)
        stdout_lines.extend(visitor.stdout)

    outcome = ToolOutcome(
        tool=metadata.tool,
        action="check",
        returncode=1 if diagnostics else 0,
        stdout=stdout_lines,
        stderr=[],
        diagnostics=diagnostics,
        exit_category=ToolExitCategory.DIAGNOSTIC if diagnostics else ToolExitCategory.SUCCESS,
    )
    return InternalLintReport(outcome=outcome, files=tuple(files))


__all__ = [
    "BaseAstLintVisitor",
    "VisitorMetadata",
    "run_ast_linter",
]
