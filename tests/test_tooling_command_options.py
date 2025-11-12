# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Regression tests for command option mapping helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyqa.catalog.command_options import command_option_map, compile_option_mappings
from pyqa.catalog.errors import CatalogIntegrityError
from pyqa.config import Config
from pyqa.tools.base import ToolContext


def test_command_option_map_builds_expected_command(tmp_path: Path) -> None:
    """Ensure option behaviours compose CLI fragments as expected."""

    config = {
        "base": ["quality-tool"],
        "appendFiles": False,
        "options": [
            {
                "setting": "list",
                "type": "args",
                "flag": "--list",
                "joinWith": ",",
            },
            {
                "setting": "path",
                "type": "path",
                "flag": "--path",
                "literalValues": ["workspace"],
            },
            {
                "setting": "enable",
                "type": "flag",
                "flag": "--enable",
                "negateFlag": "--disable",
            },
            {
                "setting": "threshold",
                "type": "value",
                "flag": "--threshold",
            },
            {
                "setting": "retries",
                "type": "repeatFlag",
                "flag": "-v",
            },
            {
                "setting": "quiet",
                "type": "repeatFlag",
                "flag": "-q",
                "negateFlag": "--loud",
            },
            {
                "setting": "toggle",
                "type": "value",
                "flag": "--toggle=",
                "transform": "bool_to_yn",
            },
        ],
    }

    builder = command_option_map(config)

    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        settings={
            "list": ["alpha", "beta"],
            "path": "workspace",
            "enable": True,
            "threshold": 3,
            "retries": 2,
            "quiet": 0,
            "toggle": False,
        },
    )

    command = builder.build(ctx)
    assert command == (
        "quality-tool",
        "--list",
        "alpha,beta",
        "--path",
        "workspace",
        "--enable",
        "--threshold",
        "3",
        "-v",
        "-v",
        "--loud",
        "--toggle=n",
    )


def test_command_option_map_uses_default_reference(tmp_path: Path) -> None:
    """Verify default references populate missing settings from shared config."""

    config = {
        "base": ["formatter-tool"],
        "appendFiles": False,
        "options": [
            {
                "setting": "line-length",
                "type": "value",
                "flag": "--line-length",
                "defaultFrom": "execution.line_length",
            },
        ],
    }

    builder = command_option_map(config)
    ctx = ToolContext(cfg=Config(), root=tmp_path)

    command = builder.build(ctx)
    assert command == ("formatter-tool", "--line-length", "120")


def test_compile_option_mappings_rejects_non_sequence() -> None:
    """Non-array option declarations must raise a catalog validation error."""

    with pytest.raises(CatalogIntegrityError):
        compile_option_mappings(123, context="tests.invalid")
