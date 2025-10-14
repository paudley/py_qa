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

_INTERFACES_KEYWORD: Final[str] = "interfaces"
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
        "pyqa.analysis.providers",
        "pyqa.reporting",
        "pyqa.reporting.output.highlighting",
        "pyqa.reporting.presenters.emitters",
    },
    "pyqa.cli.commands.lint.runtime": {
        "pyqa.analysis.bootstrap",
        "pyqa.orchestration.orchestrator",
        "pyqa.orchestration.runtime",
    },
    "pyqa.cli.commands.lint.command": {
        "pyqa.runtime.console.manager",
        "pyqa.orchestration.selection_context",
    },
    "pyqa.cli.commands.lint.fetch": {"pyqa.runtime.console.manager"},
    "pyqa.cli.commands.lint.progress": {"pyqa.runtime.console.manager"},
    "pyqa.cli.commands.lint.meta": {"pyqa.orchestration.selection_context"},
    "pyqa.reporting.advice.builder": {"pyqa.analysis.services", "pyqa.analysis.providers"},
    "pyqa.reporting.output.highlighting": {"pyqa.analysis", "pyqa.analysis.providers"},
    "pyqa.reporting.presenters.emitters": {"pyqa.analysis.annotations", "pyqa.analysis.providers"},
    "pyqa.reporting.presenters.formatters": {"pyqa.analysis.providers", "pyqa.runtime.console.manager"},
    "pyqa.reporting.presenters.stats": {"pyqa.runtime.console.manager"},
    "pyqa.reporting.advice.panels": {"pyqa.runtime.console.manager"},
    "pyqa.reporting.advice.refactor": {"pyqa.runtime.console.manager"},
    "pyqa.reporting.output.diagnostics": {"pyqa.core.logging.public", "pyqa.runtime.console.manager"},
    "pyqa.reporting.output.modes": {"pyqa.core.logging.public", "pyqa.runtime.console.manager"},
    "pyqa.runtime.installers.bootstrap": {"pyqa.runtime"},
    "pyqa.core.logging.public": {"pyqa.runtime.console.manager"},
    "pyqa.core.runtime.di": {"pyqa.runtime.console.manager"},
    "pyqa.diagnostics.core": {"pyqa.analysis.providers"},
}
_ALLOWED_INTERFACE_PACKAGES: Final[set[str]] = {
    "pyqa.analysis.bootstrap",
    "pyqa.cli.commands.doctor.command",
    "pyqa.runtime.installers.bootstrap",
    "pyqa.orchestration.orchestrator",
    "pyqa.orchestration.runtime",
    "pyqa.runtime.console.manager",
}
_BANNED_DOMAIN_SUFFIXES: Final[tuple[str, ...]] = (
    "analysis",
    "reporting",
    "runtime",
    "orchestration",
)
_ALLOWED_ABSTRACT_CLASS_SUFFIXES: Final[tuple[str, ...]] = (
    "Protocol",
    "ABC",
    "ABCMeta",
    "TypedDict",
    "Enum",
    "StrEnum",
)
_ALLOWED_CLASS_DECORATORS: Final[frozenset[str]] = frozenset(
    {
        "dataclass",
        "runtime_checkable",
        "unique",
        "final",
    }
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
        visitor_factory=_build_interface_visitor,
        file_filter=_should_visit_file,
    )


@dataclass(slots=True)
class _ImportViolation:
    """Represent a detected import that violates interface rules."""

    imported: str
    message: str


def _build_interface_visitor(
    path: Path,
    state: PreparedLintState,
    metadata: VisitorMetadata,
) -> _InterfaceVisitor:
    """Return an interface visitor instance bound to ``path``."""

    return _InterfaceVisitor(path, state, metadata)


