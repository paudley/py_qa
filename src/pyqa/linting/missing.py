# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Internal linter that flags markers for missing functionality."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterator, Protocol

from tree_sitter import Node, Parser

from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key
from pyqa.interfaces.linting import PreparedLintState
from pyqa.cache.in_memory import memoize

from .base import InternalLintReport, build_internal_report
from .tree_sitter_utils import resolve_python_parser
from .utils import collect_target_files

_GENERIC_MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:TODO|FIXME|TBD|XXX|PENDING|STUB)\b",
    re.IGNORECASE,
)
_NOT_IMPLEMENTED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bnot[\s_-]?implemented\b",
    re.IGNORECASE,
)
_RUST_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:todo|unimplemented)\s*!",
    re.IGNORECASE,
)
_CS_NOT_IMPLEMENTED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bthrow\s+new\s+NotImplementedException\b",
    re.IGNORECASE,
)
_CS_NOT_SUPPORTED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bthrow\s+new\s+NotSupportedException\b",
    re.IGNORECASE,
)
_PYTHON_NOT_IMPLEMENTED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\braise\s+NotImplementedError\b",
    re.IGNORECASE,
)
_PYTHON_SUFFIXES: Final[frozenset[str]] = frozenset({".py", ".pyi"})
_DOC_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".markdown", ".rst"})
_ESCAPE_CHAR: Final[str] = "\\"
_SINGLE_QUOTE: Final[str] = "'"
_DOUBLE_QUOTE: Final[str] = '"'
_BACKTICK: Final[str] = "`"
_INTERFACES_SEGMENT: Final[str] = "interfaces"
_FUNCTION_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {"function_definition", "async_function_definition"},
)
_CLASS_NODE_TYPE: Final[str] = "class_definition"
_DECORATED_DEFINITION: Final[str] = "decorated_definition"
_RAISE_STATEMENT: Final[str] = "raise_statement"
_ABSTRACT_DECORATOR_TOKENS: Final[tuple[str, ...]] = (
    "abstractmethod",
    "abstractclassmethod",
    "abstractproperty",
    "abstractstaticmethod",
)
_DECORATOR_NODE_TYPE: Final[str] = "decorator"
_PROTOCOL_TOKEN: Final[str] = "protocol"
_NOT_IMPLEMENTED_ERROR_TOKEN: Final[str] = "NotImplementedError"

_MARKER_MESSAGE_TEMPLATE: Final[str] = "Marker '{marker}' indicates missing implementation."
_NOT_IMPLEMENTED_ERROR_MESSAGE: Final[str] = "Raising NotImplementedError indicates missing functionality."
_NOT_IMPLEMENTED_EXCEPTION_MESSAGE: Final[str] = "Throwing NotImplemented/NotSupported indicates missing functionality."
_PLACEHOLDER_MACRO_MESSAGE: Final[str] = "Placeholder macro indicates missing implementation."
_NOT_IMPLEMENTED_PHRASE_MESSAGE: Final[str] = "Line references 'not implemented', suggesting incomplete code."


@dataclass(frozen=True, slots=True)
class _FileScanContext:
    """Describe immutable file-level metadata required during scanning."""

    path: Path
    suffix: str
    skip_not_implemented: bool
    safe_not_implemented_lines: frozenset[int]

    @property
    def is_python(self) -> bool:
        """Return whether the current file should follow Python-specific heuristics.

        Returns:
            bool: ``True`` when the file extension matches Python expectations.
        """

        return self.suffix in _PYTHON_SUFFIXES


@dataclass(frozen=True, slots=True)
class _LineContext:
    """Describe immutable line-level metadata used by detectors."""

    number: int
    raw_text: str
    stripped_text: str


