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
from pathlib import Path
from collections.abc import Iterable

PACKAGE_ROOT = Path("src/pyqa").resolve()
PACKAGE_PREFIX = "pyqa"


def _module_name_from_path(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([PACKAGE_PREFIX, *parts]) if parts else PACKAGE_PREFIX


def _resolve_relative(module: str | None, level: int, current: str) -> str | None:
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
    graph: dict[str, set[str]] = defaultdict(set)
    for path in root.rglob("*.py"):
        module_name = _module_name_from_path(path)
        graph[module_name] |= _collect_dependencies(path, module_name)
    return {module: sorted(deps) for module, deps in sorted(graph.items())}


def _dependency_histogram(graph: dict[str, Iterable[str]]) -> dict[str, int]:
    return {module: len(list(deps)) for module, deps in graph.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reorg/artifacts/phase0/pyqa_dependency_graph.json"),
        help="Path to the JSON file that will store the dependency graph.",
    )
    args = parser.parse_args()

    graph = build_graph(PACKAGE_ROOT)
    histogram = _dependency_histogram(graph)

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "package_root": str(PACKAGE_ROOT),
        "module_count": len(graph),
        "graph": graph,
        "dependency_histogram": histogram,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
