# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Generic guidance for value-type classes based on Tree-sitter analysis."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast, runtime_checkable

from pyqa.analysis.treesitter.grammars import ensure_language
from pyqa.config import (
    Config,
    GenericValueTypesConfig,
    GenericValueTypesImplication,
    GenericValueTypesRule,
    ValueTypeFindingSeverity,
    ValueTypeTriggerKind,
)
from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from pyqa.cli.commands.lint.preparation import PreparedLintState
else:  # pragma: no cover - runtime placeholder to avoid circular import
    PreparedLintState = object

from .base import InternalLintReport, build_internal_report
from .utils import collect_python_files

TOOL_NAME: Final[str] = "generic-value-types"
_REQUIRED_CODE: Final[str] = "generic-value-types:missing-required"
_RECOMMENDED_CODE: Final[str] = "generic-value-types:missing-recommended"


@dataclass(frozen=True, slots=True)
class ClassFacts:
    """Context extracted for a Python class definition."""

    module: str
    qualname: str
    file_path: Path
    line: int
    methods: frozenset[str]
    traits: frozenset[str]


@dataclass(frozen=True, slots=True)
class Finding:
    """Represent a missing dunder report for a class."""

    severity: Severity
    reason: str
    methods: tuple[str, ...]


@runtime_checkable
class _TreeSitterNode(Protocol):
    """Protocol describing the tree-sitter node interface used by the linter."""

    type: str
    start_byte: int
    end_byte: int
    start_point: tuple[int, int]
    children: tuple[_TreeSitterNode, ...]

    def child_by_field_name(self, name: str) -> _TreeSitterNode | None:
        """Return the child node referenced by ``name`` when available."""
        ...


@runtime_checkable
class _TreeSitterTree(Protocol):
    """Protocol describing the tree-sitter parse tree interface."""

    @property
    def root_node(self) -> _TreeSitterNode:
        """Return the root node for the parsed source."""
        ...


class _TreeSitterParser(Protocol):
    """Protocol describing the tree-sitter parser surface used in the linter."""

    def parse(self, source: bytes) -> _TreeSitterTree:
        """Return the parsed tree for ``source``."""
        ...


_PARSER: _TreeSitterParser | None = None
_PARSER_ERROR: str | None = None


_TRAIT_DATACLASS: Final[str] = "dataclass"
_TRAIT_DATACLASS_FROZEN: Final[str] = "dataclass-frozen"
_TRAIT_SLOTS: Final[str] = "slots"
_TRAIT_ENUM: Final[str] = "enum"
_TRAIT_ITERABLE: Final[str] = "iterable"
_TRAIT_SEQUENCE: Final[str] = "sequence"
_TRAIT_MAPPING: Final[str] = "mapping"
_TRAIT_VALUE_SEMANTICS: Final[str] = "value"
_TRAIT_EQ: Final[str] = "eq"
_TRAIT_HASH: Final[str] = "hash"
_TRAIT_REPR: Final[str] = "repr"
_TRAIT_STR: Final[str] = "str"
_TRAIT_LEN: Final[str] = "len"
_TRAIT_BOOL: Final[str] = "bool"
_TRAIT_CONTAINS: Final[str] = "contains"
_TRAIT_ITER: Final[str] = "iter"

_METHOD_NODE_TYPES: Final[tuple[str, ...]] = ("function_definition", "async_function_definition")


