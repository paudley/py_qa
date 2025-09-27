# SPDX-License-Identifier: MIT
"""Duplicate code detection for DRY-focused advice."""

from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence, cast

from ..config import DuplicateDetectionConfig
from ..models import Diagnostic, RunResult


@dataclass(frozen=True)
class DuplicateOccurrence:
    """Single duplicate appearance captured during analysis."""

    file: str
    line: int | None
    function: str | None
    size: int | None
    snippet: str | None


@dataclass(frozen=True)
class DuplicateCluster:
    """Grouped duplicates discovered by a specific strategy."""

    kind: str
    fingerprint: str
    summary: str
    occurrences: tuple[DuplicateOccurrence, ...]


class _CanonicalisingTransformer(ast.NodeTransformer):
    """Normalize AST identifiers, literals, and attribute names for hashing."""

    def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: D401 - docstring inherited
        return ast.copy_location(ast.Name(id="NAME", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:  # noqa: D401
        node.arg = "ARG"
        if node.annotation is not None:
            node.annotation = self.visit(node.annotation)
        return node

    def visit_alias(self, node: ast.alias) -> ast.AST:  # noqa: D401
        node.name = "ALIAS"
        if node.asname is not None:
            node.asname = "ALIAS"
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:  # noqa: D401
        node = self.generic_visit(node)
        node.attr = "ATTR"
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # noqa: D401
        node = self.generic_visit(node)
        node.name = "FUNC"
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:  # noqa: D401
        node = self.generic_visit(node)
        node.name = "FUNC"
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: D401
        if isinstance(node.value, str):
            value: Any = "STR"
        elif isinstance(node.value, (int, float, complex)):
            value = "NUM"
        elif isinstance(node.value, bytes):
            value = "BYTES"
        elif isinstance(node.value, bool):
            value = "BOOL"
        else:
            value = node.value
        return ast.copy_location(ast.Constant(value=value), node)

    def visit_keyword(self, node: ast.keyword) -> ast.AST:  # noqa: D401
        node = self.generic_visit(node)
        if node.arg is not None:
            node.arg = "KW"
        return node


class _DocstringPruner(ast.NodeTransformer):
    """Remove leading docstrings so hashes focus on executable statements."""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # noqa: D401
        node = self.generic_visit(node)
        if node.body and _is_docstring(node.body[0]):
            node.body = node.body[1:]
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:  # noqa: D401
        node = self.generic_visit(node)
        if node.body and _is_docstring(node.body[0]):
            node.body = node.body[1:]
        return node


def detect_duplicate_code(
    result: RunResult,
    config: DuplicateDetectionConfig,
) -> list[dict[str, Any]]:
    """Return duplicate clusters derived from AST hashing and heuristics."""
    if not config.enabled:
        return []

    clusters: list[DuplicateCluster] = []
    if config.ast_enabled:
        clusters.extend(_detect_ast_duplicates(result, config))
    if config.cross_diagnostics:
        clusters.extend(_detect_diagnostic_duplicates(result, config))

    return [
        {
            "kind": cluster.kind,
            "fingerprint": cluster.fingerprint,
            "summary": cluster.summary,
            "occurrences": [
                {
                    "file": occurrence.file,
                    "line": occurrence.line,
                    "function": occurrence.function,
                    "size": occurrence.size,
                    "snippet": occurrence.snippet,
                }
                for occurrence in cluster.occurrences
            ],
        }
        for cluster in clusters
    ]


def _detect_ast_duplicates(
    result: RunResult,
    config: DuplicateDetectionConfig,
) -> Iterable[DuplicateCluster]:
    root_path = result.root.resolve()
    occurrences: dict[str, list[DuplicateOccurrence]] = {}
    normalizer = _CanonicalisingTransformer()
    pruner = _DocstringPruner()

    for path in result.files:
        if path.suffix != ".py":
            continue
        rel_path = _relative_path(root_path, path)
        if not config.ast_include_tests and _looks_like_test_path(rel_path):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue
        module = cast(ast.Module, pruner.visit(module))
        source_lines = source.splitlines()
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(node.body)
            if not body:
                continue
            candidate_body = [copy.deepcopy(stmt) for stmt in body]
            if not candidate_body:
                continue
            segment = ast.Module(body=candidate_body, type_ignores=[])
            segment = cast(ast.Module, normalizer.visit(ast.fix_missing_locations(segment)))
            dump = ast.dump(segment, include_attributes=False, annotate_fields=True)

            node_size = _node_line_span(node)
            if node_size is not None and node_size < config.ast_min_lines:
                continue
            nodes_count = sum(1 for _ in ast.walk(segment))
            if nodes_count < config.ast_min_nodes:
                continue

            fingerprint = hashlib.sha1(  # noqa: S324 - not used for security
                dump.encode("utf-8"),
                usedforsecurity=False,
            ).hexdigest()
            line = getattr(node, "lineno", None)
            snippet = _snippet_from_lines(source_lines, line, node_size)
            occurrence = DuplicateOccurrence(
                file=rel_path,
                line=line,
                function=getattr(node, "name", None),
                size=node_size,
                snippet=snippet,
            )
            bucket = occurrences.setdefault(fingerprint, [])
            if occurrence not in bucket:
                bucket.append(occurrence)

    for fingerprint, bucket in occurrences.items():
        if len(bucket) < 2:
            continue
        unique_keys = {(entry.file, entry.line) for entry in bucket}
        if len(unique_keys) < 2:
            continue
        size_hint = bucket[0].size or 0
        summary = _format_ast_summary(size_hint, len(bucket))
        yield DuplicateCluster(
            kind="ast",
            fingerprint=fingerprint,
            summary=summary,
            occurrences=tuple(bucket),
        )


def _detect_diagnostic_duplicates(
    result: RunResult,
    config: DuplicateDetectionConfig,
) -> Iterable[DuplicateCluster]:
    root_path = result.root.resolve()
    clusters: dict[tuple[str, str, str], list[DuplicateOccurrence]] = {}

    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            key = _diagnostic_key(diag)
            if key is None:
                continue
            tool_name, code, message = key
            rel_path = _relative_path(root_path, Path(diag.file) if diag.file else root_path)
            occurrence = DuplicateOccurrence(
                file=rel_path,
                line=diag.line,
                function=diag.function,
                size=None,
                snippet=message,
            )
            bucket = clusters.setdefault((tool_name, code, message), [])
            if occurrence not in bucket:
                bucket.append(occurrence)

    for (tool_name, code, message), bucket in clusters.items():
        unique_files = {entry.file for entry in bucket}
        if len(unique_files) < config.cross_message_threshold:
            continue
        summary = _format_diagnostic_summary(tool_name, code, message, len(unique_files))
        fingerprint = hashlib.sha1(  # noqa: S324 - not used for security
            f"{tool_name}|{code}|{message}".encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        yield DuplicateCluster(
            kind="diagnostic",
            fingerprint=fingerprint,
            summary=summary,
            occurrences=tuple(bucket),
        )


def _diagnostic_key(diag: Diagnostic) -> tuple[str, str, str] | None:
    message = diag.message.splitlines()[0].strip()
    if not message:
        return None
    tool = (diag.tool or "").lower() or "unknown"
    code = (diag.code or "-").upper()
    return tool, code, message


def _format_ast_summary(size_hint: int, count: int) -> str:
    size_part = f"~{size_hint} line" + ("s" if size_hint != 1 else "") if size_hint else "multiple lines"
    return f"Duplicate block ({size_part}) detected across {count} locations"


def _format_diagnostic_summary(tool: str, code: str, message: str, files: int) -> str:
    return f"Repeated {tool}:{code} diagnostic '{message}' across {files} files"


def _relative_path(root: Path, path: Path) -> str:
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()


def _node_line_span(node: ast.AST) -> int | None:
    start = getattr(node, "lineno", None)
    if start is None:
        return None
    end = getattr(node, "end_lineno", None)
    if end is None:
        end = start
        for child in ast.walk(node):
            child_end = getattr(child, "end_lineno", None)
            child_start = getattr(child, "lineno", None)
            if child_end is not None:
                end = max(end, child_end)
            elif child_start is not None:
                end = max(end, child_start)
    return max(0, end - start + 1)


def _snippet_from_lines(lines: Sequence[str], start: int | None, size: int | None) -> str | None:
    if start is None or start <= 0 or start > len(lines):
        return None
    count = min(size or 3, 3)
    slice_end = min(start - 1 + count, len(lines))
    snippet = " ".join(entry.strip() for entry in lines[start - 1 : slice_end])
    return snippet or None


def _is_docstring(node: ast.AST) -> bool:
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        return isinstance(node.value.value, str)
    return False


def _looks_like_test_path(path: str) -> bool:
    normalized = path.lower()
    return normalized.startswith("tests/") or "/tests/" in normalized
