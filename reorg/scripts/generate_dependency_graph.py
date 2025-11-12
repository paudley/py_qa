# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Generate a module dependency graph for the ``pyqa`` package.

The script walks ``src/pyqa`` and records direct intra-package imports
encountered in each module.  The result is written as JSON containing an
adjacency list and a simple histogram that counts how many dependencies
each module declares.

Example usage::

    python reorg/scripts/generate_dependency_graph.py \
        --output reorg/artifacts/phase0/pyqa_dependency_graph.json

"""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = (REPO_ROOT / "src/pyqa").resolve()
PACKAGE_PREFIX = "pyqa"
_INIT_FILENAME = "__init__"


def _module_name_from_path(path: Path) -> str:
    """Return the fully-qualified module name for ``path``.

    Args:
        path: Absolute path to a Python module residing beneath ``PACKAGE_ROOT``.

    Returns:
        str: Dotted module name using the project prefix.
    """

    relative = path.relative_to(PACKAGE_ROOT)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == _INIT_FILENAME:
        parts = parts[:-1]
    return ".".join([PACKAGE_PREFIX, *parts]) if parts else PACKAGE_PREFIX


def _resolve_relative(module: str | None, level: int, current: str) -> str | None:
    """Resolve a relative import target to an absolute module path.

    Args:
        module: Optional module suffix present in the import statement.
        level: Count of leading dots describing the relative depth.
        current: Fully-qualified module issuing the import.

    Returns:
        str | None: Absolute module name when the resolution succeeds; otherwise
        ``None`` when the relative import escapes the package boundary.
    """

    base_parts = current.split(".")[:-1]
    if level > len(base_parts) + 1:
        return None
    target_parts = base_parts[: len(base_parts) + 1 - level]
    if module:
        target_parts.extend(module.split("."))
    if not target_parts:
        return None
    return ".".join(target_parts)


def _collect_dependencies(path: Path, module_name: str) -> set[str]:
    """Return intra-package dependency names discovered in ``path``.

    Args:
        path: Absolute path to the module being inspected.
        module_name: Fully-qualified name for ``path``.

    Returns:
        set[str]: Unique set of modules imported from inside the project.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PACKAGE_PREFIX):
                    deps.add(alias.name.split(" as ")[0])
        elif isinstance(node, ast.ImportFrom):
            target = node.module
            if node.level:
                target = _resolve_relative(target, node.level, module_name)
            if target and target.startswith(PACKAGE_PREFIX):
                deps.add(target)
    deps.discard(module_name)
    return deps


def build_graph(root: Path) -> dict[str, list[str]]:
    """Return adjacency list mapping modules to intra-package dependencies.

    Args:
        root: Repository root containing the ``pyqa`` package.

    Returns:
        dict[str, list[str]]: Sorted mapping from module name to dependency
        names.
    """

    graph: dict[str, set[str]] = defaultdict(set)
    for path in root.rglob("*.py"):
        module_name = _module_name_from_path(path)
        graph[module_name] |= _collect_dependencies(path, module_name)
    return {module: sorted(deps) for module, deps in sorted(graph.items())}


def _dependency_histogram(graph: Mapping[str, Sequence[str]]) -> dict[str, int]:
    """Return mapping of modules to dependency counts.

    Args:
        graph: Adjacency list describing intra-package dependencies.

    Returns:
        dict[str, int]: Count of dependencies for each module present in
        ``graph``.
    """

    return {module: len(deps) for module, deps in graph.items()}


def _relative_to_repo(path: Path) -> str:
    """Return ``path`` relative to the repository root when possible."""

    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main(arguments: Sequence[str] | None = None) -> None:
    """Generate the dependency graph JSON artefact.

    Args:
        arguments: Optional CLI arguments supplied by external callers. When
            ``None`` the active ``sys.argv`` values are used.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reorg/artifacts/phase0/pyqa_dependency_graph.json"),
        help="Path to the JSON file that will store the dependency graph.",
    )
    args = parser.parse_args(arguments)

    graph = build_graph(PACKAGE_ROOT)
    histogram = _dependency_histogram(graph)

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "package_root": _relative_to_repo(PACKAGE_ROOT),
        "module_count": len(graph),
        "graph": graph,
        "dependency_histogram": histogram,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
