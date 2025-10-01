# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

from pathlib import Path

import pytest

from pyqa.models import RawDiagnostic


def test_raw_diagnostic_normalizes_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "pkg" / "module.py"
    target.parent.mkdir(parents=True, exist_ok=True)

    diagnostic = RawDiagnostic(
        file=str(target),
        line=3,
        column=None,
        severity="warning",
        message="example",
        code="X001",
        tool="dummy",
    )

    assert diagnostic.file == "pkg/module.py"
