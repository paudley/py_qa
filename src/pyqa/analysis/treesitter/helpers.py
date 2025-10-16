# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tree-sitter helper utilities shared across analysis components."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

from tree_sitter import Node as TSNode


def tree_node_name(node: TSNode | None) -> str | None:
    """Determine a normalised display name for the supplied node.

    Args:
        node: Tree-sitter node whose name should be extracted.

    Returns:
        str | None: Normalised node name or ``None`` when unavailable.
    """

    if node is None:
        return None

    extractor = getattr(node, "child_by_field_name", None)
    if callable(extractor):
        name_node = extractor("name")
        raw = getattr(name_node, "text", None)
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        if isinstance(raw, str):
            return raw
    text = getattr(node, "text", None)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def iter_tree_nodes(node: TSNode) -> Iterator[TSNode]:
    """Visit nodes in depth-first order starting from the supplied node.

    Args:
        node: Root node used as the traversal starting point.

    Returns:
        Iterator[TSNode]: Iterator yielding nodes in depth-first order.
    """

    return _iter_tree_nodes_generator(node)


def iter_tree_nodes_with_depth(node: TSNode, depth: int = 0) -> Iterator[tuple[TSNode, int]]:
    """Visit nodes and their depth in depth-first order.

    Args:
        node: Root node used as the traversal starting point.
        depth: Current depth supplied during recursion.

    Returns:
        Iterator[tuple[TSNode, int]]: Iterator yielding node-depth pairs.
    """

    return _iter_tree_nodes_with_depth_generator(node, depth)


def _iter_tree_nodes_generator(node: TSNode) -> Iterator[TSNode]:
    """Provide nodes for a depth-first traversal.

    Args:
        node: Root node used as the traversal starting point.

    Returns:
        Iterator[TSNode]: Generator yielding nodes in depth-first order.
    Yields:
        TSNode: Nodes visited in depth-first order.
    """

    yield node
    children = getattr(node, "children", None)
    if not children:
        return
    for child in children:
        if child is not None:
            yield from _iter_tree_nodes_generator(child)


def _iter_tree_nodes_with_depth_generator(
    node: TSNode,
    depth: int = 0,
) -> Iterator[tuple[TSNode, int]]:
    """Provide nodes and their depth for a depth-first traversal.

    Args:
        node: Root node used as the traversal starting point.
        depth: Current depth supplied during recursion.

    Returns:
        Iterator[tuple[TSNode, int]]: Generator yielding node-depth pairs.
    Yields:
        tuple[TSNode, int]: Node-depth pairs visited in depth-first order.
    """

    yield node, depth
    children = getattr(node, "children", None)
    if not children:
        return
    for child in children:
        if child is not None:
            yield from _iter_tree_nodes_with_depth_generator(child, depth + 1)


def node_row_span(node: TSNode) -> tuple[int | None, int | None]:
    """Determine 1-based (start, end) line numbers for the node when available.

    Args:
        node: Tree-sitter node whose line span should be reported.

    Returns:
        tuple[int | None, int | None]: One-based start and end row values.
    """

    start_point = getattr(node, "start_point", None)
    end_point = getattr(node, "end_point", None)
    start_row = start_point[0] + 1 if start_point else None
    end_row = end_point[0] + 1 if end_point else None
    return start_row, end_row


def node_contains_line(node: TSNode, line: int) -> bool:
    """Check whether the node spans the requested line.

    Args:
        node: Tree-sitter node to inspect for the requested line.
        line: One-based line number queried against the node span.

    Returns:
        bool: ``True`` when the line lies within the node span.
    """

    start_row, end_row = node_row_span(node)
    return bool(start_row is not None and end_row is not None and start_row <= line <= end_row)


_PYTHON_NAMED_SCOPE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "function_definition",
        "class_definition",
    }
)


def nearest_python_named_scope(node: TSNode, line: int) -> str | None:
    """Identify the innermost named Python scope covering the line.

    Args:
        node: Root node of the Python syntax tree.
        line: One-based line number requesting context.

    Returns:
        str | None: Name of the innermost scope or ``None`` when absent.
    """

    best_line = -1
    best_name: str | None = None
    for current in iter_tree_nodes(node):
        node_type = getattr(current, "type", "")
        if node_type not in _PYTHON_NAMED_SCOPE_TYPES:
            continue
        if not node_contains_line(current, line):
            continue
        start_row, _ = node_row_span(current)
        if start_row is None or start_row < best_line:
            continue
        name = tree_node_name(current)
        if name:
            best_line = start_row
            best_name = name
    return best_name


def nearest_python_generic_node(node: TSNode, line: int) -> TSNode | None:
    """Identify the deepest node covering the line when no named scope exists.

    Args:
        node: Root node of the Python syntax tree.
        line: One-based line number requesting context.

    Returns:
        TSNode | None: Deepest covering node or ``None`` when absent.
    """

    best_node: TSNode | None = None
    best_line = -1
    for current in iter_tree_nodes(node):
        if not node_contains_line(current, line):
            continue
        start_row, _ = node_row_span(current)
        if start_row is None or start_row < best_line:
            continue
        best_line = start_row
        best_node = current
    return best_node


__all__ = [
    "iter_tree_nodes",
    "iter_tree_nodes_with_depth",
    "nearest_python_generic_node",
    "nearest_python_named_scope",
    "node_contains_line",
    "node_row_span",
    "tree_node_name",
]
