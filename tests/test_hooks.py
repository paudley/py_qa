# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for hook installation utilities."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.hooks import HOOK_NAMES, install_hooks


def _make_repo(root: Path) -> Path:
    git_dir = root / ".git"
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    template_dir = root / "pyqa-lint" / "hooks"
    template_dir.mkdir(parents=True, exist_ok=True)
    for name in HOOK_NAMES:
        template = template_dir / name
        template.write_text("#!/bin/bash\necho hook\n", encoding="utf-8")
    return hooks_dir


def test_install_hooks_creates_symlinks(tmp_path: Path) -> None:
    hooks_dir = _make_repo(tmp_path)
    result = install_hooks(tmp_path, dry_run=False)
    assert len(result.installed) == len(HOOK_NAMES)
    for name in HOOK_NAMES:
        destination = hooks_dir / name
        assert destination.is_symlink()
        assert destination.resolve() == (tmp_path / "pyqa-lint" / "hooks" / name).resolve()


def test_cli_dry_run(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "install-hooks",
            "--root",
            str(tmp_path),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.stdout or "Dry run" in result.stdout.lower()
