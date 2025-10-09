# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Focused tests for pyqa-specific AST linters."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pyqa.linting.di import run_pyqa_di_linter
from pyqa.linting.interfaces import run_pyqa_interface_linter


def _stub_state(tmp_path: Path, module: Path) -> SimpleNamespace:
    return SimpleNamespace(
        root=tmp_path,
        options=SimpleNamespace(
            target_options=SimpleNamespace(
                root=tmp_path,
                paths=[module],
                dirs=[],
                exclude=[],
                paths_from_stdin=False,
            ),
        ),
        meta=SimpleNamespace(pyqa_rules=True),
        logger=None,
    )


def test_pyqa_interface_linter_skips_test_directory(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    module = tests_dir / "example.py"
    module.write_text("import pyqa.reporting\n", encoding="utf-8")

    state = _stub_state(tmp_path, module)
    report = run_pyqa_interface_linter(state, emit_to_logger=False)

    assert report.outcome.diagnostics == []


def test_pyqa_interface_linter_flags_production_import(tmp_path: Path) -> None:
    module = tmp_path / "module.py"
    module.write_text("import pyqa.reporting\n", encoding="utf-8")

    state = _stub_state(tmp_path, module)
    report = run_pyqa_interface_linter(state, emit_to_logger=False)

    assert any("interfaces" in diagnostic.message for diagnostic in report.outcome.diagnostics)


def test_pyqa_di_linter_reports_registration_outside_allowlist(tmp_path: Path) -> None:
    module = tmp_path / "service.py"
    module.write_text(
        """from pyqa.core.runtime.di import ServiceContainer\ncontainer = ServiceContainer()\ncontainer.register('tool', object())\n""",
        encoding="utf-8",
    )

    state = _stub_state(tmp_path, module)
    report = run_pyqa_di_linter(state, emit_to_logger=False)

    assert report.outcome.diagnostics

