# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the catalog-driven tooling loader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pyqa.tooling.loader import (
    CatalogIntegrityError,
    CatalogValidationError,
    JSONValue,
    ToolCatalogLoader,
)


def _write_json(path: Path, payload: JSONValue) -> None:
    """Serialize *payload* as formatted JSON to *path*.

    Args:
        path: Destination file path.
        payload: JSON-serializable payload to write.

    """
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_loader_reads_tool_and_strategy_catalog(tmp_path: Path, schema_root: Path) -> None:
    """Loader should parse well-formed tool and strategy definitions."""
    catalog_root = tmp_path / "catalog"
    strategies_dir = catalog_root / "strategies"
    strategies_dir.mkdir(parents=True)

    _write_json(
        strategies_dir / "sample_command.json",
        {
            "schemaVersion": "1.0.0",
            "id": "sample_command",
            "type": "command",
            "description": "Command strategy used only for tests.",
            "implementation": "tests.tooling.sample_strategies.command_builder",
            "config": {
                "args": {
                    "type": "array",
                    "description": "Command arguments appended during execution.",
                },
            },
        },
    )
    _write_json(
        strategies_dir / "sample_parser.json",
        {
            "schemaVersion": "1.0.0",
            "id": "sample_parser",
            "type": "parser",
            "description": "Parser strategy used only for tests.",
            "implementation": "tests.tooling.sample_strategies.parser_factory",
            "config": {
                "id": {
                    "type": "string",
                    "description": "Optional identifier for testing purposes.",
                },
            },
        },
    )
    _write_json(
        catalog_root / "_python_defaults.json",
        {
            "schemaVersion": "1.0.0",
            "suppressions": {"tests": ["tests/**"], "general": [".github/**"], "duplicates": []},
        },
    )
    _write_json(
        catalog_root / "sample_tool.json",
        {
            "schemaVersion": "1.0.0",
            "name": "sample-tool",
            "description": "Synthetic tool used within loader tests.",
            "extends": ["python_defaults"],
            "languages": ["python"],
            "phase": "lint",
            "actions": [
                {
                    "name": "lint",
                    "command": {
                        "strategy": "sample_command",
                        "config": {"args": ["echo", "hello"]},
                    },
                    "parser": {
                        "strategy": "sample_parser",
                        "config": {"id": "lint"},
                    },
                },
            ],
        },
    )

    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)
    tool_defs = loader.load_tool_definitions()
    strategy_defs = loader.load_strategy_definitions()

    assert len(tool_defs) == 1
    assert tool_defs[0].name == "sample-tool"
    assert tool_defs[0].actions[0].command.reference.strategy == "sample_command"
    suppressions = tool_defs[0].diagnostics_bundle.suppressions
    assert suppressions is not None
    assert suppressions.tests == ("tests/**",)
    assert suppressions.general == (".github/**",)
    assert len(strategy_defs) == 2
    assert {definition.identifier for definition in strategy_defs} == {
        "sample_command",
        "sample_parser",
    }


def test_loader_rejects_mismatched_schema_versions(tmp_path: Path, schema_root: Path) -> None:
    """Loader should raise when encountering unsupported schema versions."""
    catalog_root = tmp_path / "catalog"
    catalog_root.mkdir()
    _write_json(
        catalog_root / "invalid_tool.json",
        {
            "schemaVersion": "999.0.0",
            "name": "broken-tool",
            "description": "Invalid schema version.",
            "languages": ["python"],
            "phase": "lint",
            "actions": [
                {
                    "name": "lint",
                    "command": {"strategy": "noop"},
                },
            ],
        },
    )

    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)

    with pytest.raises(CatalogValidationError):
        loader.load_tool_definitions()


def test_loader_validates_strategy_imports(tmp_path: Path, schema_root: Path) -> None:
    """Loader should surface errors for unresolvable strategy implementations."""
    catalog_root = tmp_path / "catalog"
    strategies_dir = catalog_root / "strategies"
    strategies_dir.mkdir(parents=True)

    _write_json(
        strategies_dir / "invalid_strategy.json",
        {
            "schemaVersion": "1.0.0",
            "id": "broken_strategy",
            "type": "command",
            "implementation": "tests.tooling.missing.module",
        },
    )

    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)

    with pytest.raises(CatalogIntegrityError):
        loader.load_strategy_definitions()


def test_loader_rejects_schema_mismatches(tmp_path: Path, schema_root: Path) -> None:
    """Loader should report validation errors when schema rules are violated."""
    catalog_root = tmp_path / "catalog"
    catalog_root.mkdir()
    _write_json(
        catalog_root / "invalid_tool.json",
        {
            "schemaVersion": "1.0.0",
            "name": "missing-fields",
            "description": "Violates required properties.",
            "phase": "lint",
            "actions": [],
        },
    )

    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)

    with pytest.raises(CatalogValidationError):
        loader.load_tool_definitions()


