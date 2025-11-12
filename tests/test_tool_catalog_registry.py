# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for integrating catalog snapshots with the runtime tool registry."""

from __future__ import annotations

import json
from pathlib import Path

from pyqa.catalog import CatalogSnapshot, ToolCatalogLoader
from pyqa.config import Config
from pyqa.tools.base import ToolContext
from pyqa.tools.builtin_registry import (
    clear_catalog_cache,
    initialize_registry,
    register_catalog_tools,
)
from pyqa.tools.registry import ToolRegistry


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_initialize_registry_catalog(tmp_path: Path, schema_root: Path) -> None:
    """Catalog-backed registration should populate tools from JSON definitions."""
    clear_catalog_cache()
    catalog_root = tmp_path / "catalog"
    strategies_dir = catalog_root / "strategies"
    strategies_dir.mkdir(parents=True)

    _write_json(
        strategies_dir / "sample_command.json",
        {
            "schemaVersion": "1.0.0",
            "id": "sample_command",
            "type": "command",
            "implementation": "tests.tooling.sample_strategies.command_builder",
        },
    )
    _write_json(
        catalog_root / "tool.json",
        {
            "schemaVersion": "1.0.0",
            "name": "sample-tool",
            "description": "Synthetic tool defined in catalog.",
            "languages": ["python"],
            "phase": "lint",
            "actions": [
                {
                    "name": "lint",
                    "command": {
                        "strategy": "sample_command",
                        "config": {"args": ["echo", "hi"]},
                    },
                },
            ],
        },
    )

    registry = ToolRegistry()
    snapshot = initialize_registry(
        registry=registry,
        catalog_root=catalog_root,
        schema_root=schema_root,
    )

    assert snapshot is not None
    assert [tool.name for tool in snapshot.tools] == ["sample-tool"]
    assert list(registry.keys()) == ["sample-tool"], registry._tools
    tool = registry.get("sample-tool")
    context = ToolContext(cfg=Config(), root=tmp_path)
    command = tool.actions[0].build_command(context)
    assert command[-2:] == ["echo", "hi"]


def test_initialize_registry_real_catalog(schema_root: Path, tmp_path: Path) -> None:
    """The real catalog should register known tools like Ruff, Black, and Mypy."""
    clear_catalog_cache()
    catalog_root = Path(__file__).resolve().parents[1] / "tooling" / "catalog"
    registry = ToolRegistry()
    snapshot = initialize_registry(
        registry=registry,
        catalog_root=catalog_root,
        schema_root=schema_root,
    )

    assert snapshot is not None
    expected_tools = {
        "actionlint",
        "bandit",
        "black",
        "cargo-clippy",
        "cargo-fmt",
        "cpplint",
        "dockerfilelint",
        "dotenv-linter",
        "eslint",
        "gofmt",
        "golangci-lint",
        "gts",
        "hadolint",
        "isort",
        "kube-linter",
        "luacheck",
        "lualint",
        "mdformat",
        "mypy",
        "perlcritic",
        "perltidy",
        "prettier",
        "pylint",
        "pyright",
        "pyupgrade",
        "remark-lint",
        "ruff",
        "ruff-format",
        "selene",
        "shfmt",
        "speccy",
        "sqlfluff",
        "stylelint",
        "tombi",
        "tsc",
        "yamllint",
    }
    assert expected_tools.issubset(set(registry.keys()))

    context = ToolContext(cfg=Config(), root=tmp_path)

    ruff_cmd = registry.get("ruff").actions[0].build_command(context)
    assert ruff_cmd[:2] == ["ruff", "check"]

    black_cmd = registry.get("black").actions[0].build_command(context)
    assert black_cmd[0] == "black"

    mypy_cmd = registry.get("mypy").actions[0].build_command(context)
    assert mypy_cmd[:3] == ["mypy", "--output", "json"]

    isort_cmd = registry.get("isort").actions[0].build_command(context)
    assert isort_cmd[0] == "isort"

    pylint_cmd = registry.get("pylint").actions[0].build_command(context)
    assert pylint_cmd[:2] == ["pylint", "--output-format=json"]

    pyright_cmd = registry.get("pyright").actions[0].build_command(context)
    assert pyright_cmd[:2] == ["pyright", "--outputjson"]

    eslint_cmd = registry.get("eslint").actions[0].build_command(context)
    assert eslint_cmd[:3] == ["eslint", "--format", "json"]

    prettier_cmd = registry.get("prettier").actions[0].build_command(context)
    assert prettier_cmd[:2] == ["prettier", "--write"]

    actionlint_cmd = registry.get("actionlint").actions[0].build_command(context)
    assert "actionlint" in Path(actionlint_cmd[0]).name

    stylelint_cmd = registry.get("stylelint").actions[0].build_command(context)
    assert stylelint_cmd[0] == "stylelint"

    kube_cmd = registry.get("kube-linter").actions[0].build_command(context)
    assert kube_cmd[:3] == ["kube-linter", "lint", "--format"]

    docker_cmd = registry.get("dockerfilelint").actions[0].build_command(context)
    assert docker_cmd[0] == "dockerfilelint"

    documentation = registry.get("ruff").documentation
    assert documentation is not None
    assert documentation.help is not None
    assert "Ruff" in documentation.help.content


