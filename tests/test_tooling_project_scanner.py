# SPDX-License-Identifier: MIT

"""Regression tests for project scanner command helpers."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.project_scanner import build_project_scanner
from pyqa.tools.base import ToolContext


def test_project_scanner_resolves_targets_and_excludes(tmp_path: Path) -> None:
    """Ensure project scanner builds commands respecting excludes and targets."""

    config = {
        "base": ["scan"],
        "options": [
            {
                "setting": "opt",
                "type": "value",
                "flag": "--opt",
            },
        ],
        "exclude": {
            "settings": ["excludes"],
            "flag": "--exclude",
            "separator": ",",
        },
        "targets": {
            "settings": ["targets"],
            "includeDiscoveryRoots": False,
            "includeDiscoveryExplicit": False,
            "fallback": ["fallback"],
            "defaultToRoot": False,
            "filterExcluded": True,
            "prefix": "--path=",
        },
    }

    builder = build_project_scanner(config)

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "exclude").mkdir(parents=True)
    (tmp_path / "fallback").mkdir()

    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        settings={
            "opt": "42",
            "targets": ["src"],
            "excludes": ["src/exclude"],
        },
    )

    command = builder.build(ctx)
    assert command[0] == "scan"

    exclude_index = command.index("--exclude")
    exclude_arg = command[exclude_index + 1]
    assert str(tmp_path / "src" / "exclude") in exclude_arg
    assert "src/exclude" in exclude_arg

    opt_index = command.index("--opt")
    assert command[opt_index + 1] == "42"

    # Prefix argument is emitted followed by the prefixed target entry
    path_prefix_index = command.index("--path=")
    assert command[path_prefix_index + 1].startswith("--path=")
    assert command[path_prefix_index + 1] == f"--path={tmp_path / 'src'}"

    fallback_ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        settings={"opt": "99"},
    )
    fallback_command = builder.build(fallback_ctx)
    assert fallback_command == (
        "scan",
        "--opt",
        "99",
        "--path=",
        f"--path={tmp_path / 'fallback'}",
    )
