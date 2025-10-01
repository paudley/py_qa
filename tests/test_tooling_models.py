# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Unit tests exercising catalog model helpers and parsing primitives."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyqa.tooling import CatalogIntegrityError
from pyqa.tooling.catalog.model_actions import actions_array
from pyqa.tooling.catalog.model_documentation import documentation_entry
from pyqa.tooling.catalog.model_tool import ToolDefinition


def test_tool_definition_parses_augmented_mapping(tmp_path: Path) -> None:
    """``ToolDefinition.from_mapping`` should materialise rich metadata."""

    catalog_root = tmp_path / "catalog"
    catalog_root.mkdir()
    docs_path = catalog_root / "docs" / "help.txt"
    docs_path.parent.mkdir(parents=True)
    docs_path.write_text("catalog help", encoding="utf-8")

    source = catalog_root / "example_tool.json"
    source.write_text("{}", encoding="utf-8")

    mapping = {
        "schemaVersion": "1.0.0",
        "name": "example-tool",
        "aliases": ["example"],
        "description": "Example tool for unit testing.",
        "languages": ["python"],
        "tags": ["lint"],
        "phase": "lint",
        "before": [],
        "after": ["other-tool"],
        "fileExtensions": [".py"],
        "configFiles": ["pyproject.toml"],
        "defaultEnabled": True,
        "autoInstall": False,
        "runtime": {
            "type": "python",
            "package": "example",
            "versionCommand": ["example", "--version"],
            "binaries": {"example": "bin/example"},
            "install": {
                "strategy": "pip",
                "config": {"packages": ["example"]},
            },
        },
        "diagnostics": {
            "dedupe": {"E100": "ruff"},
            "severityMapping": {"info": "low"},
        },
        "suppressions": {
            "tests": ["tests/**"],
            "general": [".github/**"],
            "duplicates": ["duplicate-pattern"],
        },
        "documentation": {
            "help": {"path": "docs/help.txt"},
        },
        "options": [
            {
                "name": "severity",
                "type": "string",
                "description": "Severity threshold.",
                "default": "warning",
                "choices": ["info", "warning", "error"],
                "aliases": [],
                "cli": {"flag": "--severity", "shortFlag": "-s"},
            },
        ],
        "actions": [
            {
                "name": "lint",
                "description": "Run linting",
                "appendFiles": False,
                "isFix": True,
                "ignoreExit": False,
                "timeoutSeconds": 5,
                "env": {"EXAMPLE_FLAG": "1"},
                "filters": ["*.py"],
                "command": {
                    "strategy": "command.strategy",
                    "config": {},
                },
                "parser": {
                    "strategy": "parser.strategy",
                    "config": {},
                },
            },
        ],
    }

    tool = ToolDefinition.from_mapping(mapping, source=source, catalog_root=catalog_root)

    assert tool.name == "example-tool"
    assert tool.aliases == ("example",)
    assert tool.metadata.files.file_extensions == (".py",)
    assert tool.runtime is not None
    assert tool.runtime.kind == "python"
    assert tool.actions[0].append_files is False
    assert tool.actions[0].is_fix is True
    assert tool.options[0].choices == ("info", "warning", "error")
    assert tool.diagnostics_bundle.diagnostics is not None
    assert tool.diagnostics_bundle.diagnostics.dedupe["E100"] == "ruff"
    assert tool.diagnostics_bundle.suppressions is not None
    assert tool.diagnostics_bundle.suppressions.general == (".github/**",)
    assert tool.documentation is not None
    assert tool.documentation.help is not None
    assert tool.documentation.help.content == "catalog help"


def test_documentation_entry_resolves_relative_to_source(tmp_path: Path) -> None:
    """Documentation loader should fall back to the source directory."""

    catalog_root = tmp_path / "catalog"
    catalog_root.mkdir()
    source = tmp_path / "tool.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    doc_rel_path = Path("docs/usage.txt")
    doc_file = source.parent / doc_rel_path
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("relative documentation", encoding="utf-8")

    entry = documentation_entry(
        {"path": str(doc_rel_path)},
        context="tool.documentation.help",
        catalog_root=catalog_root,
        source=source,
    )

    assert entry.content == "relative documentation"


def test_actions_array_rejects_empty_sequences() -> None:
    """The actions helper should raise when populated with an empty list."""

    with pytest.raises(CatalogIntegrityError):
        actions_array([], key="actions", context="tool.actions")