class _LineDetector(Protocol):
    """Protocol implemented by line-level detection helpers."""

    def __call__(self, file_ctx: _FileScanContext, line_ctx: _LineContext) -> tuple[_Finding, ...]:
        """Return findings detected for ``line_ctx`` within ``file_ctx``.

        Args:
            file_ctx: File-level context applied to the current scan.
            line_ctx: Line context describing the source under inspection.

        Returns:
            tuple[_Finding, ...]: Findings that should be recorded for the line.
        """



@dataclass(frozen=True, slots=True)
class _Finding:
    """Represent a missing-functionality finding discovered in a file."""

    file: Path
    line: int
    message: str
    code: str


def run_missing_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
) -> InternalLintReport:
    """Execute the missing functionality linter and return its report.

    Args:
        state: Prepared lint state describing the current invocation. Markdown
            and other documentation files are ignored automatically.
        emit_to_logger: Unused compatibility flag for the internal runner API.

    Returns:
        InternalLintReport: Aggregated diagnostics describing missing work.
    """

    _ = emit_to_logger
    findings: list[_Finding] = []
    target_files = collect_target_files(state)
    for file_path in target_files:
        if file_path.suffix.lower() in _DOC_SUFFIXES:
            continue
        findings.extend(_scan_file(file_path))

    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    for finding in findings:
        normalized = normalize_path_key(finding.file, base_dir=state.root)
        diagnostics.append(
            Diagnostic(
                file=normalized,
                line=finding.line,
                column=None,
                severity=Severity.ERROR,
                message=finding.message,
                tool="missing",
                code=finding.code,
            ),
        )
        stdout_lines.append(f"{normalized}:{finding.line}: {finding.message}")

    return build_internal_report(
        tool="missing",
        stdout=stdout_lines,
        diagnostics=diagnostics,
        files=tuple(sorted(target_files)),
    )


def _scan_file(path: Path) -> list[_Finding]:
    """Collect missing-functionality findings detected within ``path``.

    Args:
        path: File path under inspection.

    Returns:
        list[_Finding]: Findings detected within the file.
    """

    text = _read_text(path)
    file_ctx = _build_file_scan_context(path, text)
    findings: list[_Finding] = []
    for line_ctx in _iter_line_contexts(text.splitlines()):
        detections = _detect_line_findings(file_ctx, line_ctx)
        if detections:
            findings.extend(detections)
    return findings


def _read_text(path: Path) -> str:
    """Return the decoded contents of ``path`` using a tolerant UTF-8 strategy.

    Args:
        path: File path whose contents should be loaded.

    Returns:
        str: UTF-8 decoded file contents.
    """

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _build_file_scan_context(path: Path, text: str) -> _FileScanContext:
    """Return a file-scan context capturing metadata required for detectors.

    Args:
        path: File path under inspection.
        text: Raw text content of the file.

    Returns:
        _FileScanContext: Immutable context describing file-level configuration.
    """

    suffix = path.suffix.lower()
    safe_lines = _collect_python_stub_lines(text) if suffix in _PYTHON_SUFFIXES else frozenset()
    return _FileScanContext(
        path=path,
        suffix=suffix,
        skip_not_implemented=_INTERFACES_SEGMENT in path.parts,
        safe_not_implemented_lines=safe_lines,
    )


def _iter_line_contexts(lines: list[str]) -> Iterator[_LineContext]:
    """Yield :class:`_LineContext` entries for ``lines``.

    Args:
        lines: Sequence of raw line contents.

    Yields:
        _LineContext: Immutable view of each line suitable for detectors.
    """

    for number, raw_line in enumerate(lines, start=1):
        yield _LineContext(number=number, raw_text=raw_line, stripped_text=raw_line.strip())


def _detect_line_findings(file_ctx: _FileScanContext, line_ctx: _LineContext) -> list[_Finding]:
    """Return findings generated by the detection pipeline for ``line_ctx``.

    Args:
        file_ctx: Context describing the file being scanned.
        line_ctx: Context describing the current line under inspection.

    Returns:
        list[_Finding]: Findings detected for the supplied line.
    """

    for detector in _LINE_DETECTORS:
        findings = detector(file_ctx, line_ctx)
        if findings:
            return list(findings)
    return []


