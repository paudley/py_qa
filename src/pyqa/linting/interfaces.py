# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Phase-9 linter enforcing interface-first imports and DI construction rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover
    from pyqa.cli.commands.lint.preparation import PreparedLintState
else:  # pragma: no cover
    PreparedLintState = object

from ._ast_visitors import BaseAstLintVisitor, VisitorMetadata, run_ast_linter
from ._module_utils import module_name_from_path
from .base import InternalLintReport

_INTERFACES_PREFIX: Final[str] = "pyqa.interfaces"
_ALLOWED_INTERFACE_IMPORTS: Final[dict[str, set[str]]] = {
    "pyqa.analysis.bootstrap": {"pyqa.analysis", "pyqa.analysis.annotations", "pyqa.analysis.treesitter"},
    "pyqa.linting.docstrings": {
        "pyqa.analysis.spacy",
        "pyqa.analysis.treesitter",
        "pyqa.analysis.treesitter.grammars",
        "pyqa.analysis.treesitter.resolver",
    },
    "pyqa.cli.commands.install.command": {"pyqa.runtime.installers"},
    "pyqa.cli.commands.update.command": {"pyqa.runtime.installers.update"},
    "pyqa.cli.commands.lint.reporting": {
        "pyqa.reporting",
        "pyqa.reporting.output.highlighting",
        "pyqa.reporting.presenters.emitters",
    },
    "pyqa.cli.commands.lint.runtime": {
        "pyqa.analysis.bootstrap",
        "pyqa.orchestration.orchestrator",
        "pyqa.orchestration.runtime",
    },
    "pyqa.reporting.advice.builder": {"pyqa.analysis.services"},
    "pyqa.reporting.output.highlighting": {"pyqa.analysis"},
    "pyqa.reporting.presenters.emitters": {"pyqa.analysis.annotations"},
    "pyqa.runtime.installers.bootstrap": {"pyqa.runtime"},
}
_ALLOWED_INTERFACE_PACKAGES: Final[set[str]] = {
    "pyqa.analysis.bootstrap",
    "pyqa.cli.commands.doctor.command",
    "pyqa.runtime.installers.bootstrap",
    "pyqa.orchestration.orchestrator",
    "pyqa.orchestration.runtime",
}
_BANNED_CONCRETE_PREFIXES: Final[tuple[str, ...]] = (
    "pyqa.analysis",
    "pyqa.reporting",
    "pyqa.runtime",
    "pyqa.orchestration",
)
_BANNED_CONSTRUCTORS: Final[tuple[str, ...]] = (
    "TreeSitterContextResolver",
    "AnnotationEngine",
)
_ALLOWED_CONSTRUCTOR_MODULES: Final[set[str]] = {
    "pyqa.analysis.bootstrap",
    "pyqa.cli.commands.doctor.command",
}


def run_pyqa_interface_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool = True,
) -> InternalLintReport:
    """Enforce interface-centric imports and flag banned constructors.

    Args:
        state: Prepared lint execution context provided by the CLI.
        emit_to_logger: Backwards compatible flag ignored by the new pipeline.

    Returns:
        Report describing interface and constructor violations.
    """

    _ = emit_to_logger
    metadata = VisitorMetadata(tool="pyqa-interfaces", code="pyqa:interfaces")
    return run_ast_linter(
        state,
        metadata=metadata,
        visitor_factory=lambda path, st, meta: _InterfaceVisitor(path, st, meta),
        file_filter=_should_visit_file,
    )


@dataclass(slots=True)
class _ImportViolation:
    """Represent a detected import that violates interface rules."""

    imported: str
    message: str


