# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Coercion helpers for lint CLI options."""

from __future__ import annotations

from typing import cast

import typer

from ....core.lint_literals import StrictnessLiteral
from ..literals import (
    BANDIT_LEVEL_CHOICES,
    OUTPUT_MODE_CHOICES,
    PR_SUMMARY_SEVERITIES,
    SENSITIVITY_CHOICES,
    STRICTNESS_CHOICES,
    BanditLevelLiteral,
    OutputModeLiteral,
    PRSummarySeverityLiteral,
    SensitivityLiteral,
)


def _coerce_choice(value: str, *, option_name: str, choices: tuple[str, ...]) -> str:
    """Normalise a string option and validate membership.

    Args:
        value: Raw user-supplied value to coerce.
        option_name: CLI option name used to build error messages.
        choices: Allowed choices for the option.

    Returns:
        str: Lower-cased value guaranteed to exist within ``choices``.

    Raises:
        typer.BadParameter: If ``value`` is not present in ``choices``.
    """

    normalized = value.lower()
    if normalized not in choices:
        allowed = ", ".join(choices)
        raise typer.BadParameter(f"{option_name} must be one of: {allowed}")
    return normalized


def _coerce_output_mode(value: str) -> OutputModeLiteral:
    """Return a validated output mode literal.

    Args:
        value: Raw output mode supplied via the CLI.

    Returns:
        OutputModeLiteral: Normalised output mode value.

    Raises:
        typer.BadParameter: If ``value`` does not map to a permitted mode.
    """

    coerced = _coerce_choice(value, option_name="--output", choices=OUTPUT_MODE_CHOICES)
    return cast(OutputModeLiteral, coerced)


def _coerce_optional_strictness(value: str | None) -> StrictnessLiteral | None:
    """Return a validated strictness literal when supplied.

    Args:
        value: Optional strictness value obtained from CLI flags.

    Returns:
        StrictnessLiteral | None: Normalised strictness or ``None`` when not provided.

    Raises:
        typer.BadParameter: If ``value`` falls outside the allowed set.
    """

    if value is None:
        return None
    coerced = _coerce_choice(value, option_name="--type-checking", choices=STRICTNESS_CHOICES)
    return cast(StrictnessLiteral, coerced)


def _coerce_optional_bandit(value: str | None, *, option_name: str) -> BanditLevelLiteral | None:
    """Return a validated Bandit level literal when supplied.

    Args:
        value: Optional Bandit level provided by the user.
        option_name: CLI option name used for error messaging.

    Returns:
        BanditLevelLiteral | None: Normalised severity or confidence value.

    Raises:
        typer.BadParameter: If ``value`` does not belong to the allowed set.
    """

    if value is None:
        return None
    coerced = _coerce_choice(value, option_name=option_name, choices=BANDIT_LEVEL_CHOICES)
    return cast(BanditLevelLiteral, coerced)


def _coerce_optional_sensitivity(value: str | None) -> SensitivityLiteral | None:
    """Return a validated sensitivity literal when supplied.

    Args:
        value: Optional sensitivity value provided via CLI arguments.

    Returns:
        SensitivityLiteral | None: Normalised sensitivity or ``None`` if not provided.

    Raises:
        typer.BadParameter: If ``value`` is outside the allowed set.
    """

    if value is None:
        return None
    coerced = _coerce_choice(value, option_name="--sensitivity", choices=SENSITIVITY_CHOICES)
    return cast(SensitivityLiteral, coerced)


def _coerce_pr_summary_severity(value: str) -> PRSummarySeverityLiteral:
    """Return a normalised PR summary severity literal.

    Args:
        value: Raw severity supplied on the CLI.

    Returns:
        PRSummarySeverityLiteral: Normalised severity literal.

    Raises:
        typer.BadParameter: If ``value`` is not one of the permitted severities.
    """

    coerced = _coerce_choice(
        value,
        option_name="--pr-summary-min-severity",
        choices=PR_SUMMARY_SEVERITIES,
    )
    return cast(PRSummarySeverityLiteral, coerced)


__all__ = [
    "_coerce_choice",
    "_coerce_optional_bandit",
    "_coerce_optional_sensitivity",
    "_coerce_optional_strictness",
    "_coerce_output_mode",
    "_coerce_pr_summary_severity",
]
