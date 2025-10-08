# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Ensure value-type helpers expose ergonomic dunder methods."""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport, build_internal_report

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from pyqa.cli.commands.lint.preparation import PreparedLintState


@dataclass(frozen=True, slots=True)
class _ValueTypeContract:
    """Describe required dunder methods for a value-type helper."""

    module_path: str
    qualname: str
    required_methods: tuple[str, ...]


_CONTRACTS: tuple[_ValueTypeContract, ...] = (
    _ValueTypeContract(
        module_path="pyqa.analysis.navigator",
        qualname="NavigatorBucket",
        required_methods=("__len__",),
    ),
    _ValueTypeContract(
        module_path="pyqa.clean.runner",
        qualname="CleanResult",
        required_methods=("__bool__",),
    ),
    _ValueTypeContract(
        module_path="pyqa.core.runtime.di",
        qualname="ServiceContainer",
        required_methods=("__contains__", "__len__"),
    ),
)


def run_value_type_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool = True,
) -> InternalLintReport:
    """Validate that critical helper classes expose ergonomic dunder methods.

    Args:
        state: Prepared lint state describing the active workspace.
        emit_to_logger: Compatibility flag; retained to match the internal linter
            protocol although no logger output is produced directly.

    Returns:
        InternalLintReport: Aggregated diagnostics describing missing dunder
        implementations.
    """

    _ = emit_to_logger
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []

    for contract in _CONTRACTS:
        missing = _missing_methods(contract)
        if not missing:
            continue
        file_path, line_number = _definition_location(contract)
        message = f"{contract.qualname} is missing required dunder methods: {', '.join(sorted(missing))}"
        normalized = normalize_path_key(file_path, base_dir=state.root)
        diagnostics.append(
            Diagnostic(
                file=normalized,
                line=line_number,
                column=None,
                severity=Severity.ERROR,
                message=message,
                tool="value-types",
                code="internal:value-types",
            ),
        )
        stdout_lines.append(f"{normalized}:{line_number}: {message}")

    return build_internal_report(
        tool="value-types",
        stdout=stdout_lines,
        diagnostics=diagnostics,
        files=(),
    )


def _missing_methods(contract: _ValueTypeContract) -> Sequence[str]:
    """Return the methods from ``contract`` that are absent on the class."""

    module = _import_module(contract.module_path)
    if module is None:
        return contract.required_methods
    cls = getattr(module, contract.qualname, None)
    if cls is None:
        return contract.required_methods

    missing = [method for method in contract.required_methods if not hasattr(cls, method)]
    return tuple(missing)


def _definition_location(contract: _ValueTypeContract) -> tuple[Path, int]:
    """Return the source file path and line number for ``contract``."""

    module = _import_module(contract.module_path)
    if module is None:
        return _fallback_location(contract)

    cls = getattr(module, contract.qualname, None)
    if cls is None:
        return _fallback_location(contract)

    source_path = inspect.getsourcefile(cls)
    if source_path is None:
        return _fallback_location(contract)

    try:
        line_number = inspect.getsourcelines(cls)[1]
    except (OSError, TypeError, ValueError):
        line_number = 1
    return Path(source_path), line_number


def _import_module(path: str) -> Any | None:
    """Return the imported module for ``path`` when available."""

    try:
        return __import__(path, fromlist=[path.rsplit(".", 1)[-1]])
    except ImportError:
        return None


def _fallback_location(contract: _ValueTypeContract) -> tuple[Path, int]:
    """Return a conservative file/line tuple when introspection fails."""

    return Path(contract.module_path.replace(".", "/") + ".py"), 1


__all__ = ["run_value_type_linter"]
