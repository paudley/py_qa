# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Severity override dependency factories for the lint CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from ..params import LintSeverityParams
from .coercion import _coerce_optional_bandit, _coerce_optional_sensitivity
from .constants import BANDIT_CONFIDENCE_HELP, BANDIT_SEVERITY_HELP, PYLINT_FAIL_UNDER_HELP, SENSITIVITY_HELP


def _severity_params_dependency(
    bandit_severity: Annotated[
        str | None,
        typer.Option(None, "--bandit-severity", case_sensitive=False, help=BANDIT_SEVERITY_HELP),
    ],
    bandit_confidence: Annotated[
        str | None,
        typer.Option(None, "--bandit-confidence", case_sensitive=False, help=BANDIT_CONFIDENCE_HELP),
    ],
    pylint_fail_under: Annotated[float | None, typer.Option(None, "--pylint-fail-under", help=PYLINT_FAIL_UNDER_HELP)],
    sensitivity: Annotated[
        str | None,
        typer.Option(None, "--sensitivity", case_sensitive=False, help=SENSITIVITY_HELP),
    ],
) -> LintSeverityParams:
    """Return severity overrides captured from CLI options.

    Args:
        bandit_severity: Optional Bandit severity override.
        bandit_confidence: Optional Bandit confidence override.
        pylint_fail_under: Optional pylint fail-under score.
        sensitivity: Optional global sensitivity override.

    Returns:
        LintSeverityParams: Structured severity overrides.
    """

    return LintSeverityParams(
        bandit_severity=_coerce_optional_bandit(bandit_severity, option_name="--bandit-severity"),
        bandit_confidence=_coerce_optional_bandit(bandit_confidence, option_name="--bandit-confidence"),
        pylint_fail_under=pylint_fail_under,
        sensitivity=_coerce_optional_sensitivity(sensitivity),
    )


__all__ = ["_severity_params_dependency"]
