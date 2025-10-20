# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Generic guidance for value-type classes based on Tree-sitter analysis."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Final, cast

from tree_sitter import Node, Parser

from pyqa.cli.commands.lint.preparation import PreparedLintState
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

from .base import InternalLintReport, build_internal_report
from .suppressions import SuppressionRegistry
from .tree_sitter_utils import resolve_python_parser
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
_FROZEN_ARGUMENT: Final[str] = "frozen=True"
_ENUM_SUFFIX: Final[str] = "Enum"
_NAMEDTUPLE_SUFFIXES: Final[tuple[str, ...]] = ("NamedTuple", "tuple")
_ITERABLE_BASES: Final[tuple[str, ...]] = ("Iterable", "Collection")
_SEQUENCE_BASES: Final[tuple[str, ...]] = ("Sequence", "MutableSequence")
_MAPPING_BASES: Final[tuple[str, ...]] = ("Mapping", "MutableMapping")
_ASSIGNMENT_MIN_CHILDREN: Final[int] = 3
_DATACLASS_SUFFIX: Final[str] = "dataclass"
_DECORATED_DEFINITION_NODE: Final[str] = "decorated_definition"
_DECORATOR_NODE: Final[str] = "decorator"
_CLASS_DEFINITION_NODE: Final[str] = "class_definition"
_FUNCTION_DEFINITION_NODE: Final[str] = "function_definition"
_ASYNC_FUNCTION_DEFINITION_NODE: Final[str] = "async_function_definition"
_EXPRESSION_STATEMENT_NODE: Final[str] = "expression_statement"
_ASSIGNMENT_NODE: Final[str] = "assignment"
_IDENTIFIER_NODE: Final[str] = "identifier"
_ATTRIBUTE_NODE: Final[str] = "attribute"
_NAME_FIELD: Final[str] = "name"
_BODY_FIELD: Final[str] = "body"
_SUPERCLASSES_FIELD: Final[str] = "superclasses"
_SLOTS_IDENTIFIER: Final[str] = "__slots__"
_INIT_MODULE_BASENAME: Final[str] = "__init__"
_METHOD_LEN: Final[str] = "__len__"
_METHOD_BOOL: Final[str] = "__bool__"
_METHOD_ITER: Final[str] = "__iter__"
_METHOD_CONTAINS: Final[str] = "__contains__"
_METHOD_EQ: Final[str] = "__eq__"
_METHOD_HASH: Final[str] = "__hash__"
_METHOD_REPR: Final[str] = "__repr__"
_METHOD_STR: Final[str] = "__str__"

_METHOD_NODE_TYPES: Final[tuple[str, ...]] = (
    _FUNCTION_DEFINITION_NODE,
    _ASYNC_FUNCTION_DEFINITION_NODE,
)


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

    try:
        parser = resolve_python_parser()
    except RuntimeError as exc:
        return build_internal_report(tool=TOOL_NAME, stdout=[str(exc)], diagnostics=[], files=())

    files = tuple(collect_python_files(state))
    suppressions = cast(SuppressionRegistry | None, getattr(state, "suppressions", None))
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []

    for file_path in files:
        file_diagnostics, file_stdout = _evaluate_file_for_value_types(
            parser=parser,
            file_path=file_path,
            root=state.root,
            config=gv_config,
            suppressions=suppressions,
        )
        diagnostics.extend(file_diagnostics)
        stdout_lines.extend(file_stdout)

    return build_internal_report(
        tool=TOOL_NAME,
        stdout=stdout_lines,
        diagnostics=diagnostics,
        files=files,
    )


def _collect_class_facts(
    parser: Parser,
    file_path: Path,
    root: Path,
) -> tuple[ClassFacts, ...]:
    """Return class metadata discovered in ``file_path`` using Tree-sitter.

    Args:
        parser: Tree-sitter parser configured for Python grammar.
        file_path: Python source file to inspect.
        root: Repository root used to normalise module names.

    Returns:
        tuple[ClassFacts, ...]: Facts describing each class definition in the file.
    """

    try:
        source = file_path.read_bytes()
    except OSError:
        return ()
    tree = parser.parse(source)
    module_name = _module_name(file_path, root)
    collector = _ClassCollector(source=source, module=module_name, root_file=file_path)
    collector.visit(tree.root_node)
    return tuple(collector.facts)


