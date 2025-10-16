# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the value-type ergonomics linter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pyqa.linting.value_types import run_value_type_linter


@pytest.fixture
def stub_state() -> SimpleNamespace:
    root = Path(__file__).resolve().parents[3]
    target_options = SimpleNamespace(paths=[root / "src/pyqa/analysis/navigator.py"], dirs=[])
    target_options.include_dotfiles = False
    options = SimpleNamespace(target_options=target_options)
    meta = SimpleNamespace(normal=False)
    return SimpleNamespace(root=root, options=options, meta=meta)


def test_value_type_linter_passes_when_contracts_met(stub_state: SimpleNamespace) -> None:
    report = run_value_type_linter(stub_state, emit_to_logger=False)
    assert report.outcome.returncode == 0


def test_value_type_linter_flags_missing_method(monkeypatch: pytest.MonkeyPatch, stub_state: SimpleNamespace) -> None:
    from pyqa.clean.runner import CleanResult

    monkeypatch.delattr(CleanResult, "__bool__")

    report = run_value_type_linter(stub_state, emit_to_logger=False)
    diagnostics = report.outcome.diagnostics
    assert report.outcome.returncode == 1
    assert any("CleanResult" in diagnostic.message for diagnostic in diagnostics)
