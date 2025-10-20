# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tool selection dependency factories for the lint CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from ..params import LintSelectionParams
from .constants import FILTER_HELP


def _selection_params_dependency(
    filters: Annotated[list[str], typer.Option([], "--filter", help=FILTER_HELP)],
    only: Annotated[list[str], typer.Option([], help="Run only the selected tool(s).")],
    language: Annotated[list[str], typer.Option([], help="Filter tools by language.")],
    fix_only: Annotated[bool, typer.Option(False, help="Run only fix-capable actions.")],
    check_only: Annotated[bool, typer.Option(False, help="Run only check actions.")],
) -> LintSelectionParams:
    """Return structured selection parameters based on CLI filters.

    Args:
        filters: Regex filters applied to tool output.
        only: Explicit tool selection overrides.
        language: Languages used to restrict tool execution.
        fix_only: Whether to run only fix-capable tools.
        check_only: Whether to run only check-oriented tools.

    Returns:
        LintSelectionParams: Structured selection configuration for lint.
    """

    return LintSelectionParams(
        filters=list(filters),
        only=list(only),
        language=list(language),
        fix_only=fix_only,
        check_only=check_only,
    )


__all__ = ["_selection_params_dependency"]
