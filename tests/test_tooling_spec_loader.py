# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Regression tests for the standalone tooling specification package."""

from __future__ import annotations

import json
from pathlib import Path

from tooling_spec.catalog import CatalogSnapshot, StrategyDefinition, ToolCatalogLoader, ToolDefinition


def _write_json(path: Path, payload: object) -> None:
    """Serialize ``payload`` as formatted JSON into ``path``."""

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_tooling_spec_loader_builds_snapshot(tmp_path: Path) -> None:
    """The standalone loader should materialise catalog data without pyqa imports."""

    catalog_root = tmp_path / "catalog"
    strategies_dir = catalog_root / "strategies"
    strategies_dir.mkdir(parents=True)

    _write_json(
        strategies_dir / "echo.json",
        {
            "schemaVersion": "1.0.0",
            "id": "echo_command",
            "type": "command",
            "implementation": "tests.tooling.sample_strategies.command_builder",
            "config": {},
        },
    )
    _write_json(
        catalog_root / "tool.json",
        {
            "schemaVersion": "1.0.0",
            "name": "echo-tool",
            "description": "Lightweight tool defined via tooling_spec.",
            "languages": ["python"],
            "phase": "lint",
            "actions": [
                {
                    "name": "lint",
                    "command": {
                        "strategy": "echo_command",
                        "config": {"args": ["echo", "spec"]},
                    },
                },
            ],
        },
    )

    schema_root = tmp_path / "schema"
    schema_root.mkdir()
    (schema_root / "tool_definition.schema.json").write_text(
        (Path(__file__).resolve().parents[1] / "tooling" / "schema" / "tool_definition.schema.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (schema_root / "strategy_definition.schema.json").write_text(
        (Path(__file__).resolve().parents[1] / "tooling" / "schema" / "strategy_definition.schema.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)
    snapshot = loader.load_snapshot()

    assert isinstance(snapshot, CatalogSnapshot)
    assert [tool.name for tool in snapshot.tools] == ["echo-tool"]
    strategy = snapshot.strategy("echo_command")
    assert strategy({"args": ["echo", "spec"]}) is not None
    tool_definition = snapshot.tools[0]
    assert isinstance(tool_definition, ToolDefinition)
    assert tool_definition.to_dict()["name"] == "echo-tool"
    strategies = snapshot.strategies
    assert isinstance(strategies[0], StrategyDefinition)
