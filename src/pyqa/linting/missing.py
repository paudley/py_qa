# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Internal linter that flags markers for missing functionality."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from tree_sitter import Node, Parser

from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key
from pyqa.interfaces.linting import PreparedLintState

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
    """Collect missing-functionality findings from ``path``.

    Args:
        path: File path under inspection.

    Returns:
        list[_Finding]: Findings detected within the file.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    findings: list[_Finding] = []
    suffix = path.suffix.lower()
    skip_not_implemented = _INTERFACES_SEGMENT in path.parts
    safe_not_implemented_lines: frozenset[int] = frozenset()
    if suffix in _PYTHON_SUFFIXES:
        safe_not_implemented_lines = _collect_python_stub_lines(text)
    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        generic_marker = _match_generic_marker(raw_line)
        if generic_marker is not None:
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message=f"Marker '{generic_marker}' indicates missing implementation.",
                    code="missing:marker",
                ),
            )
            continue

        python_match = None
        if suffix in _PYTHON_SUFFIXES:
            python_match = _PYTHON_NOT_IMPLEMENTED_PATTERN.search(raw_line)
        if python_match is not None and not _is_within_string(raw_line, python_match.start()):
            if skip_not_implemented or line_number in safe_not_implemented_lines:
                continue
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Raising NotImplementedError indicates missing functionality.",
                    code="missing:not-implemented-error",
                ),
            )
            continue

        cs_match = _CS_NOT_IMPLEMENTED_PATTERN.search(raw_line) or _CS_NOT_SUPPORTED_PATTERN.search(
            raw_line,
        )
        if cs_match is not None and not _is_within_string(raw_line, cs_match.start()):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Throwing NotImplemented/NotSupported indicates missing functionality.",
                    code="missing:not-implemented-exception",
                ),
            )
            continue

        if _RUST_PLACEHOLDER_PATTERN.search(stripped):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Placeholder macro indicates missing implementation.",
                    code="missing:placeholder-macro",
                ),
            )
            continue

        not_impl_match = _NOT_IMPLEMENTED_PATTERN.search(raw_line)
        if (
            not_impl_match is not None
            and not skip_not_implemented
            and not _is_within_string(raw_line, not_impl_match.start())
        ):
            findings.append(
                _Finding(
                    file=path,
                    line=line_number,
                    message="Line references 'not implemented', suggesting incomplete code.",
                    code="missing:not-implemented-text",
                ),
            )
            continue
    return findings


def _match_generic_marker(line: str) -> str | None:
    """Identify the missing-work marker present within ``line``.

    Args:
        line: Line of source text to inspect.

    Returns:
        str | None: Matched marker text when detected; otherwise ``None``.
    """

    marker_match = _GENERIC_MARKER_PATTERN.search(line)
    if marker_match is not None and not _is_within_string(line, marker_match.start()):
        return marker_match.group(0)
    return None


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

    def _visit(node: Node) -> None:
        if node.type == _RAISE_STATEMENT and _node_raises_not_implemented(node, source_bytes):
            function_node = _nearest_function_node(node)
            if function_node is not None and _function_is_abstract(function_node, source_bytes):
                safe_lines.add(node.start_point[0] + 1)
        for child in node.children:
            _visit(child)

    _visit(tree.root_node)
    return frozenset(safe_lines)


@lru_cache(maxsize=1)
def _python_parser() -> Parser:
    """Return a cached Tree-sitter parser for Python source.

    Returns:
        Parser: Tree-sitter parser configured for Python grammar.
    """

    return resolve_python_parser()


def _node_raises_not_implemented(node: Node, source_bytes: bytes) -> bool:
    """Determine whether ``node`` raises ``NotImplementedError``.

    Args:
        node: Tree-sitter node to inspect.
        source_bytes: Encoded source text for the Python module.

    Returns:
        bool: ``True`` when ``node`` raises ``NotImplementedError``.
    """

    snippet = source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")
    return "NotImplementedError" in snippet


def _nearest_function_node(node: Node) -> Node | None:
    """Return the nearest ancestor function node for ``node``.

    Args:
        node: Tree-sitter node whose ancestors are inspected.

    Returns:
        Node | None: Function definition node when present; otherwise ``None``.
    """

    current = node.parent
    while current is not None:
        if current.type in _FUNCTION_NODE_TYPES:
            return current
        current = current.parent
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
        if decorator.type != "decorator":
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

    current = node.parent
    while current is not None:
        if current.type == _CLASS_NODE_TYPE:
            return current
        current = current.parent
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
    return "protocol" in header_text.lower()


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
