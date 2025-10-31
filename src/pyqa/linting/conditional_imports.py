# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Detect conditional imports and recommend interface-driven abstractions."""

from __future__ import annotations

import ast
from enum import Enum
from pathlib import Path
from typing import Final

from pyqa.interfaces.linting import PreparedLintState

from ._ast_visitors import BaseAstLintVisitor, VisitorMetadata, run_ast_linter
from .base import InternalLintReport

DEFAULT_INTERFACES_ROOT: Final[str] = "src/pyqa/interfaces"
_MODULE_SCOPE_DEPTH: Final[int] = 2
_TYPE_CHECKING_SENTINEL: Final[str] = "TYPE_CHECKING"
_RELATIVE_PREFIX_SENTINEL: Final[str] = "."


class ImportKind(str, Enum):
    """Categorise whether a module import targets internal or external code."""

    INTERNAL = "internal"
    EXTERNAL = "external"


def _resolve_interfaces_hint(state: PreparedLintState) -> str | None:
    """Return the configured interfaces root relative to the repository.

    Args:
        state: Prepared lint state that may provide configuration metadata.

    Returns:
        str | None: Relative path to the interfaces module when configured; otherwise ``None``.
    """

    meta = getattr(state, "meta", None)
    candidate: str | Path | None = None
    if meta is not None:
        candidate = getattr(meta, "interfaces_root", None)
        if candidate is None and getattr(meta, "pyqa_rules", False):
            candidate = DEFAULT_INTERFACES_ROOT
    if candidate is None:
        default_path = state.root / DEFAULT_INTERFACES_ROOT
        if default_path.exists():
            candidate = DEFAULT_INTERFACES_ROOT
    if candidate is None:
        return None
    if isinstance(candidate, Path):
        if not candidate.is_absolute():
            candidate = state.root / candidate
        try:
            relative = candidate.relative_to(state.root)
        except ValueError:
            return str(candidate)
        return str(relative)
    return str(candidate)


def _discover_module_search_roots(state: PreparedLintState) -> tuple[Path, ...]:
    """Return directories that may contain importable modules for the repository.

    Args:
        state: Prepared lint state describing repository metadata.

    Returns:
        tuple[Path, ...]: Sorted tuple of candidate directories inspected for modules.
    """

    roots = _collect_base_roots(state.root)
    roots.update(_collect_target_roots(state))
    return tuple(sorted(roots))


def _collect_base_roots(base_root: Path) -> set[Path]:
    """Return root directories derived from the repository root.

    Args:
        base_root: Repository root directory discovered from the lint state.

    Returns:
        set[Path]: Existing directories that should be consulted for module discovery.
    """

    roots: set[Path] = set()
    if not base_root.exists():
        return roots
    try:
        resolved_root = base_root.resolve()
    except OSError:
        return roots
    roots.add(resolved_root)
    try:
        for entry in resolved_root.iterdir():
            if entry.is_dir():
                try:
                    roots.add(entry.resolve())
                except OSError:
                    continue
    except OSError:
        return roots
    return roots


def _collect_target_roots(state: PreparedLintState) -> set[Path]:
    """Return root directories derived from lint target options.

    Args:
        state: Lint state providing optional discovery metadata.

    Returns:
        set[Path]: Additional directories referenced by the lint options.
    """

    options = getattr(state, "options", None)
    target_options = getattr(options, "target_options", None) if options is not None else None
    if target_options is None:
        return set()
    roots: set[Path] = set()
    resolved_root = _resolve_existing_path(getattr(target_options, "root", None), treat_file_parent=False)
    if resolved_root is not None:
        roots.add(resolved_root)
    for path in getattr(target_options, "paths", ()):
        resolved_path = _resolve_existing_path(path, treat_file_parent=True)
        if resolved_path is not None:
            roots.add(resolved_path)
    for directory in getattr(target_options, "dirs", ()):
        resolved_dir = _resolve_existing_path(directory, treat_file_parent=False)
        if resolved_dir is not None:
            roots.add(resolved_dir)
    return roots


def _resolve_existing_path(value: object, *, treat_file_parent: bool) -> Path | None:
    """Return a resolved path for ``value`` when an existing directory is found.

    Args:
        value: Candidate path supplied by lint configuration.
        treat_file_parent: Flag indicating whether regular files should resolve to their parent directory.

    Returns:
        Path | None: Resolved directory path or ``None`` when the candidate does not exist.
    """

    if not isinstance(value, Path):
        return None
    candidate = value if value.is_dir() or not treat_file_parent else value.parent
    if not candidate.exists():
        return None
    try:
        return candidate.resolve()
    except OSError:
        return None