def _evaluate_file_for_value_types(
    parser: Parser,
    file_path: Path,
    root: Path,
    config: GenericValueTypesConfig,
    suppressions: SuppressionRegistry | None,
) -> tuple[list[Diagnostic], list[str]]:
    """Return diagnostics and stdout lines for ``file_path``.

    Args:
        parser: Tree-sitter parser configured for Python grammar.
        file_path: File currently being analysed.
        root: Repository root used for path normalisation.
        config: Generic value-type configuration defining rules.
        suppressions: Registry used to honour ``suppression_valid`` directives.

    Returns:
        tuple[list[Diagnostic], list[str]]: Diagnostics and corresponding stdout lines.
    """

    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    for facts in _collect_class_facts(parser, file_path, root):
        findings = _evaluate_class_facts(facts, config)
        if not findings:
            continue
        for finding in findings:
            diagnostic = _build_diagnostic(facts, finding, root)
            if suppressions is not None:
                absolute_path = facts.file_path if facts.file_path.is_absolute() else (root / facts.file_path).resolve()
                if suppressions.should_suppress(
                    absolute_path,
                    diagnostic.line or facts.line,
                    tool=diagnostic.tool,
                    code=diagnostic.code or diagnostic.tool,
                ):
                    continue
            diagnostics.append(diagnostic)
            stdout_lines.append(f"{diagnostic.file}:{diagnostic.line}: {diagnostic.message}")
    return diagnostics, stdout_lines


def _evaluate_class_facts(
    facts: ClassFacts,
    config: GenericValueTypesConfig,
) -> tuple[Finding, ...]:
    """Return findings for ``facts`` based on ``config`` rules and implications.

    Args:
        facts: Class metadata extracted from the source file.
        config: Configuration describing rules and implications.

    Returns:
        tuple[Finding, ...]: Findings describing missing dunder methods.
    """

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
    """Accumulate missing ``candidates`` into ``target`` keyed by ``reason``.

    Args:
        candidates: Candidate method names to evaluate.
        methods: Methods currently implemented on the class.
        allow_missing: Methods explicitly allowed to be omitted.
        target: Mapping of reason to missing method names.
        reason: Explanation associated with missing methods.
    """

    if not candidates:
        return
    missing = [candidate for candidate in candidates if candidate not in methods and candidate not in allow_missing]
    if not missing:
        return
    bucket = target.setdefault(reason, set())
    bucket.update(missing)


def _rule_matches(rule: GenericValueTypesRule, facts: ClassFacts) -> bool:
    """Return ``True`` when ``rule`` applies to ``facts``.

    Args:
        rule: Rule under evaluation.
        facts: Class metadata describing the candidate class.

    Returns:
        bool: ``True`` when the rule pattern matches the class facts.
    """

    if not fnmatchcase(facts.qualname, rule.pattern):
        return False
    if rule.traits and not set(rule.traits).issubset(facts.traits):
        return False
    return True


def _implication_matches(implication: GenericValueTypesImplication, facts: ClassFacts) -> bool:
    """Return ``True`` when ``implication`` should fire for ``facts``.

    Args:
        implication: Implication specification from the configuration.
        facts: Class metadata describing the candidate class.

    Returns:
        bool: ``True`` when the implication trigger is satisfied.
    """

    kind, trigger = implication.parsed_trigger()
    if implication.traits and not set(implication.traits).issubset(facts.traits):
        return False
    if kind is ValueTypeTriggerKind.METHOD:
        return trigger in facts.methods
    if kind is ValueTypeTriggerKind.TRAIT:
        return trigger in facts.traits
    raise AssertionError(f"Unhandled trigger kind: {kind}")


def _rule_reason(rule: GenericValueTypesRule) -> str:
    """Return a human-readable reason string for ``rule`` findings.

    Args:
        rule: Rule that produced the finding.

    Returns:
        str: Reason string describing the rule match.
    """

    if rule.description:
        return rule.description
    return f"rule pattern '{rule.pattern}'"


def _implication_reason(implication: GenericValueTypesImplication) -> str:
    """Return a human-readable reason string for ``implication`` findings.

    Args:
        implication: Implication that produced the finding.

    Returns:
        str: Reason string describing the implication trigger.
    """

    kind, trigger = implication.parsed_trigger()
    prefix = "method" if kind is ValueTypeTriggerKind.METHOD else "trait"
    return f"implication triggered by {prefix} '{trigger}'"


