from __future__ import annotations

import json
from pathlib import Path

from reorg.scripts.generate_dependency_graph import build_graph


PACKAGE_ROOT = Path("src/pyqa").resolve()


def test_dependency_graph_contains_pyqa_modules(tmp_path: Path) -> None:
    graph = build_graph(PACKAGE_ROOT)
    assert graph, "dependency graph must include modules"
    sample_module, deps = next(iter(graph.items()))
    assert sample_module.startswith("pyqa")
    for dep in deps:
        assert dep.startswith("pyqa")

    payload = {
        "graph": graph,
        "module_count": len(graph),
    }
    output = tmp_path / "graph.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["module_count"] == len(graph)