def test_loader_merges_fragments(tmp_path: Path, schema_root: Path) -> None:
    """Fragment data should merge into tool definitions with overrides applied."""
    catalog_root = tmp_path / "catalog"
    strategies_dir = catalog_root / "strategies"
    strategies_dir.mkdir(parents=True)

    _write_json(
        strategies_dir / "noop_command.json",
        {
            "schemaVersion": "1.0.0",
            "id": "noop_command",
            "type": "command",
            "implementation": "tests.tooling.sample_strategies.command_builder",
        },
    )
    _write_json(
        catalog_root / "_python_common.json",
        {
            "description": "Common Python lint tool.",
            "languages": ["python"],
            "phase": "lint",
            "runtime": {
                "type": "python",
                "minVersion": "3.8",
            },
            "actions": [
                {
                    "name": "lint",
                    "command": {"strategy": "noop_command"},
                },
            ],
        },
    )
    _write_json(
        catalog_root / "tool.json",
        {
            "schemaVersion": "1.0.0",
            "name": "py-common",
            "extends": ["python_common"],
            "description": "Specialized Python tool.",
            "runtime": {
                "minVersion": "3.12",
                "maxVersion": "3.13",
            },
        },
    )

    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)
    tool_defs = loader.load_tool_definitions()

    assert len(tool_defs) == 1
    tool = tool_defs[0]
    assert tool.languages == ("python",)
    assert tool.phase == "lint"
    assert tool.runtime is not None
    assert tool.runtime.kind == "python"
    assert tool.runtime.min_version == "3.12"
    assert tool.runtime.max_version == "3.13"
    assert tool.actions[0].command.reference.strategy == "noop_command"


def test_loader_errors_on_unknown_fragment(tmp_path: Path, schema_root: Path) -> None:
    """Referencing a missing fragment should raise an integrity error."""
    catalog_root = tmp_path / "catalog"
    catalog_root.mkdir()
    _write_json(
        catalog_root / "tool.json",
        {
            "schemaVersion": "1.0.0",
            "name": "unknown-fragment",
            "description": "Attempts to use an undefined fragment.",
            "languages": ["python"],
            "phase": "lint",
            "extends": ["does_not_exist"],
            "actions": [
                {
                    "name": "lint",
                    "command": {"strategy": "noop"},
                },
            ],
        },
    )

    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)

    with pytest.raises(CatalogIntegrityError):
        loader.load_tool_definitions()


def test_loader_generates_checksum_and_fragments(tmp_path: Path, schema_root: Path) -> None:
    """Snapshot loading should include fragments and provide deterministic checksum."""
    catalog_root = tmp_path / "catalog"
    strategies_dir = catalog_root / "strategies"
    strategies_dir.mkdir(parents=True)

    _write_json(
        strategies_dir / "noop_command.json",
        {
            "schemaVersion": "1.0.0",
            "id": "noop_command",
            "type": "command",
            "implementation": "tests.tooling.sample_strategies.command_builder",
        },
    )
    _write_json(
        catalog_root / "_shared.json",
        {
            "configFiles": ["pyproject.toml"],
        },
    )
    _write_json(
        catalog_root / "tool.json",
        {
            "schemaVersion": "1.0.0",
            "name": "checksum-tool",
            "description": "Tool used to validate checksum generation.",
            "languages": ["python"],
            "phase": "lint",
            "extends": ["shared"],
            "actions": [
                {
                    "name": "lint",
                    "command": {"strategy": "noop_command"},
                },
            ],
        },
    )

    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)
    snapshot = loader.load_snapshot()
    fragment_paths = {fragment.source for fragment in snapshot.fragments}
    fragment_names = {fragment.name for fragment in snapshot.fragments}

    assert snapshot.tools[0].name == "checksum-tool"
    assert snapshot.tools[0].config_files == ("pyproject.toml",)
    assert snapshot.strategies[0].identifier == "noop_command"
    assert len(snapshot.fragments) == 1
    assert fragment_paths == {catalog_root / "_shared.json"}
    assert fragment_names == {"shared"}

    expected_paths = (
        (catalog_root / "_shared.json"),
        (catalog_root / "tool.json"),
        (strategies_dir / "noop_command.json"),
    )
    hasher = hashlib.sha256()
    for path in sorted(expected_paths):
        rel = path.relative_to(catalog_root).as_posix().encode("utf-8")
        hasher.update(rel)
        hasher.update(b"\0")
        hasher.update(path.read_bytes())

    assert snapshot.checksum == hasher.hexdigest()


def test_loader_validates_entire_catalog(schema_root: Path) -> None:
    """Real catalog should load without validation errors."""
    catalog_root = Path(__file__).resolve().parents[1] / "tooling" / "catalog"
    loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)
    snapshot = loader.load_snapshot()
    assert snapshot.tools
    assert snapshot.strategies
