# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Dataclasses and helpers for lint CLI override application."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from ..config import (
    BanditConfidence,
    BanditLevel,
    Config,
    SensitivityLevel,
    StrictnessLevel,
)

EnumValueT = TypeVar("EnumValueT", bound=Enum)


@dataclass(frozen=True)
class SeverityOverrides:
    """CLI-provided overrides for severity-related configuration."""

    sensitivity: SensitivityLevel | None = None
    bandit_level: BanditLevel | None = None
    bandit_confidence: BanditConfidence | None = None
    pylint_fail_under: float | None = None

    def updates(self) -> dict[str, object]:
        """Return a mapping of overridden severity fields.

        Returns:
            dict[str, object]: Keys and values that should overwrite the
            configuration severity section.
        """

        payload: dict[str, object] = {}
        if self.sensitivity is not None:
            payload["sensitivity"] = self.sensitivity
        if self.bandit_level is not None:
            payload["bandit_level"] = self.bandit_level
        if self.bandit_confidence is not None:
            payload["bandit_confidence"] = self.bandit_confidence
        if self.pylint_fail_under is not None:
            payload["pylint_fail_under"] = self.pylint_fail_under
        return payload

    def has_updates(self) -> bool:
        """Return ``True`` when any overrides were provided."""

        return bool(self.updates())


@dataclass(frozen=True)
class ComplexityOverrides:
    """CLI-provided overrides for complexity-related configuration."""

    max_complexity: int | None = None
    max_arguments: int | None = None

    def updates(self) -> dict[str, int | None]:
        """Return the complexity thresholds that should be overridden."""

        payload: dict[str, int | None] = {}
        if self.max_complexity is not None:
            payload["max_complexity"] = self.max_complexity
        if self.max_arguments is not None:
            payload["max_arguments"] = self.max_arguments
        return payload

    def has_updates(self) -> bool:
        """Return ``True`` when a complexity override has been supplied."""

        return bool(self.updates())


@dataclass(frozen=True)
class StrictnessOverrides:
    """CLI-provided overrides for strictness-related configuration."""

    type_checking: StrictnessLevel | None = None

    def updates(self) -> dict[str, StrictnessLevel]:
        """Return the strictness overrides to apply."""

        return {"type_checking": self.type_checking} if self.type_checking is not None else {}

    def has_updates(self) -> bool:
        """Return ``True`` when a strictness override has been provided."""

        return self.type_checking is not None


def apply_severity_overrides(config: Config, overrides: SeverityOverrides) -> Config:
    """Apply severity overrides to ``config`` and return the updated model."""

    if not overrides.has_updates():
        return config
    return config.model_copy(
        update={"severity": config.severity.model_copy(update=overrides.updates())},
    )


def apply_complexity_overrides(config: Config, overrides: ComplexityOverrides) -> Config:
    """Return ``config`` with complexity overrides applied."""

    if not overrides.has_updates():
        return config
    return config.model_copy(
        update={"complexity": config.complexity.model_copy(update=overrides.updates())},
    )


def apply_strictness_overrides(config: Config, overrides: StrictnessOverrides) -> Config:
    """Return ``config`` with strictness overrides applied."""

    if not overrides.has_updates():
        return config
    return config.model_copy(
        update={"strictness": config.strictness.model_copy(update=overrides.updates())},
    )


def coerce_enum_value(raw: str, enum_cls: type[EnumValueT], context: str) -> EnumValueT:
    """Translate a CLI token into a strongly typed enumeration value."""

    candidate = raw.strip().lower()
    for member in enum_cls:
        if member.value == candidate:
            return member
    allowed = ", ".join(sorted(member.value for member in enum_cls))
    raise ValueError(f"{context} must be one of: {allowed}")


__all__ = [
    "SeverityOverrides",
    "ComplexityOverrides",
    "StrictnessOverrides",
    "apply_severity_overrides",
    "apply_complexity_overrides",
    "apply_strictness_overrides",
    "coerce_enum_value",
]
