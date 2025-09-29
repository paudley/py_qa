# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for kube-linter tool integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import kube_linter_command
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


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


_KUBE_LINTER_COMMAND = kube_linter_command(_kube_linter_command_config())


def test_kube_linter_command_build(tmp_path: Path) -> None:
    cfg = Mock()
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

    action = ToolAction(
        name="lint",
        command=_KUBE_LINTER_COMMAND,
        append_files=True,
    )

    command = action.build_command(ctx)
    assert tuple(command[:4]) == ("kube-linter", "lint", "--format", "json")
    assert "--config" in command
    assert str(tmp_path / "config" / "custom.yaml") in command
    assert command[-1].endswith("deployment.yaml")