def _build_diagnostic(facts: ClassFacts, finding: Finding, root: Path) -> Diagnostic:
    """Convert ``finding`` into a ``Diagnostic`` for reporting.

    Args:
        facts: Class metadata associated with the finding.
        finding: Finding message describing the missing methods.
        root: Repository root used to normalise file paths.

    Returns:
        Diagnostic: Diagnostic representing the finding.
    """

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
    """Return the dotted module path for ``file_path`` relative to ``root``.

    Args:
        file_path: Source file being analysed.
        root: Repository root used to compute module names.

    Returns:
        str: Normalised module path.
    """

    try:
        relative = file_path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = file_path.resolve()
    parts = list(relative.parts)
    if not parts:
        return file_path.stem
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == _INIT_MODULE_BASENAME and len(parts) > 1:
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

    def visit(self, node: Node, parents: tuple[str, ...] = ()) -> None:
        """Traverse ``node`` collecting class metadata.

        Args:
            node: Current syntax node being visited.
            parents: Qualified name components for parent classes.
        """

        if node.type == _DECORATED_DEFINITION_NODE:
            decorators = tuple(self._decorator_info(child) for child in node.children if child.type == _DECORATOR_NODE)
            for child in node.children:
                if child.type == _CLASS_DEFINITION_NODE:
                    self._handle_class(child, parents, decorators)
                elif child.type in {_DECORATED_DEFINITION_NODE, _CLASS_DEFINITION_NODE}:
                    self.visit(child, parents)
                else:
                    self._visit_child(child, parents)
            return
        if node.type == _CLASS_DEFINITION_NODE:
            self._handle_class(node, parents, ())
            return
        self._visit_child(node, parents)

    def _visit_child(self, node: Node, parents: tuple[str, ...]) -> None:
        """Visit ``node`` while preserving ``parents`` context.

        Args:
            node: Child node to traverse.
            parents: Qualified name components for parent classes.
        """

        for child in node.children:
            self.visit(child, parents)

    def _handle_class(
        self,
        node: Node,
        parents: tuple[str, ...],
        decorators: tuple[_DecoratorInfo, ...],
    ) -> None:
        """Record class metadata for ``node`` and nested definitions.

        Args:
            node: Class definition node encountered in the syntax tree.
            parents: Qualified name components for parent classes.
            decorators: Decorators applied to the class definition.
        """

        name_node = node.child_by_field_name(_NAME_FIELD)
        if name_node is None:
            return
        class_name = self._slice(name_node)
        if not class_name:
            return
        qualname = ".".join(part for part in (self.module, *parents, class_name) if part)
        body = node.child_by_field_name(_BODY_FIELD)
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

    def _collect_methods(self, body: Node | None) -> set[str]:
        """Return method names defined within ``body``.

        Args:
            body: Class body node or ``None`` when absent.

        Returns:
            set[str]: Names of methods declared in the class body.
        """
        methods: set[str] = set()
        if body is None:
            return methods
        for child in body.children:
            if child.type not in _METHOD_NODE_TYPES:
                continue
            name_node = child.child_by_field_name(_NAME_FIELD)
            if name_node is None:
                continue
            method_name = self._slice(name_node)
            if method_name:
                methods.add(method_name)
        return methods

    def _collect_traits(
        self,
        node: Node,
        body: Node | None,
        decorators: tuple[_DecoratorInfo, ...],
        methods: set[str],
    ) -> set[str]:
        """Derive semantic traits for ``node``.

        Args:
            node: Class definition node.
            body: Body node containing class statements.
            decorators: Decorator metadata applied to the class.
            methods: Methods declared on the class.

        Returns:
            set[str]: Derived trait identifiers for the class.
        """
        decorator_traits = self._traits_from_decorators(decorators)
        base_traits = self._traits_from_bases(self._collect_bases(node.child_by_field_name(_SUPERCLASSES_FIELD)))
        method_traits = self._traits_from_methods(methods)
        traits = decorator_traits | base_traits | method_traits
        if self._has_slots(body):
            traits.add(_TRAIT_SLOTS)
        if traits & {_TRAIT_DATACLASS, _TRAIT_SLOTS, _TRAIT_SEQUENCE, _TRAIT_MAPPING}:
            traits.add(_TRAIT_VALUE_SEMANTICS)
        return traits

    def _traits_from_decorators(self, decorators: tuple[_DecoratorInfo, ...]) -> set[str]:
        """Return traits implied by ``decorators``.

        Args:
            decorators: Decorator metadata applied to a class definition.

        Returns:
            set[str]: Trait identifiers derived from decorators.
        """

        traits: set[str] = set()
        decorator_tokens = {token for decorator in decorators for token in decorator.tokens if token}
        if any(token.endswith(_DATACLASS_SUFFIX) for token in decorator_tokens):
            traits.add(_TRAIT_DATACLASS)
            decorator_text = {decorator.text for decorator in decorators if decorator.text}
            if any(_FROZEN_ARGUMENT in text for text in decorator_text):
                traits.add(_TRAIT_DATACLASS_FROZEN)
        return traits

    def _traits_from_bases(self, bases: tuple[str, ...]) -> set[str]:
        """Return traits implied by base classes listed in ``bases``.

        Args:
            bases: Base class names extracted from the class definition.

        Returns:
            set[str]: Trait identifiers derived from base classes.
        """

        traits: set[str] = set()
        if any(base.endswith(_ENUM_SUFFIX) for base in bases):
            traits.add(_TRAIT_ENUM)
        if any(base.endswith(suffix) for base in bases for suffix in _NAMEDTUPLE_SUFFIXES):
            traits.add(_TRAIT_VALUE_SEMANTICS)
        if any(base.endswith(option) for base in bases for option in _ITERABLE_BASES):
            traits.add(_TRAIT_ITERABLE)
        if any(base.endswith(option) for base in bases for option in _SEQUENCE_BASES):
            traits.add(_TRAIT_SEQUENCE)
        if any(base.endswith(option) for base in bases for option in _MAPPING_BASES):
            traits.add(_TRAIT_MAPPING)
        return traits

    def _traits_from_methods(self, methods: set[str]) -> set[str]:
        """Return traits implied by dunder ``methods``.

        Args:
            methods: Methods defined on the class.

        Returns:
            set[str]: Trait identifiers derived from method definitions.
        """

        traits: set[str] = set()
        if _METHOD_LEN in methods:
            traits.add(_TRAIT_LEN)
        if _METHOD_BOOL in methods:
            traits.add(_TRAIT_BOOL)
        if _METHOD_ITER in methods:
            traits.add(_TRAIT_ITER)
            traits.add(_TRAIT_ITERABLE)
        if _METHOD_CONTAINS in methods:
            traits.add(_TRAIT_CONTAINS)
        if _METHOD_EQ in methods:
            traits.add(_TRAIT_EQ)
        if _METHOD_HASH in methods:
            traits.add(_TRAIT_HASH)
        if _METHOD_REPR in methods:
            traits.add(_TRAIT_REPR)
        if _METHOD_STR in methods:
            traits.add(_TRAIT_STR)
        return traits

    def _collect_bases(self, argument_list: Node | None) -> tuple[str, ...]:
        """Return fully qualified base class names for ``argument_list``.

        Args:
            argument_list: AST node describing superclass arguments.

        Returns:
            tuple[str, ...]: Tuple of base class names.
        """
        if argument_list is None:
            return ()
        bases: list[str] = []
        for token in self._iterate_named_nodes(argument_list):
            if token.type in {_IDENTIFIER_NODE, _ATTRIBUTE_NODE}:
                text = self._slice(token)
                if text:
                    bases.append(text)
        return tuple(bases)

    def _has_slots(self, body: Node | None) -> bool:
        """Return ``True`` when ``body`` declares ``__slots__``.

        Args:
            body: Class body node inspected for ``__slots__``.

        Returns:
            bool: ``True`` when ``__slots__`` is declared.
        """
        if body is None:
            return False
        for child in body.children:
            if child.type != _EXPRESSION_STATEMENT_NODE or not child.children:
                continue
            assignment = child.children[0]
            if assignment.type != _ASSIGNMENT_NODE or len(assignment.children) < _ASSIGNMENT_MIN_CHILDREN:
                continue
            target = assignment.children[0]
            if target.type == _IDENTIFIER_NODE and self._slice(target) == _SLOTS_IDENTIFIER:
                return True
        return False

    def _decorator_info(self, decorator: Node) -> _DecoratorInfo:
        """Return decorator metadata extracted from ``decorator``.

        Args:
            decorator: Decorator node applied to the class definition.

        Returns:
            _DecoratorInfo: Extracted decorator token and text metadata.
        """
        tokens: list[str] = []
        for node in self._iterate_named_nodes(decorator):
            if node.type in {_IDENTIFIER_NODE, _ATTRIBUTE_NODE}:
                text = self._slice(node)
                if text:
                    tokens.append(text)
        text = self._slice(decorator)
        return _DecoratorInfo(tokens=tuple(tokens), text=text)

    def _iterate_named_nodes(self, node: Node) -> Iterator[Node]:
        """Yield named child nodes starting from ``node``.

        Args:
            node: Root node whose named descendants should be traversed.

        Yields:
            Node: Named child nodes in depth-first order.

        Returns:
            Iterator[Node]: Iterator yielding named nodes.
        """

        for child in node.children:
            is_named_attr = getattr(child, "is_named", True)
            is_named = bool(is_named_attr()) if callable(is_named_attr) else bool(is_named_attr)
            if is_named:
                yield child
            yield from self._iterate_named_nodes(child)

    def _slice(self, node: Node) -> str:
        """Return the UTF-8 decoded source slice for ``node``.

        Args:
            node: Node whose span should be extracted from ``self.source``.

        Returns:
            str: Source text corresponding to ``node``.
        """
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="ignore").strip()


__all__ = ["run_generic_value_type_linter"]
