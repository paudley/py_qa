# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for linting utility helpers."""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from pyqa.cli.commands.lint.preparation import PreparedLintState


def _collect_target_files() -> Callable[[PreparedLintState], list[Path]]:
    """Load the ``collect_target_files`` function without importing ``pyqa.linting``.

    Returns:
        Callable[[PreparedLintState], list[Path]]: Resolved collector function
        sourced from the linting utilities module.
    """

    module_name = "tests.linting._utils_under_test"
    if module_name in sys.modules:
        module = sys.modules[module_name]
    else:
        module_path = Path(__file__).resolve().parents[2] / "src" / "pyqa" / "linting" / "utils.py"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return cast("Callable[[PreparedLintState], list[Path]]", getattr(module, "collect_target_files"))


collect_target_files = _collect_target_files()


def _build_state(
    *,
    root: Path,
    paths: list[Path] | None = None,
    dirs: list[Path] | None = None,
    exclude: list[Path] | None = None,
) -> PreparedLintState:
    """Build a minimal stand-in resembling :class:`PreparedLintState`.

    Args:
        root: Workspace root supplied to the lint command.
        paths: Optional list of user-specified paths.
        dirs: Optional list of directories supplied via CLI flags.
        exclude: Optional list of exclusion paths.

    Returns:
        PreparedLintState: Stand-in object containing only the attributes required
        by :func:`collect_target_files`.
    """

    target_options = SimpleNamespace(
        root=root,
        paths=paths or [],
        dirs=dirs or [],
        exclude=exclude or [],
        paths_from_stdin=False,
    )
    options = SimpleNamespace(target_options=target_options)
    state = SimpleNamespace(options=options)
    return cast("PreparedLintState", state)


def test_collect_target_files_rejects_paths_above_root(tmp_path: Path) -> None:
    """Verify files located above the workspace root are ignored.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """

    root = tmp_path / "workspace"
    root.mkdir()
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("print('outside')\n", encoding="utf-8")

    state = _build_state(root=root, paths=[outside_file])

    result = collect_target_files(state)

    assert result == []


def test_collect_target_files_ignores_symlinks_escaping_root(tmp_path: Path) -> None:
    """Verify directory walks ignore symlinks that resolve outside the root.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """

    if not hasattr(os, "symlink"):
        pytest.skip("OS does not support symlinks required for this test")

    root = tmp_path / "workspace"
    root.mkdir()
    inside_file = root / "inside.py"
    inside_file.write_text("print('inside')\n", encoding="utf-8")

    outside_target = tmp_path / "outside.py"
    outside_target.write_text("print('outside')\n", encoding="utf-8")
    escaping_symlink = root / "linked.py"
    try:
        os.symlink(outside_target, escaping_symlink)
    except OSError:
        pytest.skip("Unable to create symlinks in this environment")

    state = _build_state(root=root, paths=[root])

    result = collect_target_files(state)

    assert result == [inside_file.resolve()]
