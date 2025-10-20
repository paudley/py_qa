# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Phase-9 linter enforcing interface-first imports and DI construction rules."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final, cast

from pyqa.cli.commands.lint.preparation import PreparedLintState

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
_PATH_SEGMENT_DOMAIN_LIMIT: Final[int] = 2
_BANNED_CONSTRUCTORS: Final[tuple[str, ...]] = (
    "TreeSitterContextResolver",
    "AnnotationEngine",
)
_ALLOWED_CONSTRUCTOR_MODULES: Final[set[str]] = {
    "pyqa.analysis.bootstrap",
    "pyqa.cli.commands.doctor.command",
}
_EXCLUDED_TEST_PARTS: Final[frozenset[str]] = frozenset({"tests"})
_EXCLUDED_INTERNAL_PARTS: Final[tuple[frozenset[str], ...]] = (frozenset({"pyqa", "linting"}),)
_ALL_EXPORT_NAME: Final[str] = "__all__"
_ALLOWED_TYPING_SUBSCRIPTS: Final[frozenset[str]] = frozenset(
    {"Literal", "Final", "Annotated", "Union", "Optional", "Tuple"}
)
_ALLOWED_SIMPLE_NAME_LITERALS: Final[frozenset[str]] = frozenset({"None", "True", "False"})
_CONCRETE_CALL_EXCLUSIONS: Final[frozenset[str]] = frozenset({"tuple", "frozenset", "literal"})
_CAST_FUNCTION_NAME: Final[str] = "cast"
_CONSTRUCTOR_VIOLATION_MESSAGE: Final[str] = (
    "Constructor '{fully_qualified}' may only be used in designated composition modules"
)


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
    """Return an interface visitor instance bound to ``path``.

    Args:
        path: File system path of the module under inspection.
        state: Prepared lint state constructed by the CLI layer.
        metadata: Lint visitor metadata describing the active tool.

    Returns:
        _InterfaceVisitor: Visitor prepared to analyse the module.
    """

    return _InterfaceVisitor(path, state, metadata)


