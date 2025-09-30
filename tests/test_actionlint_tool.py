# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the actionlint tool integration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_download_binary
from pyqa.tools.base import ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _catalog_actionlint_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "actionlint":
            continue
        for action in definition.actions:
            if action.name != "lint":
                continue
            config = action.command.reference.config
            if isinstance(config, Mapping):
                return dict(config)
    raise AssertionError("actionlint configuration missing from catalog")


_ACTIONLINT_CONFIG = _catalog_actionlint_config()


def test_actionlint_command_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binary_path = tmp_path / "bin" / "actionlint"
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr(
        "pyqa.tooling.strategies._download_artifact_for_tool",
        lambda download_config, version, cache_root, context: binary_path,
    )

    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        files=[],
        settings={},
    )

    (tmp_path / ".github" / "workflows").mkdir(parents=True)

    builder = command_download_binary(_ACTIONLINT_CONFIG)
    command = builder.build(ctx)

    assert command[0] == str(binary_path)
    assert command[1:4] == ("-format", "{{json .}}", "-no-color")
    assert command[-1].endswith(".github/workflows")


def test_actionlint_filters_non_github_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "bin" / "actionlint"
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr(
        "pyqa.tooling.strategies._download_artifact_for_tool",
        lambda download_config, version, cache_root, context: binary_path,
    )

    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("name: test\n", encoding="utf-8")

    sample = tmp_path / "tooling" / "catalog" / "docs" / "_scratch" / "sample.yaml"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("kind: Pod\n", encoding="utf-8")

    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        files=[sample, workflow],
        settings={},
    )

    builder = command_download_binary(_ACTIONLINT_CONFIG)
    command = builder.build(ctx)

    args = list(command)
    assert any(str(workflow) == arg for arg in args)
    assert not any("sample.yaml" in arg for arg in args)