def _detect_generic_marker(file_ctx: _FileScanContext, line_ctx: _LineContext) -> tuple[_Finding, ...]:
    """Detect generic TODO-style markers present within the line.

    Args:
        file_ctx: File-level context applied to the current scan.
        line_ctx: Line context describing the source under inspection.

    Returns:
        tuple[_Finding, ...]: Findings highlighting generic TODO markers.
    """

    marker_match = _GENERIC_MARKER_PATTERN.search(line_ctx.raw_text)
    if marker_match is None or _is_within_string(line_ctx.raw_text, marker_match.start()):
        return ()
    marker = marker_match.group(0)
    return (
        _build_finding(
            file_ctx,
            line_ctx,
            _MARKER_MESSAGE_TEMPLATE.format(marker=marker),
            "missing:marker",
        ),
    )


def _detect_python_not_implemented_error(
    file_ctx: _FileScanContext,
    line_ctx: _LineContext,
) -> tuple[_Finding, ...]:
    """Detect ``NotImplementedError`` raises that lack abstract context.

    Args:
        file_ctx: File-level context applied to the current scan.
        line_ctx: Line context describing the source under inspection.

    Returns:
        tuple[_Finding, ...]: Findings created for disallowed ``NotImplementedError`` raises.
    """

    if not file_ctx.is_python:
        return ()
    match = _PYTHON_NOT_IMPLEMENTED_PATTERN.search(line_ctx.raw_text)
    if match is None or _is_within_string(line_ctx.raw_text, match.start()):
        return ()
    if file_ctx.skip_not_implemented or line_ctx.number in file_ctx.safe_not_implemented_lines:
        return ()
    return (
        _build_finding(
            file_ctx,
            line_ctx,
            _NOT_IMPLEMENTED_ERROR_MESSAGE,
            "missing:not-implemented-error",
        ),
    )


def _detect_cs_placeholder(
    file_ctx: _FileScanContext,
    line_ctx: _LineContext,
) -> tuple[_Finding, ...]:
    """Detect C# placeholders such as ``NotImplementedException`` raises.

    Args:
        file_ctx: File-level context applied to the current scan.
        line_ctx: Line context describing the source under inspection.

    Returns:
        tuple[_Finding, ...]: Findings capturing C# placeholder exceptions.
    """

    match = _CS_NOT_IMPLEMENTED_PATTERN.search(line_ctx.raw_text)
    if match is None:
        match = _CS_NOT_SUPPORTED_PATTERN.search(line_ctx.raw_text)
    if match is None or _is_within_string(line_ctx.raw_text, match.start()):
        return ()
    return (
        _build_finding(
            file_ctx,
            line_ctx,
            _NOT_IMPLEMENTED_EXCEPTION_MESSAGE,
            "missing:not-implemented-exception",
        ),
    )


def _detect_rust_placeholder(
    file_ctx: _FileScanContext,
    line_ctx: _LineContext,
) -> tuple[_Finding, ...]:
    """Detect Rust placeholder macros such as ``todo!`` and ``unimplemented!``.

    Args:
        file_ctx: File-level context applied to the current scan.
        line_ctx: Line context describing the source under inspection.

    Returns:
        tuple[_Finding, ...]: Findings describing placeholder macro usage.
    """

    if _RUST_PLACEHOLDER_PATTERN.search(line_ctx.stripped_text):
        return (
            _build_finding(
                file_ctx,
                line_ctx,
                _PLACEHOLDER_MACRO_MESSAGE,
                "missing:placeholder-macro",
            ),
        )
    return ()