class _InterfaceVisitor(BaseAstLintVisitor):
    """AST visitor that audits imports and constructor usage."""

    _HANDLER_NAMES: ClassVar[dict[type[ast.AST], str]] = {
        ast.FunctionDef: "_handle_function_definition",
        ast.AsyncFunctionDef: "_handle_async_function_definition",
        ast.ClassDef: "_handle_class_definition",
        ast.Assign: "_handle_assignment",
        ast.AnnAssign: "_handle_annotated_assignment",
        ast.Import: "_handle_import",
        ast.ImportFrom: "_handle_from_import",
        ast.Call: "_handle_call",
    }

    def __init__(self, path: Path, state: PreparedLintState, metadata: VisitorMetadata) -> None:
        """Initialise module metadata used during linting.

        Args:
            path: File system path of the module under inspection.
            state: Prepared lint state constructed by the CLI layer.
            metadata: Lint visitor metadata describing the active tool.
        """

        super().__init__(path, state, metadata)
        self._module = module_name_from_path(path, state.options.target_options.root)
        parts = self._module.split(".") if self._module else []
        self._namespace_root = parts[0] if parts else ""
        self._namespace_prefix = f"{self._namespace_root}." if self._namespace_root else ""
        self._banned_concrete_prefixes = tuple(f"{self._namespace_root}.{suffix}" for suffix in _BANNED_DOMAIN_SUFFIXES)
        self._is_interface_module = _is_interface_module_name(self._module)
        self._class_stack: list[str] = []

    def visit(self, node: ast.AST) -> None:
        """Dispatch ``node`` to specialised handlers where required.

        Args:
            node: AST node currently visited by the walker.
        """

        if self._try_handle_node(node):
            return
        super().visit(node)

    def _try_handle_node(self, node: ast.AST) -> bool:
        """Return ``True`` when ``node`` is handled by a specialised method.

        Args:
            node: AST node currently visited by the walker.

        Returns:
            bool: ``True`` when a specific handler processed the node.
        """

        handler_name = self._HANDLER_NAMES.get(type(node))
        if handler_name is None:
            return False
        handler = cast(Callable[[ast.AST], None], getattr(self, handler_name))
        handler(node)
        return True

    def _handle_function_definition(self, node: ast.FunctionDef) -> None:
        """Inspect top-level function definitions for interface violations.

        Args:
            node: Function definition node encountered during traversal.
        """

        if self._is_interface_module and not self._class_stack:
            self._record_concrete_symbol(node, "function")
        self.generic_visit(node)

    def _handle_async_function_definition(self, node: ast.AsyncFunctionDef) -> None:
        """Inspect top-level async function definitions for interface violations.

        Args:
            node: Async function definition node encountered during traversal.
        """

        if self._is_interface_module and not self._class_stack:
            self._record_concrete_symbol(node, "async function")
        self.generic_visit(node)

    def _handle_class_definition(self, node: ast.ClassDef) -> None:
        """Inspect class definitions and track nested scope state.

        Args:
            node: Class definition node encountered during traversal.
        """

        is_interface = self._is_interface_module and not _is_allowed_interface_class(node)
        self._class_stack.append(node.name)
        if is_interface:
            self._record_concrete_symbol(node, "class")
        self.generic_visit(node)
        self._class_stack.pop()

    def _handle_assignment(self, node: ast.Assign) -> None:
        """Inspect assignments within interface modules for concretion.

        Args:
            node: Assignment node encountered during traversal.
        """

        if self._is_interface_module and not self._class_stack and _is_concrete_expression(node.value):
            self._record_concrete_symbol(node, "assignment")
        self.generic_visit(node)

    def _handle_annotated_assignment(self, node: ast.AnnAssign) -> None:
        """Inspect annotated assignments within interface modules for concretion.

        Args:
            node: Annotated assignment node encountered during traversal.
        """

        if self._is_interface_module and not self._class_stack and _is_concrete_expression(node.value):
            self._record_concrete_symbol(node, "assignment")
        self.generic_visit(node)

    def _handle_import(self, node: ast.Import) -> None:
        """Inspect import statements to guard against concrete dependencies.

        Args:
            node: Import node encountered during traversal.
        """

        for alias in node.names:
            violation = self._check_import_target(alias.name)
            if violation is not None:
                self.record_issue(node, violation.message)
        self.generic_visit(node)

    def _handle_from_import(self, node: ast.ImportFrom) -> None:
        """Inspect ``from`` import statements to guard against concrete dependencies.

        Args:
            node: ``from`` import node encountered during traversal.
        """

        target = node.module
        if node.level:
            target = self._resolve_relative_module(target, node.level)
        if target is None:
            return
        violation = self._check_import_target(target)
        if violation is not None:
            self.record_issue(node, violation.message)
        self.generic_visit(node)

    def _handle_call(self, node: ast.Call) -> None:
        """Inspect constructor calls to prevent instantiating concrete services.

        Args:
            node: Call expression node encountered during traversal.
        """

        fully_qualified = _call_qualifier(node.func)
        if fully_qualified is not None:
            if (
                fully_qualified.split(".")[-1] in _BANNED_CONSTRUCTORS
                and self._module not in _ALLOWED_CONSTRUCTOR_MODULES
            ):
                self.record_issue(
                    node,
                    _CONSTRUCTOR_VIOLATION_MESSAGE.format(fully_qualified=fully_qualified),
                )
        self.generic_visit(node)

    def _resolve_relative_module(self, module: str | None, level: int) -> str | None:
        """Resolve a relative import against the current module.

        Args:
            module: Module path referenced by the import.
            level: Relative import level derived from leading periods.

        Returns:
            str | None: Resolved absolute module path, when available.
        """

        parts = self._module.split(".")[:-1]
        if level > len(parts) + 1:
            return None
        resolved_parts = parts[: len(parts) + 1 - level]
        if module:
            resolved_parts.extend(module.split("."))
        return ".".join(resolved_parts) if resolved_parts else None

    def _check_import_target(self, target: str) -> _ImportViolation | None:
        """Return a violation when ``target`` imports a concrete implementation.

        Args:
            target: Module name referenced by the import.

        Returns:
            _ImportViolation | None: Violation describing the import issue.
        """

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
        """Return ``True`` when ``target`` is allow-listed for concrete imports.

        Args:
            target: Module name referenced by the import.

        Returns:
            bool: ``True`` when the import is explicitly allowed.
        """

        if self._module in _ALLOWED_INTERFACE_PACKAGES:
            return True
        allowed_targets = _ALLOWED_INTERFACE_IMPORTS.get(self._module)
        if allowed_targets is not None:
            return any(target.startswith(prefix) for prefix in allowed_targets)
        return False

    def _shares_domain(self, target: str) -> bool:
        """Return ``True`` when ``target`` resides in the same domain package.

        Args:
            target: Module name referenced by the import.

        Returns:
            bool: ``True`` when the module shares the same first two path segments.
        """

        module_parts = self._module.split(".")
        target_parts = target.split(".")
        if len(module_parts) < _PATH_SEGMENT_DOMAIN_LIMIT or len(target_parts) < _PATH_SEGMENT_DOMAIN_LIMIT:
            return True
        module_domain = ".".join(module_parts[:_PATH_SEGMENT_DOMAIN_LIMIT])
        target_domain = ".".join(target_parts[:_PATH_SEGMENT_DOMAIN_LIMIT])
        return module_domain == target_domain

    def _record_concrete_symbol(self, node: ast.AST, symbol_kind: str) -> None:
        """Record an issue when a concrete symbol exists within an interface module.

        Args:
            node: AST node defining the symbol.
            symbol_kind: High-level description of the symbol (e.g. function).
        """

        symbol = getattr(node, "name", None)
        if symbol == _ALL_EXPORT_NAME:
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
    """Return dotted name for ``func`` if it can be resolved statically.

    Args:
        func: Call target whose qualified name should be derived.

    Returns:
        str | None: Dotted name or ``None`` when the name cannot be derived.
    """

    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = _collect_attribute_parts(func)
        return ".".join(parts) if parts else None
    return None


