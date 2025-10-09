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

_ALLOWED_SERVICE_REGISTERERS: Final[frozenset[str]] = frozenset({
    "pyqa.core.runtime.di",
    "pyqa.analysis.bootstrap",
})
_ALLOWED_SERVICE_SUFFIXES: Final[tuple[str, ...]] = (".bootstrap",)
_ALLOWED_SERVICE_REGISTERERS_DISPLAY: Final[str] = ", ".join(
    (*sorted(_ALLOWED_SERVICE_REGISTERERS), "*bootstrap modules"),
)
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
            if not self._is_allowed_module():
                service_label = self._describe_service(node)
                message = (
                    f"Service '{service_label}' registered from '{self._module}' "
                    f"must move into an approved composition root ({_ALLOWED_SERVICE_REGISTERERS_DISPLAY})."
                )
                hints = self._service_hints(service_label)
                self.record_issue(
                    node,
                    message,
                    hints=hints,
                    meta={
                        "service": service_label,
                        "module": self._module,
                        "allowed_roots": sorted(_ALLOWED_SERVICE_REGISTERERS),
                        "allowed_suffixes": _ALLOWED_SERVICE_SUFFIXES,
                    },
                )
        self.generic_visit(node)

    def _is_service_registration(self, node: ast.Call) -> bool:
        """Return ``True`` for ServiceContainer.register style invocations."""

        if isinstance(node.func, ast.Attribute) and node.func.attr == "register":
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id in _SERVICE_CONTAINER_NAMES:
                return True
        return False

    def _is_allowed_module(self) -> bool:
        """Return ``True`` when the current module is an approved root."""

        if self._module in _ALLOWED_SERVICE_REGISTERERS:
            return True
        return any(self._module.endswith(suffix) for suffix in _ALLOWED_SERVICE_SUFFIXES)

    def _describe_service(self, node: ast.Call) -> str:
        """Return a human-friendly representation of the registered service."""

        if node.args:
            label = self._render_argument(node.args[0])
            if label:
                return label
        for keyword in node.keywords:
            if keyword.arg in {"name", "service", "interface"}:
                label = self._render_argument(keyword.value)
                if label:
                    return label
        return "unknown service"

    def _render_argument(self, arg: ast.AST) -> str:
        """Render ``arg`` as a readable literal or expression string."""

        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        if isinstance(arg, ast.Name):
            return arg.id
        try:
            return ast.unparse(arg)
        except Exception:  # pragma: no cover - ast.unparse best-effort fall back.
            return ast.dump(arg, annotate_fields=False)

    def _service_hints(self, service_label: str) -> tuple[str, ...]:
        """Return actionable hints encouraging proper DI configuration."""

        suffix_text = " or a module ending with '.bootstrap'" if _ALLOWED_SERVICE_SUFFIXES else ""
        return (
            f"Move '{service_label}' registration into pyqa.core.runtime.di{suffix_text}.",
            "Extend pyqa.di.CompositionRegistry or add a dedicated package bootstrap when a new root is justified.",
            "Use pyqa.app.di.configure_services or test DI fixtures instead of ad-hoc container wiring.",
        )


__all__ = ["run_pyqa_di_linter"]