def _detect_not_implemented_phrase(
    file_ctx: _FileScanContext,
    line_ctx: _LineContext,
) -> tuple[_Finding, ...]:
    """Detect textual ``not implemented`` references outside of interfaces.

    Args:
        file_ctx: File-level context applied to the current scan.
        line_ctx: Line context describing the source under inspection.

    Returns:
        tuple[_Finding, ...]: Findings documenting textual ``not implemented`` references.
    """

    if file_ctx.skip_not_implemented:
        return ()
    match = _NOT_IMPLEMENTED_PATTERN.search(line_ctx.raw_text)
    if match is None or _is_within_string(line_ctx.raw_text, match.start()):
        return ()
    return (
        _build_finding(
            file_ctx,
            line_ctx,
            _NOT_IMPLEMENTED_PHRASE_MESSAGE,
            "missing:not-implemented-text",
        ),
    )


def _build_finding(
    file_ctx: _FileScanContext,
    line_ctx: _LineContext,
    message: str,
    code: str,
) -> _Finding:
    """Construct a :class:`_Finding` with shared metadata helpers.

    Args:
        file_ctx: File-level context applied to the current scan.
        line_ctx: Line context describing the source under inspection.
        message: Human-readable diagnostic message.
        code: Diagnostic code emitted by the detector.

    Returns:
        _Finding: Populated finding ready for aggregation.
    """

    return _Finding(file=file_ctx.path, line=line_ctx.number, message=message, code=code)


_LINE_DETECTORS: Final[tuple[_LineDetector, ...]] = (
    _detect_generic_marker,
    _detect_python_not_implemented_error,
    _detect_cs_placeholder,
    _detect_rust_placeholder,
    _detect_not_implemented_phrase,
)
def _collect_python_stub_lines(source: str) -> frozenset[int]:
    """Return line numbers where ``NotImplementedError`` is raised in an abstract context.

    Args:
        source: Python source text to analyse.

    Returns:
        frozenset[int]: Line numbers containing abstract ``NotImplementedError`` raises.
    """

    parser = _python_parser()
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    safe_lines: set[int] = set()
    _collect_abstract_raise_lines(tree.root_node, source_bytes, safe_lines)
    return frozenset(safe_lines)


def _collect_abstract_raise_lines(node: Node, source_bytes: bytes, safe_lines: set[int]) -> None:
    """Populate ``safe_lines`` with raises deemed valid inside abstract contracts.

    Args:
        node: Current Tree-sitter node under inspection.
        source_bytes: Encoded module source used for slicing snippets.
        safe_lines: Collector for line numbers that should be considered safe.

    Returns:
        None
    """

    if node.type == _RAISE_STATEMENT and _node_raises_not_implemented(node, source_bytes):
        function_node = _nearest_function_node(node)
        if function_node is not None and _function_is_abstract(function_node, source_bytes):
            safe_lines.add(node.start_point[0] + 1)
    for child in node.children:
        _collect_abstract_raise_lines(child, source_bytes, safe_lines)


@memoize(maxsize=1)
def _python_parser() -> Parser:
    """Return a cached Tree-sitter parser for Python source.

    Returns:
        Parser: Tree-sitter parser configured for Python grammar.
    """

    return resolve_python_parser()


def _iter_parent_nodes(node: Node) -> Iterator[Node]:
    """Yield parent nodes for ``node`` starting from the immediate parent.

    Args:
        node: Tree-sitter node whose ancestors are desired.

    Yields:
        Node: Parent nodes beginning with the immediate parent.
    """

    parent = node.parent
    if parent is None:
        return
    yield parent
    yield from _iter_parent_nodes(parent)


def _node_raises_not_implemented(node: Node, source_bytes: bytes) -> bool:
    """Determine whether ``node`` raises ``NotImplementedError``.

    Args:
        node: Tree-sitter node to inspect.
        source_bytes: Encoded source text for the Python module.

    Returns:
        bool: ``True`` when ``node`` raises ``NotImplementedError``.
    """

    snippet = source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")
    return _NOT_IMPLEMENTED_ERROR_TOKEN in snippet


