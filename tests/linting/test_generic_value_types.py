# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the generic value-type recommendation linter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    import tree_sitter  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pytest.skip("tree-sitter not available", allow_module_level=True)
else:
    _ = tree_sitter

from pyqa.config import Config, GenericValueTypesRule
from pyqa.linting.generic_value_types import run_generic_value_type_linter
from pyqa.linting.suppressions import SuppressionRegistry


def _build_state(root: Path, targets: list[Path]) -> SimpleNamespace:
    """Return a minimal stub resembling :class:`PreparedLintState`."""

    target_options = SimpleNamespace(
        root=root,
        paths=targets,
        dirs=[],
        exclude=[],
        paths_from_stdin=False,
    )
    options = SimpleNamespace(target_options=target_options)
    meta = SimpleNamespace(
        normal=False,
        show_valid_suppressions=False,
    )
    logger = SimpleNamespace(debug=lambda *args, **kwargs: None)
    suppressions = SuppressionRegistry(root)
    return SimpleNamespace(
        root=root,
        options=options,
        meta=meta,
        suppressions=suppressions,
        logger=logger,
        artifacts=None,
        display=None,
        ignored_py_qa=[],
    )


def test_generic_value_types_flags_missing_required(tmp_path: Path) -> None:
    """Ensure the linter emits errors for missing required dunder methods."""

    source = tmp_path / "container.py"
    source.write_text(
        """
class Payload:
    def __iter__(self):
        yield from ()
""".strip()
    )
    state = _build_state(tmp_path, [source])
    config = Config()
    rule = GenericValueTypesRule(
        pattern="*.Payload",
        traits=("iterable",),
        require=("__len__", "__contains__"),
    )
    config.generic_value_types = config.generic_value_types.model_copy(
        update={
            "enabled": True,
            "rules": (rule,),
            "implications": (),
        },
    )

    report = run_generic_value_type_linter(state, emit_to_logger=False, config=config)
    diagnostics = report.outcome.diagnostics

    assert report.outcome.returncode == 1
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.severity.name == "ERROR"
    assert "Payload" in diagnostic.message
    assert "__len__" in diagnostic.message
    assert diagnostic.code == "generic-value-types:missing-required"


def test_generic_value_types_respects_suppression(tmp_path: Path) -> None:
    """Ensure suppression_valid directives suppress generic value-type findings."""

    source = tmp_path / "data.py"
    source.write_text(
        """
# suppression_valid: lint=generic-value-types reason this class exposes a dynamic size contract across adapters
class Payload:
    def __iter__(self):
        yield from ()
""".strip()
    )
    state = _build_state(tmp_path, [source])
    config = Config()
    rule = GenericValueTypesRule(
        pattern="*.Payload",
        traits=("iterable",),
        require=("__len__",),
    )
    config.generic_value_types = config.generic_value_types.model_copy(
        update={
            "enabled": True,
            "rules": (rule,),
            "implications": (),
        },
    )

    report = run_generic_value_type_linter(state, emit_to_logger=False, config=config)

    assert report.outcome.returncode == 0
    assert not report.outcome.diagnostics