class _InterfaceVisitor(BaseAstLintVisitor):
    """AST visitor that audits imports and constructor usage."""

    def __init__(self, path: Path, state: PreparedLintState, metadata: VisitorMetadata) -> None:
        """Initialise module metadata used during linting."""

        super().__init__(path, state, metadata)
        self._module = module_name_from_path(path, state.options.target_options.root)
        parts = self._module.split(".") if self._module else []
        self._namespace_root = parts[0] if parts else ""
        self._namespace_prefix = f"{self._namespace_root}." if self._namespace_root else ""
        self._banned_concrete_prefixes = tuple(f"{self._namespace_root}.{suffix}" for suffix in _BANNED_DOMAIN_SUFFIXES)
        self._is_interface_module = _is_interface_module_name(self._module)
        self._class_stack: list[str] = []

    # --- Interface concretion detection --------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: D401 suppression_valid
        if self._is_interface_module and not self._class_stack:
            self._record_concrete_symbol(node, "function")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: D401 suppression_valid
        if self._is_interface_module and not self._class_stack:
            self._record_concrete_symbol(node, "async function")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: D401 suppression_valid
        is_interface = self._is_interface_module and not _is_allowed_interface_class(node)
        self._class_stack.append(node.name)
        if is_interface:
            self._record_concrete_symbol(node, "class")
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: D401 suppression_valid
        if self._is_interface_module and not self._class_stack and _is_concrete_expression(node.value):
            self._record_concrete_symbol(node, "assignment")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: D401 suppression_valid
        if self._is_interface_module and not self._class_stack and _is_concrete_expression(node.value):
            self._record_concrete_symbol(node, "assignment")
        self.generic_visit(node)

    # --- Import handling -----------------------------------------------------------------

    def visit_import(self, node: ast.Import) -> None:  # noqa: D401 suppression_valid
        for alias in node.names:
            target = alias.name
            violation = self._check_import_target(target)
            if violation is not None:
                self.record_issue(node, violation.message)
        self.generic_visit(node)

    def visit_import_from(self, node: ast.ImportFrom) -> None:  # noqa: D401 suppression_valid
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

        if _is_interface_module_name(target):
            return None
        if not self._namespace_prefix or not target.startswith(self._namespace_prefix):
            return None
        if self._shares_domain(target):
            return None
        if self._is_allowed_concrete_import(target):
            return None
        if target.startswith(self._banned_concrete_prefixes):
            return _ImportViolation(
                imported=target,
                message=(
                    f"Import '{target}' must use the matching interfaces module instead of the"
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

    def _record_concrete_symbol(self, node: ast.AST, symbol_kind: str) -> None:
        symbol = getattr(node, "name", None)
        if symbol == "__all__":
            return
        name_part = f" '{symbol}'" if symbol else ""
        message = f"Interfaces module '{self._module}' must not define concrete {symbol_kind}{name_part}"
        hints = (
            "Limit interfaces packages to Protocols, TypedDicts, dataclasses, and literals.",
            "Move concrete logic into the owning runtime/orchestration module and expose Protocols here only.",
        )
        self.record_issue(
            node,
            message,
            hints=hints,
            meta={
                "module": self._module,
                "symbol": symbol,
                "violation": "concrete-interface",
                "symbol_kind": symbol_kind,
            },
        )


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


def _is_interface_module_name(name: str | None) -> bool:
    """Return ``True`` when ``name`` denotes a module within an interfaces package."""

    if not name:
        return False
    return _INTERFACES_KEYWORD in name.split(".")


def _should_visit_file(path: Path) -> bool:
    """Return ``True`` when ``path`` is outside traditional test directories."""

    lowered_parts = {part.lower() for part in path.parts}
    if "tests" in lowered_parts:
        return False
    if "pyqa" in lowered_parts and "linting" in lowered_parts:
        return False
    return True


def _is_allowed_interface_class(node: ast.ClassDef) -> bool:
    base_names = {_qualify_expr(base) for base in node.bases}
    if any(name.endswith(_ALLOWED_ABSTRACT_CLASS_SUFFIXES) for name in base_names if name):
        return True
    if any(name and name.split(".")[-1] in {"Exception", "RuntimeError", "Error"} for name in base_names if name):
        return True
    decorator_names = {_qualify_expr(deco) for deco in node.decorator_list}
    if any(name and name.split(".")[-1] in _ALLOWED_CLASS_DECORATORS for name in decorator_names):
        return True
    return False


def _is_concrete_expression(expr: ast.AST | None) -> bool:
    if expr is None:
        return False
    if isinstance(expr, ast.Subscript):
        base_name = _qualify_expr(expr.value)
        if base_name.split(".")[-1] in {"Literal", "Final", "Annotated", "Union", "Optional", "Tuple"}:
            return False
        return True
    if isinstance(expr, ast.Call):
        func_name = _qualify_expr(expr.func)
        simple_name = func_name.split(".")[-1]
        if simple_name in {"cast", "tuple", "frozenset", "literal"}:
            return any(_is_concrete_expression(arg) for arg in expr.args[1:]) if simple_name == "cast" else False
        return True
    if isinstance(expr, (ast.Attribute, ast.Lambda)):
        return True
    if isinstance(expr, ast.Name):
        return expr.id not in {"None", "True", "False"}
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        return any(_is_concrete_expression(element) for element in expr.elts)
    if isinstance(expr, ast.Dict):
        return any(_is_concrete_expression(value) for value in expr.values)
    if isinstance(expr, ast.JoinedStr):
        return any(_is_concrete_expression(value) for value in expr.values)
    return False


def _qualify_expr(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        current: ast.AST | None = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    if isinstance(node, ast.Call):
        return _qualify_expr(node.func)
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - resilience for Python AST edge cases.
        return ""


__all__ = ["run_pyqa_interface_linter"]
