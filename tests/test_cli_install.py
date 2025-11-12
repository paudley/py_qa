# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI tests for the install command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.runtime.installers import InstallSummary


def test_install_cli_passes_flags(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    calls: list[tuple[Path, bool, bool]] = []

    def fake_install(
        root: Path,
        *,
        include_optional: bool,
        generate_typing_modules: bool,
        on_optional_package=None,
        on_module_generation=None,
    ) -> InstallSummary:
        calls.append((root, include_optional, generate_typing_modules))
        return InstallSummary(
            optional_typing_packages=(),
            generated_typing_modules=(),
            marker_path=root / ".lint-cache" / "marker.json",
        )

    monkeypatch.setattr("pyqa.cli.commands.install.command.install_dev_environment", fake_install)

    result = runner.invoke(
        app,
        [
            "install",
            "--root",
            str(tmp_path),
            "--no-include-optional",
            "--no-generate-stubs",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert calls == [(tmp_path.resolve(), False, False)]
    assert "Dependency installation complete." in result.stdout
    assert "✅" not in result.stdout


def test_install_cli_emits_progress(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    def fake_install(
        root: Path,
        *,
        include_optional: bool,
        generate_typing_modules: bool,
        on_optional_package=None,
        on_module_generation=None,
    ) -> InstallSummary:
        if on_optional_package is not None:
            on_optional_package("types-requests")
        if on_module_generation is not None:
            on_module_generation("pyarrow")
        return InstallSummary(
            optional_typing_packages=("types-requests",),
            generated_typing_modules=("pyarrow",),
            marker_path=root / "marker",
        )

    monkeypatch.setattr("pyqa.cli.commands.install.command.install_dev_environment", fake_install)

    result = runner.invoke(app, ["install", "--root", str(tmp_path), "--no-emoji"])

    assert result.exit_code == 0
    assert "types-requests" in result.stdout
    assert "pyarrow" in result.stdout
