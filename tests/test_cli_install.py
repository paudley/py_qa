# SPDX-License-Identifier: MIT
"""CLI tests for the install command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.installs import InstallSummary


def test_install_cli_passes_flags(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    calls: list[tuple[Path, bool, bool]] = []

    def fake_install(
        root: Path,
        *,
        include_optional: bool,
        generate_stubs: bool,
        on_optional_stub=None,
        on_stub_generation=None,
    ) -> InstallSummary:
        calls.append((root, include_optional, generate_stubs))
        return InstallSummary((), (), root / ".lint-cache" / "marker.json")

    monkeypatch.setattr("pyqa.cli.install.install_dev_environment", fake_install)

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
        generate_stubs: bool,
        on_optional_stub=None,
        on_stub_generation=None,
    ) -> InstallSummary:
        if on_optional_stub is not None:
            on_optional_stub("types-requests")
        if on_stub_generation is not None:
            on_stub_generation("pyarrow")
        return InstallSummary(("types-requests",), ("pyarrow",), root / "marker")

    monkeypatch.setattr("pyqa.cli.install.install_dev_environment", fake_install)

    result = runner.invoke(app, ["install", "--root", str(tmp_path), "--no-emoji"])

    assert result.exit_code == 0
    assert "types-requests" in result.stdout
    assert "pyarrow" in result.stdout