class _InterfaceVisitor(BaseAstLintVisitor):
    """AST visitor that audits imports and constructor usage."""

    def __init__(self, path, state, metadata):  # type: ignore[override] suppression_valid: Visitor subclasses must accept the broader NodeVisitor parameters even though typing narrows them downstream.
        super().__init__(path, state, metadata)
        self._module = module_name_from_path(path, state.options.target_options.root)

    # --- Import handling -----------------------------------------------------------------

    def visit_import(self, node: ast.Import) -> None:  # noqa: D401 suppression_valid: NodeVisitor API contract supplies the visitor docstring; duplicating it here would add no clarity.
        for alias in node.names:
            target = alias.name
            violation = self._check_import_target(target)
            if violation is not None:
                self.record_issue(node, violation.message)
        self.generic_visit(node)

    def visit_import_from(self, node: ast.ImportFrom) -> None:  # noqa: D401 suppression_valid: Method inherits NodeVisitor semantics; an inline docstring would repeat the inherited contract.
        target = node.module
        if node.level:
            target = self._resolve_relative_module(target, node.level)
        if target is None:
            return
        violation = self._check_import_target(target)
        if violation is not None:
            self.record_issue(node, violation.message)
        self.generic_visit(node)

    def _resolve_relative_module(self, module: str | None, level: int) -> str | None:
        """Resolve a relative import against the current module."""

        parts = self._module.split(".")[:-1]
        if level > len(parts) + 1:
            return None
        resolved_parts = parts[: len(parts) + 1 - level]
        if module:
            resolved_parts.extend(module.split("."))
        return ".".join(resolved_parts) if resolved_parts else None

    def _check_import_target(self, target: str) -> _ImportViolation | None:
        """Return a violation when ``target`` imports a concrete implementation."""

        if target.startswith(_INTERFACES_PREFIX):
            return None
        if not target.startswith("pyqa."):
            return None
        if self._shares_domain(target):
            return None
        if self._is_allowed_concrete_import(target):
            return None
        if target.startswith(_BANNED_CONCRETE_PREFIXES):
            return _ImportViolation(
                imported=target,
                message=(
                    f"Import '{target}' must use the matching pyqa.interfaces module instead of the"
                    " concrete implementation"
                ),
            )
        return None

    def _is_allowed_concrete_import(self, target: str) -> bool:
        """Return ``True`` when ``target`` is allow-listed for concrete imports."""

        if self._module in _ALLOWED_INTERFACE_PACKAGES:
            return True
        allowed_targets = _ALLOWED_INTERFACE_IMPORTS.get(self._module)
        if allowed_targets is not None:
            return any(target.startswith(prefix) for prefix in allowed_targets)
        return False

    def _shares_domain(self, target: str) -> bool:
        """Return ``True`` when ``target`` resides in the same domain package."""

        module_parts = self._module.split(".")
        target_parts = target.split(".")
        if len(module_parts) < 2 or len(target_parts) < 2:
            return True
        module_domain = ".".join(module_parts[:2])
        target_domain = ".".join(target_parts[:2])
        return module_domain == target_domain

    # --- Constructor bans ----------------------------------------------------------------

    def visit_call(self, node: ast.Call) -> None:  # noqa: D401 suppression_valid: Call visitor adheres to NodeVisitor API and its behaviour is fully described by the base class.
        fully_qualified = _call_qualifier(node.func)
        if fully_qualified is None:
            self.generic_visit(node)
            return
        if fully_qualified.split(".")[-1] in _BANNED_CONSTRUCTORS and self._module not in _ALLOWED_CONSTRUCTOR_MODULES:
            self.record_issue(
                node,
                (f"Constructor '{fully_qualified}' may only be used in designated composition" " modules"),
            )
        self.generic_visit(node)


def _call_qualifier(func: ast.AST) -> str | None:
    """Return dotted name for ``func`` if it can be resolved statically."""

    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = []
        current: ast.AST | None = func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    return None


def _should_visit_file(path: Path) -> bool:
    """Return ``True`` when ``path`` is outside traditional test directories."""

    return "tests" not in {part.lower() for part in path.parts}


__all__ = ["run_pyqa_interface_linter"]
