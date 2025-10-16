# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Focused tests for pyqa-specific AST linters."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pyqa.linting import di as di_linter
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
                include_dotfiles=False,
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
    pkg_dir = tmp_path / "pyqa"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    module = pkg_dir / "module.py"
    module.write_text("import pyqa.reporting\n", encoding="utf-8")

    state = _stub_state(tmp_path, module)
    report = run_pyqa_interface_linter(state, emit_to_logger=False)

    assert any("interfaces" in diagnostic.message for diagnostic in report.outcome.diagnostics)


def test_pyqa_interface_linter_treats_generic_interfaces_modules_as_abstract(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "pkg"
    interfaces_dir = pkg_dir / "interfaces"
    interfaces_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (interfaces_dir / "contracts.py").write_text("class Marker: ...\n", encoding="utf-8")
    module = pkg_dir / "module.py"
    module.write_text("import pkg.interfaces.contracts\n", encoding="utf-8")

    state = _stub_state(tmp_path, module)
    report = run_pyqa_interface_linter(state, emit_to_logger=False)

    assert report.outcome.diagnostics == []


def test_pyqa_interface_linter_flags_concrete_symbols_in_interfaces(tmp_path: Path) -> None:
    pyqa_dir = tmp_path / "pyqa"
    interfaces_dir = pyqa_dir / "interfaces"
    interfaces_dir.mkdir(parents=True)
    (pyqa_dir / "__init__.py").write_text("", encoding="utf-8")
    (interfaces_dir / "__init__.py").write_text("", encoding="utf-8")
    module = interfaces_dir / "core.py"
    module.write_text(
        """def detect_tty():\n    return True\n""",
        encoding="utf-8",
    )

    state = _stub_state(tmp_path, module)
    report = run_pyqa_interface_linter(state, emit_to_logger=False)
    diagnostics = report.outcome.diagnostics

    assert diagnostics
    diagnostic = diagnostics[0]
    assert "must not define concrete function" in diagnostic.message
    assert diagnostic.meta["violation"] == "concrete-interface"
    assert "interfaces packages" in " ".join(diagnostic.hints)


def test_pyqa_di_linter_reports_registration_outside_allowlist(tmp_path: Path) -> None:
    module = tmp_path / "service.py"
    module.write_text(
        """from pyqa.core.runtime.di import ServiceContainer\ncontainer = ServiceContainer()\ncontainer.register('tool', object())\n""",
        encoding="utf-8",
    )

    state = _stub_state(tmp_path, module)
    report = run_pyqa_di_linter(state, emit_to_logger=False)
    diagnostics = report.outcome.diagnostics

    assert diagnostics
    diagnostic = diagnostics[0]
    assert "tool" in diagnostic.message
    for module_name in di_linter._ALLOWED_SERVICE_REGISTERERS:
        assert module_name in diagnostic.message
    assert "bootstrap" in diagnostic.message
    assert diagnostic.hints
    hint_text = " ".join(diagnostic.hints)
    assert "CompositionRegistry" in hint_text
    assert "pyqa.core.runtime.di" in hint_text
    assert "test DI fixtures" in hint_text
    assert diagnostic.meta.get("service") == "tool"
    suffixes = diagnostic.meta.get("allowed_suffixes")
    if isinstance(suffixes, list):
        suffixes_value = tuple(suffixes)
    else:
        suffixes_value = suffixes
    assert suffixes_value == di_linter._ALLOWED_SERVICE_SUFFIXES
