# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Phase-9 linter enforcing dependency injection composition rules."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from pyqa.cli.commands.lint.preparation import PreparedLintState
else:  # pragma: no cover - runtime hinting only
    PreparedLintState = object

from ._ast_visitors import BaseAstLintVisitor, VisitorMetadata, run_ast_linter
from ._module_utils import module_name_from_path
from .base import InternalLintReport

_ALLOWED_SERVICE_REGISTERERS: Final[set[str]] = {
    "pyqa.analysis.bootstrap",
    "pyqa.runtime.installers.bootstrap",
    "pyqa.runtime.console.bootstrap",
}
_SERVICE_CONTAINER_NAMES: Final[frozenset[str]] = frozenset({"ServiceContainer", "container"})


def run_pyqa_di_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool = True,
) -> InternalLintReport:
    """Report DI violations such as rogue service registration.

    Args:
        state: Prepared lint execution context.
        emit_to_logger: Historical compatibility flag (unused).

    Returns:
        Internal lint report describing DI violations.
    """

    _ = emit_to_logger
    metadata = VisitorMetadata(tool="pyqa-di", code="pyqa:di")
    return run_ast_linter(
        state,
        metadata=metadata,
        visitor_factory=lambda path, st, meta: _DiVisitor(path, st, meta),
    )


class _DiVisitor(BaseAstLintVisitor):
    """Visitor detecting DI rule violations."""

    def __init__(self, path, state, metadata):  # type: ignore[override] suppression_valid: Visitor signature must match NodeVisitor even when typing narrows parameters.
        super().__init__(path, state, metadata)
        self._module = module_name_from_path(path, state.options.target_options.root)

    def visit_call(self, node: ast.Call) -> None:  # noqa: D401 suppression_valid: NodeVisitor API requires this signature; additional docstring would duplicate inherited documentation.
        if self._is_service_registration(node):
            if self._module not in _ALLOWED_SERVICE_REGISTERERS:
                self.record_issue(
                    node,
                    "Service registration must occur in approved composition roots",
                )
        self.generic_visit(node)

    def _is_service_registration(self, node: ast.Call) -> bool:
        """Return ``True`` for ServiceContainer.register style invocations."""

        if isinstance(node.func, ast.Attribute) and node.func.attr == "register":
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id in _SERVICE_CONTAINER_NAMES:
                return True
        return False


__all__ = ["run_pyqa_di_linter"]