def run_conditional_import_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool = True,
) -> InternalLintReport:
    """Highlight imports executed outside module scope.

    Args:
        state: Prepared lint state describing the repository under analysis.
        emit_to_logger: Flag indicating whether stdout should be echoed to the CLI logger.

    Returns:
        InternalLintReport: Collected diagnostics and captured stdout for the run.
    """

    _ = emit_to_logger
    metadata = VisitorMetadata(
        tool="internal-conditional-imports",
        code="internal:conditional-import",
    )
    return run_ast_linter(
        state,
        metadata=metadata,
        visitor_factory=_ConditionalImportVisitor,
    )


class _ConditionalImportVisitor(BaseAstLintVisitor):
    """Record imports nested within control flow constructs or local scopes."""

    def __init__(self, path: Path, state: PreparedLintState, metadata: VisitorMetadata) -> None:
        """Initialise a visitor tracking ancestor nodes for ``path``.

        Args:
            path: File currently being analysed.
            state: Prepared lint state describing repository metadata.
            metadata: Descriptor of the linter emitting diagnostics.
        """

        super().__init__(path, state, metadata)
        self._node_stack: list[ast.AST] = []
        self._interfaces_hint = _resolve_interfaces_hint(state)
        self._has_interfaces_module = self._interfaces_hint is not None
        self._module_roots = _discover_module_search_roots(state)
        self._module_cache: dict[str, bool] = {}

    # The base class does not hook into visit dispatch, so we override `visit`
    # to push/pop the ancestor stack while delegating to the standard visitor.
    def visit(self, node: ast.AST) -> None:
        """Track ``node`` ancestry while deferring to `ast.NodeVisitor`.

        Args:
            node: AST node currently being visited.
        """

        self._node_stack.append(node)
        try:
            super().visit(node)
        finally:
            self._node_stack.pop()

    def visit_import(self, node: ast.Import) -> None:
        """Inspect import statements and flag conditional usage.

        Args:
            node: Import statement encountered in the syntax tree.
        """

        self._check_import(node)
        self.generic_visit(node)

    def visit_import_from(self, node: ast.ImportFrom) -> None:
        """Inspect from-import statements and flag conditional usage.

        Args:
            node: From-import statement encountered in the syntax tree.
        """

        self._check_import(node)
        self.generic_visit(node)

    def _check_import(self, node: ast.AST) -> None:
        """Record a diagnostic when ``node`` resides outside module scope.

        Args:
            node: Import statement subjected to lint validation.
        """

        if len(self._node_stack) < _MODULE_SCOPE_DEPTH:
            return
        parent = self._node_stack[-_MODULE_SCOPE_DEPTH]
        if isinstance(parent, ast.Module):
            return

        context = type(parent).__name__
        modules, display = self._extract_import_targets(node)
        import_kind = self._classify_import(modules, node)
        if import_kind is ImportKind.INTERNAL and not self._has_interfaces_module:
            return

        primary = display or (modules[0] if modules else "<unknown>")
        hints: list[str]
        if import_kind is ImportKind.INTERNAL:
            interfaces_hint = self._interfaces_hint or DEFAULT_INTERFACES_ROOT
            hints = [
                f"Define an abstract contract under {interfaces_hint} and inject the implementation.",
                "Move the import to module scope; conditional imports are forbidden in this project.",
            ]
            message = (
                f"Conditional import of internal module '{primary}' inside {context} is forbidden; "
                "replace it with an interface-based abstraction."
            )
        else:
            hints = [
                "Import the module at module scope so missing dependencies fail immediately.",
                "Do not defer optional dependency handling to runtime branches; fail fast during import.",
            ]
            message = (
                f"Conditional import of external module '{primary}' inside {context} is forbidden; "
                "module imports should not be conditional, fail early on missing modules."
            )
        if isinstance(parent, ast.If) and _uses_type_checking_guard(parent):
            hints.append("TYPE_CHECKING guards are banned; rely on interfaces rather than conditional imports.")

        self.record_issue(
            node,
            message,
            hints=hints,
            meta={
                "violation": "conditional-import",
                "context": context,
                "import_kind": import_kind.value,
                "targets": list(modules),
            },
        )

    def _extract_import_targets(self, node: ast.AST) -> tuple[list[str], str]:
        """Return module targets referenced by ``node`` alongside a display label.

        Args:
            node: Import statement encountered within the AST.

        Returns:
            tuple[list[str], str]: Pair containing the list of module names and a human-readable label.
        """

        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names if alias.name]
            display = ", ".join(modules)
            return modules, display
        if isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = _RELATIVE_PREFIX_SENTINEL * node.level
                module = node.module or ""
                if module:
                    target = f"{prefix}{module}"
                else:
                    names = [alias.name for alias in node.names if alias.name]
                    target = prefix + (names[0] if names else "")
                return [target], target
            module = node.module or ""
            modules = [module] if module else []
            display = module or ", ".join(alias.name for alias in node.names if alias.name)
            return modules, display
        return [], ""

    def _classify_import(self, modules: list[str], node: ast.AST) -> ImportKind:
        """Return the classification for the import statement represented by ``node``.

        Args:
            modules: Candidate module names extracted from the import statement.
            node: AST node describing the import syntax.

        Returns:
            ImportKind: Classification indicating whether the import targets internal or external modules.
        """

        if not modules:
            if isinstance(node, ast.ImportFrom) and getattr(node, "level", 0):
                return ImportKind.INTERNAL
            return ImportKind.EXTERNAL
        statuses = [self._is_internal_module(module) for module in modules]
        if statuses and all(statuses):
            return ImportKind.INTERNAL
        return ImportKind.EXTERNAL

    def _is_internal_module(self, module: str) -> bool:
        """Return whether ``module`` appears to reside inside the repository.

        Args:
            module: Dotted module path extracted from an import statement.

        Returns:
            bool: ``True`` when the module resolves to a package or module within the repository root.
        """

        cached = self._module_cache.get(module)
        if cached is not None:
            return cached
        if module.startswith(_RELATIVE_PREFIX_SENTINEL) or not module:
            self._module_cache[module] = True
            return True
        parts = [segment for segment in module.split(".") if segment]
        result = any(self._module_exists(root, parts) for root in self._module_roots)
        self._module_cache[module] = result
        return result

    def _module_exists(self, root: Path, parts: list[str]) -> bool:
        """Return whether ``parts`` resolves to a module or package beneath ``root``.

        Args:
            root: Directory considered as the root for module resolution.
            parts: Sequence of path components derived from the import name.

        Returns:
            bool: ``True`` when a corresponding module or package exists, otherwise ``False``.
        """

        if not parts:
            return False
        module_dir = root.joinpath(*parts)
        if _package_contains_python(module_dir):
            return True
        parent = root.joinpath(*parts[:-1]) if len(parts) > 1 else root
        return _module_file_exists(parent, parts[-1])


