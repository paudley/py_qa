# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Unit tests for ``pyqa.runtime.installers`` helper functions."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

from pyqa.runtime.installers import install_dev_environment


def _completed(
    args: list[str],
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> CompletedProcess[str]:
    return CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def test_install_dev_environment_installs_core_packages(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def fake_run_command(args, **kwargs):  # noqa: ANN001
        commands.append(list(args))
        return _completed(list(args))

    monkeypatch.setattr("pyqa.runtime.installers.dev.run_command", fake_run_command)

    summary = install_dev_environment(
        tmp_path,
        include_optional=False,
        generate_stubs=False,
    )

    assert any(cmd[:3] == ["uv", "add", "-q"] for cmd in commands)
    assert summary.optional_stub_packages == ()
    assert summary.generated_stub_modules == ()
    marker_contents = json.loads(summary.marker_path.read_text(encoding="utf-8"))
    assert marker_contents == {"project": True}


def test_install_dev_environment_handles_optional_and_stubs(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def fake_run_command(
        args,
        cwd=None,
        check=True,
        capture_output=False,
        **kwargs,
    ):
        commands.append(list(args))
        if capture_output:
            packages = [
                {"name": "requests"},
                {"name": "pyarrow"},
            ]
            return _completed(list(args), stdout=json.dumps(packages))
        return _completed(list(args))

    monkeypatch.setattr("pyqa.runtime.installers.dev.run_command", fake_run_command)

    summary = install_dev_environment(
        tmp_path,
        include_optional=True,
        generate_stubs=True,
    )

    assert "types-requests" in summary.optional_stub_packages
    assert "pyarrow" in summary.generated_stub_modules
    uv_add_commands = [cmd for cmd in commands if cmd[:3] == ["uv", "add", "-q"]]
    assert any("types-requests" in cmd for cmd in uv_add_commands)
    stubgen_commands = [cmd for cmd in commands if cmd[:3] == ["uv", "run", "stubgen"]]
    assert stubgen_commands

    # We simulate stub generation to ensure the follow-up call sees existing artefacts.
    stubs_root = tmp_path / "stubs"
    for module in summary.generated_stub_modules:
        target = stubs_root / module
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)

    # Running again should skip existing stub targets
    summary_again = install_dev_environment(
        tmp_path,
        include_optional=False,
        generate_stubs=True,
    )
    assert summary_again.generated_stub_modules == ()