def test_register_catalog_tools_reuses_cached_snapshot(
    tmp_path: Path,
    schema_root: Path,
    monkeypatch,
) -> None:
    """Repeated catalog registration should reuse the cached snapshot."""
    clear_catalog_cache()
    catalog_root = tmp_path / "catalog"
    strategies_dir = catalog_root / "strategies"
    strategies_dir.mkdir(parents=True)

    _write_json(
        strategies_dir / "sample_command.json",
        {
            "schemaVersion": "1.0.0",
            "id": "sample_command",
            "type": "command",
            "implementation": "tests.tooling.sample_strategies.command_builder",
        },
    )
    _write_json(
        catalog_root / "tool.json",
        {
            "schemaVersion": "1.0.0",
            "name": "sample-tool",
            "description": "Synthetic tool defined in catalog.",
            "languages": ["python"],
            "phase": "lint",
            "actions": [
                {
                    "name": "lint",
                    "command": {
                        "strategy": "sample_command",
                        "config": {"args": ["echo", "hi"]},
                    },
                },
            ],
        },
    )

    register_catalog_tools(
        registry=ToolRegistry(),
        catalog_root=catalog_root,
        schema_root=schema_root,
    )

    load_calls = 0
    checksum_calls = 0
    original_load = ToolCatalogLoader.load_snapshot
    original_checksum = ToolCatalogLoader.compute_checksum

    def patched_load(self: ToolCatalogLoader) -> CatalogSnapshot:
        nonlocal load_calls
        load_calls += 1
        return original_load(self)

    def patched_checksum(self: ToolCatalogLoader) -> str:
        nonlocal checksum_calls
        checksum_calls += 1
        return original_checksum(self)

    monkeypatch.setattr(ToolCatalogLoader, "load_snapshot", patched_load)
    monkeypatch.setattr(ToolCatalogLoader, "compute_checksum", patched_checksum)

    register_catalog_tools(
        registry=ToolRegistry(),
        catalog_root=catalog_root,
        schema_root=schema_root,
    )

    assert load_calls == 0
    assert checksum_calls == 1


def test_register_catalog_tools_refreshes_cache_on_change(
    tmp_path: Path,
    schema_root: Path,
    monkeypatch,
) -> None:
    """Cache should invalidate when catalog content changes on disk."""
    clear_catalog_cache()
    catalog_root = tmp_path / "catalog"
    strategies_dir = catalog_root / "strategies"
    strategies_dir.mkdir(parents=True)

    _write_json(
        strategies_dir / "sample_command.json",
        {
            "schemaVersion": "1.0.0",
            "id": "sample_command",
            "type": "command",
            "implementation": "tests.tooling.sample_strategies.command_builder",
        },
    )

    tool_path = catalog_root / "tool.json"
    _write_json(
        tool_path,
        {
            "schemaVersion": "1.0.0",
            "name": "sample-tool",
            "description": "Original",
            "languages": ["python"],
            "phase": "lint",
            "actions": [
                {
                    "name": "lint",
                    "command": {
                        "strategy": "sample_command",
                        "config": {"args": ["echo", "one"]},
                    },
                },
            ],
        },
    )

    registry = ToolRegistry()
    register_catalog_tools(
        registry=registry,
        catalog_root=catalog_root,
        schema_root=schema_root,
    )

    _write_json(
        tool_path,
        {
            "schemaVersion": "1.0.0",
            "name": "sample-tool",
            "description": "Updated",
            "languages": ["python"],
            "phase": "lint",
            "actions": [
                {
                    "name": "lint",
                    "command": {
                        "strategy": "sample_command",
                        "config": {"args": ["echo", "two"]},
                    },
                },
            ],
        },
    )

    load_calls = 0
    original_load = ToolCatalogLoader.load_snapshot

    def patched_load(self: ToolCatalogLoader) -> CatalogSnapshot:
        nonlocal load_calls
        load_calls += 1
        return original_load(self)

    monkeypatch.setattr(ToolCatalogLoader, "load_snapshot", patched_load)

    register_catalog_tools(
        registry=registry,
        catalog_root=catalog_root,
        schema_root=schema_root,
    )

    assert load_calls == 1
    command = registry.get("sample-tool").actions[0].build_command(ToolContext(cfg=Config(), root=tmp_path))
    assert command[-2:] == ["echo", "two"]
