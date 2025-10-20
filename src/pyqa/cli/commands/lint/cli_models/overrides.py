# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Override dependency factories shared by lint CLI options."""

from __future__ import annotations

from typing import Annotated

import typer

from ....core.shared import Depends
from ..params import LintOverrideParams, OverrideFormattingParams, OverrideStrictnessParams, OverrideThresholdParams
from .coercion import _coerce_optional_strictness
from .constants import (
    LINE_LENGTH_HELP,
    MAX_ARGUMENTS_HELP,
    MAX_COMPLEXITY_HELP,
    PYTHON_VERSION_HELP,
    SQL_DIALECT_HELP,
    TYPE_CHECKING_HELP,
)


def _override_formatting_dependency(
    line_length: Annotated[int, typer.Option(120, "--line-length", help=LINE_LENGTH_HELP)],
    sql_dialect: Annotated[str, typer.Option("postgresql", "--sql-dialect", help=SQL_DIALECT_HELP)],
    python_version: Annotated[str | None, typer.Option(None, "--python-version", help=PYTHON_VERSION_HELP)],
) -> OverrideFormattingParams:
    """Return formatting overrides shared across compatible tools.

    Args:
        line_length: Global maximum line length.
        sql_dialect: Default SQL dialect for formatting tools.
        python_version: Optional Python version advertised to tools.

    Returns:
        OverrideFormattingParams: Structured formatting overrides.
    """

    normalized_python_version = python_version.strip() if python_version else None
    return OverrideFormattingParams(
        line_length=line_length,
        sql_dialect=sql_dialect,
        python_version=normalized_python_version,
    )


def _override_threshold_dependency(
    max_complexity: Annotated[int | None, typer.Option(None, "--max-complexity", min=1, help=MAX_COMPLEXITY_HELP)],
    max_arguments: Annotated[int | None, typer.Option(None, "--max-arguments", min=1, help=MAX_ARGUMENTS_HELP)],
) -> OverrideThresholdParams:
    """Return shared threshold overrides for complexity heuristics.

    Args:
        max_complexity: Upper bound for cyclomatic complexity.
        max_arguments: Upper bound for function arguments.

    Returns:
        OverrideThresholdParams: Structured complexity overrides.
    """

    return OverrideThresholdParams(max_complexity=max_complexity, max_arguments=max_arguments)


def _override_strictness_dependency(
    type_checking: Annotated[
        str | None, typer.Option(None, "--type-checking", case_sensitive=False, help=TYPE_CHECKING_HELP)
    ],
) -> OverrideStrictnessParams:
    """Return strictness overrides for type-checking controls.

    Args:
        type_checking: Optional strictness value provided on the CLI.

    Returns:
        OverrideStrictnessParams: Structured strictness overrides.
    """

    return OverrideStrictnessParams(type_checking=_coerce_optional_strictness(type_checking))


def _override_params_dependency(
    formatting: Annotated[OverrideFormattingParams, Depends(_override_formatting_dependency)],
    thresholds: Annotated[OverrideThresholdParams, Depends(_override_threshold_dependency)],
    strictness: Annotated[OverrideStrictnessParams, Depends(_override_strictness_dependency)],
) -> LintOverrideParams:
    """Combine override parameters into the shape expected by lint.

    Args:
        formatting: Formatting overrides including line length and dialect.
        thresholds: Complexity-related thresholds.
        strictness: Type-checking strictness overrides.

    Returns:
        LintOverrideParams: Structured override configuration for lint.
    """

    return LintOverrideParams(
        line_length=formatting.line_length,
        sql_dialect=formatting.sql_dialect,
        max_complexity=thresholds.max_complexity,
        max_arguments=thresholds.max_arguments,
        type_checking=strictness.type_checking,
        python_version=formatting.python_version,
    )


__all__ = [
    "_override_formatting_dependency",
    "_override_params_dependency",
    "_override_strictness_dependency",
    "_override_threshold_dependency",
]