def _nearest_function_node(node: Node) -> Node | None:
    """Return the nearest ancestor function node for ``node``.

    Args:
        node: Tree-sitter node whose ancestors are inspected.

    Returns:
        Node | None: Function definition node when present; otherwise ``None``.
    """

    for ancestor in _iter_parent_nodes(node):
        if ancestor.type in _FUNCTION_NODE_TYPES:
            return ancestor
    return None


def _function_is_abstract(function_node: Node, source_bytes: bytes) -> bool:
    """Return ``True`` when ``function_node`` represents an abstract contract.

    Args:
        function_node: Function definition node under inspection.
        source_bytes: Encoded source text for the Python module.

    Returns:
        bool: ``True`` when the function is abstract or part of a protocol.
    """

    if _function_has_abstract_decorator(function_node, source_bytes):
        return True
    class_node = _nearest_class_node(function_node)
    if class_node is None:
        return False
    return _class_is_protocol(class_node, source_bytes)


def _function_has_abstract_decorator(function_node: Node, source_bytes: bytes) -> bool:
    """Return whether ``function_node`` is decorated with an abstract decorator.

    Args:
        function_node: Function definition node to inspect.
        source_bytes: Encoded source text for the Python module.

    Returns:
        bool: ``True`` when the function carries an abstract decorator.
    """

    parent = function_node.parent
    if parent is None or parent.type != _DECORATED_DEFINITION:
        return False
    decorators = parent.child_by_field_name("decorators")
    if decorators is None:
        return False
    for decorator in decorators.children:
        if decorator.type != _DECORATOR_NODE_TYPE:
            continue
        text = (
            source_bytes[decorator.start_byte : decorator.end_byte]
            .decode(
                "utf-8",
                errors="ignore",
            )
            .lower()
        )
        if any(token in text for token in _ABSTRACT_DECORATOR_TOKENS):
            return True
    return False


def _nearest_class_node(node: Node) -> Node | None:
    """Return the nearest ancestor class definition node for ``node``.

    Args:
        node: Tree-sitter node whose ancestors are inspected.

    Returns:
        Node | None: Class definition node when present; otherwise ``None``.
    """

    for ancestor in _iter_parent_nodes(node):
        if ancestor.type == _CLASS_NODE_TYPE:
            return ancestor
    return None


def _class_is_protocol(class_node: Node, source_bytes: bytes) -> bool:
    """Return whether ``class_node`` inherits from a protocol type.

    Args:
        class_node: Class definition node to inspect.
        source_bytes: Encoded source text for the Python module.

    Returns:
        bool: ``True`` when the class derives from ``Protocol``.
    """

    body = class_node.child_by_field_name("body")
    header_end = body.start_byte if body is not None else class_node.end_byte
    header_text = source_bytes[class_node.start_byte : header_end].decode("utf-8", errors="ignore")
    return _PROTOCOL_TOKEN in header_text.lower()


def _is_within_string(line: str, index: int) -> bool:
    """Determine whether ``index`` is located within a string literal.

    Args:
        line: Source line containing potential string delimiters.
        index: Character index to evaluate for string membership.

    Returns:
        bool: ``True`` when ``index`` resides within a quoted string region.
    """

    in_single = False
    in_double = False
    in_backtick = False
    escape = False
    for position, char in enumerate(line):
        if position == index:
            return in_single or in_double or in_backtick
        if escape:
            escape = False
            continue
        if char == _ESCAPE_CHAR:
            escape = True
            continue
        if char == _SINGLE_QUOTE and not in_double and not in_backtick:
            in_single = not in_single
            continue
        if char == _DOUBLE_QUOTE and not in_single and not in_backtick:
            in_double = not in_double
            continue
        if char == _BACKTICK and not in_single and not in_double:
            in_backtick = not in_backtick
    return in_single or in_double or in_backtick


__all__ = ["run_missing_linter"]