def run_generic_value_type_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the generic value-type analyser and build a lint report.

    Args:
        state: Prepared lint state describing the active workspace.
        emit_to_logger: Compatibility flag required by the runner protocol; no
            logging side effects are produced directly.
        config: Effective configuration resolved for the invocation.

    Returns:
        ``InternalLintReport`` describing missing dunder methods for classes
        matching the configured rules.
    """

    _ = emit_to_logger
    gv_config = config.generic_value_types
    if not gv_config.enabled or (not gv_config.rules and not gv_config.implications):
        return build_internal_report(tool=TOOL_NAME, stdout=[], diagnostics=[], files=())

    parser = _resolve_parser()
    if parser is None:
        message = _PARSER_ERROR or "Tree-sitter parser unavailable; skipping generic value-type checks."
        return build_internal_report(tool=TOOL_NAME, stdout=[message], diagnostics=[], files=())

    files = tuple(collect_python_files(state))
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    suppressions = getattr(state, "suppressions", None)

    for file_path in files:
        for facts in _collect_class_facts(parser, file_path, state.root):
            findings = _evaluate_class_facts(facts, gv_config)
            if not findings:
                continue
            for finding in findings:
                diagnostic = _build_diagnostic(facts, finding, state.root)
                if suppressions is not None:
                    absolute_path = (
                        facts.file_path if facts.file_path.is_absolute() else (state.root / facts.file_path).resolve()
                    )
                    if suppressions.should_suppress(
                        absolute_path,
                        diagnostic.line or facts.line,
                        tool=diagnostic.tool,
                        code=diagnostic.code or diagnostic.tool,
                    ):
                        continue
                diagnostics.append(diagnostic)
                stdout_lines.append(f"{diagnostic.file}:{diagnostic.line}: {diagnostic.message}")

    return build_internal_report(
        tool=TOOL_NAME,
        stdout=stdout_lines,
        diagnostics=diagnostics,
        files=files,
    )


def _resolve_parser() -> _TreeSitterParser | None:
    """Return a cached Tree-sitter parser for Python source."""

    global _PARSER, _PARSER_ERROR
    if _PARSER is not None or _PARSER_ERROR is not None:
        return _PARSER
    try:
        from tree_sitter import Parser as TreeSitterParser
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        _PARSER_ERROR = "tree_sitter module is not installed"
        return None
    language = ensure_language("python")
    if language is None:  # pragma: no cover - depends on runtime environment
        _PARSER_ERROR = "Unable to load Tree-sitter Python grammar"
        return None
    _PARSER = cast(_TreeSitterParser, TreeSitterParser(language))
    return _PARSER


def _collect_class_facts(
    parser: _TreeSitterParser,
    file_path: Path,
    root: Path,
) -> tuple[ClassFacts, ...]:
    """Return class metadata discovered in ``file_path`` using Tree-sitter."""

    try:
        source = file_path.read_bytes()
    except OSError:
        return ()
    tree = parser.parse(source)
    module_name = _module_name(file_path, root)
    collector = _ClassCollector(source=source, module=module_name, root_file=file_path)
    collector.visit(tree.root_node)
    return tuple(collector.facts)


def _evaluate_class_facts(
    facts: ClassFacts,
    config: GenericValueTypesConfig,
) -> tuple[Finding, ...]:
    """Return findings for ``facts`` based on ``config`` rules and implications."""

    allow_missing: set[str] = set()
    required: dict[str, set[str]] = {}
    recommended: dict[str, set[str]] = {}

    for rule in config.rules:
        if not _rule_matches(rule, facts):
            continue
        allow_missing.update(rule.allow_missing)
        _accumulate_missing(rule.require, facts.methods, allow_missing, required, _rule_reason(rule))
        _accumulate_missing(rule.recommend, facts.methods, allow_missing, recommended, _rule_reason(rule))

    for implication in config.implications:
        if not _implication_matches(implication, facts):
            continue
        reason = _implication_reason(implication)
        target = required if implication.severity is ValueTypeFindingSeverity.ERROR else recommended
        _accumulate_missing(implication.require, facts.methods, allow_missing, target, reason)
        _accumulate_missing(implication.recommend, facts.methods, allow_missing, recommended, reason)

    findings: list[Finding] = []
    for reason, methods in required.items():
        if not methods:
            continue
        findings.append(
            Finding(
                severity=Severity.ERROR,
                reason=reason,
                methods=tuple(sorted(methods)),
            ),
        )
    for reason, methods in recommended.items():
        if not methods:
            continue
        findings.append(
            Finding(
                severity=Severity.WARNING,
                reason=reason,
                methods=tuple(sorted(methods)),
            ),
        )
    return tuple(findings)


def _accumulate_missing(
    candidates: Sequence[str],
    methods: frozenset[str],
    allow_missing: set[str],
    target: dict[str, set[str]],
    reason: str,
) -> None:
    """Accumulate missing ``candidates`` into ``target`` keyed by ``reason``."""

    if not candidates:
        return
    missing = [candidate for candidate in candidates if candidate not in methods and candidate not in allow_missing]
    if not missing:
        return
    bucket = target.setdefault(reason, set())
    bucket.update(missing)


def _rule_matches(rule: GenericValueTypesRule, facts: ClassFacts) -> bool:
    """Return ``True`` when ``rule`` applies to ``facts``."""

    if not fnmatchcase(facts.qualname, rule.pattern):
        return False
    if rule.traits and not set(rule.traits).issubset(facts.traits):
        return False
    return True


def _implication_matches(implication: GenericValueTypesImplication, facts: ClassFacts) -> bool:
    """Return ``True`` when ``implication`` should fire for ``facts``."""

    kind, trigger = implication.parsed_trigger()
    if implication.traits and not set(implication.traits).issubset(facts.traits):
        return False
    if kind is ValueTypeTriggerKind.METHOD:
        return trigger in facts.methods
    if kind is ValueTypeTriggerKind.TRAIT:
        return trigger in facts.traits
    raise AssertionError(f"Unhandled trigger kind: {kind}")


def _rule_reason(rule: GenericValueTypesRule) -> str:
    """Return a human-readable reason string for ``rule`` findings."""

    if rule.description:
        return rule.description
    return f"rule pattern '{rule.pattern}'"


def _implication_reason(implication: GenericValueTypesImplication) -> str:
    """Return a human-readable reason string for ``implication`` findings."""

    kind, trigger = implication.parsed_trigger()
    prefix = "method" if kind is ValueTypeTriggerKind.METHOD else "trait"
    return f"implication triggered by {prefix} '{trigger}'"


def _build_diagnostic(facts: ClassFacts, finding: Finding, root: Path) -> Diagnostic:
    """Convert ``finding`` into a ``Diagnostic`` for reporting."""

    code = _RECOMMENDED_CODE if finding.severity is Severity.WARNING else _REQUIRED_CODE
    message = (
        f"{facts.qualname} is missing {'recommended' if finding.severity is Severity.WARNING else 'required'} "
        f"dunder methods: {', '.join(finding.methods)} ({finding.reason})"
    )
    normalized_path = normalize_path_key(facts.file_path, base_dir=root)
    return Diagnostic(
        file=normalized_path,
        line=facts.line,
        column=None,
        severity=finding.severity,
        message=message,
        tool=TOOL_NAME,
        code=code,
    )


def _module_name(file_path: Path, root: Path) -> str:
    """Return the dotted module path for ``file_path`` relative to ``root``."""

    try:
        relative = file_path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = file_path.resolve()
    parts = list(relative.parts)
    if not parts:
        return file_path.stem
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__" and len(parts) > 1:
        parts = parts[:-1]
    dotted = ".".join(part for part in parts if part)
    return dotted or file_path.stem


@dataclass(frozen=True, slots=True)
class _DecoratorInfo:
    """Capture metadata extracted from a decorator node."""

    tokens: tuple[str, ...]
    text: str


@dataclass(slots=True)
class _ClassCollector:
    """Tree visitor that extracts :class:`ClassFacts` instances."""

    source: bytes
    module: str
    root_file: Path
    facts: list[ClassFacts] = field(default_factory=list)

    def visit(self, node: _TreeSitterNode, parents: tuple[str, ...] = ()) -> None:
        """Traverse ``node`` collecting class metadata."""

        if node.type == "decorated_definition":
            decorators = tuple(self._decorator_info(child) for child in node.children if child.type == "decorator")
            for child in node.children:
                if child.type == "class_definition":
                    self._handle_class(child, parents, decorators)
                elif child.type in {"decorated_definition", "class_definition"}:
                    self.visit(child, parents)
                else:
                    self._visit_child(child, parents)
            return
        if node.type == "class_definition":
            self._handle_class(node, parents, ())
            return
        self._visit_child(node, parents)

    def _visit_child(self, node: _TreeSitterNode, parents: tuple[str, ...]) -> None:
        for child in node.children:
            self.visit(child, parents)

    def _handle_class(
        self,
        node: _TreeSitterNode,
        parents: tuple[str, ...],
        decorators: tuple[_DecoratorInfo, ...],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        class_name = self._slice(name_node)
        if not class_name:
            return
        qualname = ".".join(part for part in (self.module, *parents, class_name) if part)
        body = node.child_by_field_name("body")
        methods = self._collect_methods(body)
        traits = self._collect_traits(node, body, decorators, methods)
        line = (node.start_point[0] if node.start_point else 0) + 1
        facts = ClassFacts(
            module=self.module,
            qualname=qualname,
            file_path=self.root_file,
            line=line,
            methods=frozenset(methods),
            traits=frozenset(traits),
        )
        self.facts.append(facts)
        if body is None:
            return
        nested_parents = parents + (class_name,)
        for child in body.children:
            self.visit(child, nested_parents)

    def _collect_methods(self, body: _TreeSitterNode | None) -> set[str]:
        methods: set[str] = set()
        if body is None:
            return methods
        for child in body.children:
            if child.type not in _METHOD_NODE_TYPES:
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            method_name = self._slice(name_node)
            if method_name:
                methods.add(method_name)
        return methods

    def _collect_traits(
        self,
        node: _TreeSitterNode,
        body: _TreeSitterNode | None,
        decorators: tuple[_DecoratorInfo, ...],
        methods: set[str],
    ) -> set[str]:
        traits: set[str] = set()
        decorator_tokens = {token for decorator in decorators for token in decorator.tokens if token}
        if any(token.endswith("dataclass") for token in decorator_tokens):
            traits.add(_TRAIT_DATACLASS)
            decorator_text = {decorator.text for decorator in decorators if decorator.text}
            if any("frozen=True" in text for text in decorator_text):
                traits.add(_TRAIT_DATACLASS_FROZEN)
        argument_list = node.child_by_field_name("superclasses")
        bases = self._collect_bases(argument_list)
        if any(base.endswith("Enum") for base in bases):
            traits.add(_TRAIT_ENUM)
        if any(base.endswith(tuple_name) for base in bases for tuple_name in ("NamedTuple", "tuple")):
            traits.add(_TRAIT_VALUE_SEMANTICS)
        if any(base.endswith(option) for base in bases for option in ("Iterable", "Collection")):
            traits.add(_TRAIT_ITERABLE)
        if any(base.endswith(option) for base in bases for option in ("Sequence", "MutableSequence")):
            traits.add(_TRAIT_SEQUENCE)
        if any(base.endswith(option) for base in bases for option in ("Mapping", "MutableMapping")):
            traits.add(_TRAIT_MAPPING)
        if self._has_slots(body):
            traits.add(_TRAIT_SLOTS)
        if traits & {_TRAIT_DATACLASS, _TRAIT_SLOTS, _TRAIT_SEQUENCE, _TRAIT_MAPPING}:
            traits.add(_TRAIT_VALUE_SEMANTICS)
        if "__len__" in methods:
            traits.add(_TRAIT_LEN)
        if "__bool__" in methods:
            traits.add(_TRAIT_BOOL)
        if "__iter__" in methods:
            traits.add(_TRAIT_ITER)
            traits.add(_TRAIT_ITERABLE)
        if "__contains__" in methods:
            traits.add(_TRAIT_CONTAINS)
        if "__eq__" in methods:
            traits.add(_TRAIT_EQ)
        if "__hash__" in methods:
            traits.add(_TRAIT_HASH)
        if "__repr__" in methods:
            traits.add(_TRAIT_REPR)
        if "__str__" in methods:
            traits.add(_TRAIT_STR)
        return traits

    def _collect_bases(self, argument_list: _TreeSitterNode | None) -> tuple[str, ...]:
        if argument_list is None:
            return ()
        bases: list[str] = []
        for token in self._iterate_named_nodes(argument_list):
            if token.type in {"identifier", "attribute"}:
                text = self._slice(token)
                if text:
                    bases.append(text)
        return tuple(bases)

    def _has_slots(self, body: _TreeSitterNode | None) -> bool:
        if body is None:
            return False
        for child in body.children:
            if child.type != "expression_statement" or not child.children:
                continue
            assignment = child.children[0]
            if assignment.type != "assignment" or len(assignment.children) < 3:
                continue
            target = assignment.children[0]
            if target.type == "identifier" and self._slice(target) == "__slots__":
                return True
        return False

    def _decorator_info(self, decorator: _TreeSitterNode) -> _DecoratorInfo:
        tokens: list[str] = []
        for node in self._iterate_named_nodes(decorator):
            if node.type in {"identifier", "attribute"}:
                text = self._slice(node)
                if text:
                    tokens.append(text)
        text = self._slice(decorator)
        return _DecoratorInfo(tokens=tuple(tokens), text=text)

    def _iterate_named_nodes(self, node: _TreeSitterNode) -> Iterator[_TreeSitterNode]:
        stack: list[_TreeSitterNode] = [node]
        while stack:
            current = stack.pop()
            for child in current.children:
                is_named_attr = getattr(child, "is_named", True)
                if callable(is_named_attr):
                    is_named = bool(is_named_attr())
                else:
                    is_named = bool(is_named_attr)
                if is_named:
                    yield child
                stack.append(child)

    def _slice(self, node: _TreeSitterNode) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="ignore").strip()


__all__ = ["run_generic_value_type_linter"]
