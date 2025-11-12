# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for kube-linter tool integration."""

from __future__ import annotations

from pathlib import Path
from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _kube_linter_command_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "kube-linter":
            continue
        for action in definition.actions:
            if action.name != "lint":
                continue
            return dict(action.command.reference.config)
    raise AssertionError("kube-linter command configuration missing from catalog")


def test_kube_linter_command_build(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 120

    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "manifests" / "deployment.yaml"],
        settings={
            "config": tmp_path / "config" / "custom.yaml",
            "include": ["check-a"],
            "verbose": True,
        },
    )

    builder = command_option_map(_kube_linter_command_config())
    action = ToolAction(name="lint", command=builder)

    command = action.build_command(ctx)
    assert tuple(command[:4]) == ("kube-linter", "lint", "--format", "json")
    assert "--config" in command
    assert str(tmp_path / "config" / "custom.yaml") in command
    assert command[-1].endswith("deployment.yaml")
