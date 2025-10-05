# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for hadolint tool integration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_download_binary
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _catalog_hadolint_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "hadolint":
            continue
        for action in definition.actions:
            if action.name != "lint":
                continue
            config = action.command.reference.config
            if isinstance(config, Mapping):
                return dict(config)
    raise AssertionError("hadolint configuration missing from catalog")


_HADOLINT_CONFIG = _catalog_hadolint_config()


def test_hadolint_command_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_binary = tmp_path / "bin" / "hadolint"
    fake_binary.parent.mkdir(parents=True, exist_ok=True)
    fake_binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_binary.chmod(0o755)

    monkeypatch.setattr(
        "pyqa.tooling.strategies._download_artifact_for_tool",
        lambda download_config, version, cache_root, context: fake_binary,
    )

    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "Dockerfile"],
        settings={"config": tmp_path / ".hadolint"},
    )

    builder = command_download_binary(_HADOLINT_CONFIG)
    action = ToolAction(
        name="lint",
        command=builder,
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == str(fake_binary)
    assert "--format" in command and "json" in command
    assert "--config" in command and str(tmp_path / ".hadolint") in command
    assert command[-1].endswith("Dockerfile")