def _is_interface_module_name(name: str | None) -> bool:
    """Return ``True`` when ``name`` denotes a module within an interfaces package.

    Args:
        name: Candidate module name extracted from the AST.

    Returns:
        bool: ``True`` when the module path includes the interfaces segment.
    """

    if not name:
        return False
    return _INTERFACES_KEYWORD in name.split(".")


def _should_visit_file(path: Path) -> bool:
    """Return ``True`` when ``path`` is outside traditional test directories.

    Args:
        path: File path bound to the module currently under inspection.

    Returns:
        bool: ``True`` when the visitor should analyse the file.
    """

    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & _EXCLUDED_TEST_PARTS:
        return False
    return not any(group.issubset(lowered_parts) for group in _EXCLUDED_INTERNAL_PARTS)


def _is_allowed_interface_class(node: ast.ClassDef) -> bool:
    """Return ``True`` when ``node`` resembles an abstract or protocol class.

    Args:
        node: Class definition node encountered in an interfaces module.

    Returns:
        bool: ``True`` when the class satisfies abstract structure requirements.
    """

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
    """Return ``True`` when ``expr`` denotes a concrete implementation detail.

    Args:
        expr: Expression node found in an interfaces module.

    Returns:
        bool: ``True`` when the expression represents concrete state.
    """

    if expr is None:
        return False
    result = False
    if isinstance(expr, ast.Subscript):
        result = _is_non_literal_subscript(expr)
    elif isinstance(expr, ast.Call):
        result = _is_concrete_call(expr)
    elif isinstance(expr, (ast.Attribute, ast.Lambda)):
        result = True
    elif isinstance(expr, ast.Name):
        result = expr.id not in _ALLOWED_SIMPLE_NAME_LITERALS
    else:
        container_elements = _container_elements(expr)
        if container_elements:
            result = any(_is_concrete_expression(element) for element in container_elements)
        elif isinstance(expr, ast.Dict):
            result = any(_is_concrete_expression(value) for value in expr.values)
        elif isinstance(expr, ast.JoinedStr):
            result = any(_is_concrete_expression(value) for value in expr.values)
    return result


def _is_non_literal_subscript(expr: ast.Subscript) -> bool:
    """Return ``True`` when the subscript expression denotes a concrete value.

    Args:
        expr: Subscription expression to assess.

    Returns:
        bool: ``True`` when the subscription references a concrete type.
    """

    base_name = _qualify_expr(expr.value)
    return base_name.split(".")[-1] not in _ALLOWED_TYPING_SUBSCRIPTS


def _is_concrete_call(expr: ast.Call) -> bool:
    """Return ``True`` when the call expression constructs a concrete value.

    Args:
        expr: Call expression encountered within the AST.

    Returns:
        bool: ``True`` when the call constructs concrete runtime behaviour.
    """

    func_name = _qualify_expr(expr.func)
    simple_name = func_name.split(".")[-1]
    if simple_name == _CAST_FUNCTION_NAME:
        return any(_is_concrete_expression(arg) for arg in expr.args[1:])
    if simple_name in _CONCRETE_CALL_EXCLUSIONS:
        return False
    return True


def _container_elements(expr: ast.AST) -> tuple[ast.AST, ...]:
    """Return contained expression elements for literal container nodes.

    Args:
        expr: Expression encountered within the AST.

    Returns:
        tuple[ast.AST, ...]: Child expressions contained by the node.
    """

    if isinstance(expr, ast.List):
        return tuple(expr.elts)
    if isinstance(expr, ast.Tuple):
        return tuple(expr.elts)
    if isinstance(expr, ast.Set):
        return tuple(expr.elts)
    return ()


def _collect_attribute_parts(node: ast.AST) -> tuple[str, ...]:
    """Return the attribute chain represented by ``node``.

    Args:
        node: Attribute expression whose dotted name should be derived.

    Returns:
        tuple[str, ...]: Attribute tokens ordered from root to leaf.
    """

    if isinstance(node, ast.Attribute):
        return (*_collect_attribute_parts(node.value), node.attr)
    if isinstance(node, ast.Name):
        return (node.id,)
    return ()


def _qualify_expr(node: ast.AST) -> str:
    """Return a dotted identifier for ``node`` when it can be derived.

    Args:
        node: Expression whose dotted identifier should be resolved.

    Returns:
        str: Qualified name or an empty string if resolution fails.
    """

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = _collect_attribute_parts(node)
        return ".".join(parts) if parts else ""
    if isinstance(node, ast.Call):
        return _qualify_expr(node.func)
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError, TypeError):  # pragma: no cover - resilience for Python AST edge cases.
        return ""


__all__ = ["run_pyqa_interface_linter"]
