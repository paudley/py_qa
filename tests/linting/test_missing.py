# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the missing functionality internal linter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pyqa.linting.missing import run_missing_linter


def _build_state(root: Path, targets: list[Path]) -> SimpleNamespace:
    """Return a stub resembling :class:`PreparedLintState`."""

    target_options = SimpleNamespace(
        root=root,
        paths=targets,
        dirs=[],
        exclude=[],
        paths_from_stdin=False,
        include_dotfiles=False,
    )
    options = SimpleNamespace(target_options=target_options)
    meta = SimpleNamespace(
        normal=False,
        show_valid_suppressions=False,
        runtime=SimpleNamespace(pyqa_rules=False),
    )
    logger = SimpleNamespace(debug=lambda *args, **kwargs: None)
    return SimpleNamespace(
        root=root,
        options=options,
        meta=meta,
        suppressions=None,
        logger=logger,
        artifacts=None,
        display=None,
        ignored_pyqa_lint=[],
    )


def test_missing_linter_flags_todo_marker(tmp_path: Path) -> None:
    """Ensure TODO markers raise diagnostics."""

    source = tmp_path / "feature.txt"
    source.write_text("TODO: finish implementation\n", encoding="utf-8")
    state = _build_state(tmp_path, [source])

    report = run_missing_linter(state, emit_to_logger=False)

    assert report.outcome.returncode == 1
    assert report.outcome.diagnostics
    diagnostic = report.outcome.diagnostics[0]
    assert diagnostic.code == "missing:marker"
    assert "TODO" in diagnostic.message


def test_missing_linter_flags_not_implemented_error(tmp_path: Path) -> None:
    """Ensure Python NotImplementedError raises diagnostics."""

    source = tmp_path / "adapter.py"
    source.write_text(
        "class Adapter:\n    def __call__(self):\n        raise NotImplementedError\n",
        encoding="utf-8",
    )
    state = _build_state(tmp_path, [source])

    report = run_missing_linter(state, emit_to_logger=False)

    assert report.outcome.returncode == 1
    codes = {diagnostic.code for diagnostic in report.outcome.diagnostics}
    assert "missing:not-implemented-error" in codes


def test_missing_linter_allows_complete_file(tmp_path: Path) -> None:
    """Ensure files without placeholders do not raise diagnostics."""

    source = tmp_path / "complete.py"
    source.write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    state = _build_state(tmp_path, [source])

    report = run_missing_linter(state, emit_to_logger=False)

    assert report.outcome.returncode == 0
    assert not report.outcome.diagnostics


def test_missing_linter_ignores_markdown(tmp_path: Path) -> None:
    """Ensure documentation files are excluded from missing functionality checks."""

    source = tmp_path / "README.md"
    source.write_text("# TODO: flesh out documentation\n", encoding="utf-8")
    state = _build_state(tmp_path, [source])

    report = run_missing_linter(state, emit_to_logger=False)

    assert report.outcome.returncode == 0
    assert not report.outcome.diagnostics