def _package_contains_python(directory: Path) -> bool:
    """Return whether ``directory`` hosts a Python package or module files.

    Args:
        directory: Candidate package directory.

    Returns:
        bool: ``True`` when the directory contains package metadata or Python sources.
    """

    if not directory.is_dir():
        return False
    init_file = directory / "__init__.py"
    if init_file.is_file():
        return True
    try:
        return any(entry.is_file() and entry.suffix in (".py", ".pyi") for entry in directory.iterdir())
    except OSError:
        return False


def _module_file_exists(parent: Path, module_name: str) -> bool:
    """Return whether ``parent`` contains a module or stub file named ``module_name``.

    Args:
        parent: Directory inspected for module files.
        module_name: Module name extracted from the import statement.

    Returns:
        bool: ``True`` when a Python source or stub file exists for the module.
    """

    for suffix in (".py", ".pyi"):
        candidate = parent / f"{module_name}{suffix}"
        if candidate.is_file():
            return True
    return False


def _uses_type_checking_guard(node: ast.If) -> bool:
    """Return whether ``node`` tests :data:`typing.TYPE_CHECKING` in any form.

    Args:
        node: ``if`` statement guarding the import.

    Returns:
        bool: ``True`` when the guard references ``typing.TYPE_CHECKING``.
    """

    for candidate in ast.walk(node.test):
        if isinstance(candidate, ast.Name) and candidate.id == _TYPE_CHECKING_SENTINEL:
            return True
        if isinstance(candidate, ast.Attribute) and candidate.attr == _TYPE_CHECKING_SENTINEL:
            return True
    return False


__all__ = ["DEFAULT_INTERFACES_ROOT", "run_conditional_import_linter"]
