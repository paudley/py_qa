# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Architecture assertions for the CLI package."""

from __future__ import annotations

from pathlib import Path

from reorg.scripts.generate_dependency_graph import build_graph

PACKAGE_ROOT = Path("src/pyqa").resolve()


def test_cli_does_not_depend_on_execution_package() -> None:
    """CLI modules must not depend on the legacy ``pyqa.execution`` package."""

    graph = build_graph(PACKAGE_ROOT)
    offenders: dict[str, list[str]] = {}
    for module, deps in graph.items():
        if not module.startswith("pyqa.cli."):
            continue
        blocked = [dep for dep in deps if dep.startswith("pyqa.execution.")]
        if blocked:
            offenders[module] = blocked
    assert not offenders, f"CLI modules referencing pyqa.execution detected: {offenders}"
