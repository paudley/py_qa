# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Provide configuration models for generic value-type analysis."""

from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import BaseModel, Field, model_validator

from .base import ConfigError

TRIGGER_SEPARATOR: Final[str] = ":"


class ValueTypeFindingSeverity(str, Enum):
    """Provide enumeration of severities emitted by value-type checks."""

    ERROR = "error"
    WARNING = "warning"


class ValueTypeTriggerKind(str, Enum):
    """Provide enumeration of trigger kinds for value-type implications."""

    METHOD = "method"
    TRAIT = "trait"


class GenericValueTypesImplication(BaseModel):
    """Describe a derived method recommendation for value types."""

    trigger: str
    require: tuple[str, ...] = Field(default_factory=tuple)
    recommend: tuple[str, ...] = Field(default_factory=tuple)
    severity: ValueTypeFindingSeverity = ValueTypeFindingSeverity.WARNING
    traits: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _normalize(self) -> GenericValueTypesImplication:
        """Canonicalize implication trigger metadata.

        Returns:
            GenericValueTypesImplication: The normalized implication instance.

        """

        trigger = self.trigger.strip()
        if not trigger:
            msg = "generic_value_types.implications.trigger cannot be blank"
            raise ConfigError(msg)
        self.trigger = trigger.lower()
        self.traits = tuple(sorted({trait.strip() for trait in self.traits if trait.strip()}))
        self.require = tuple(sorted({method.strip() for method in self.require if method.strip()}))
        self.recommend = tuple(sorted({method.strip() for method in self.recommend if method.strip()}))
        return self

    def parsed_trigger(self) -> tuple[ValueTypeTriggerKind, str]:
        """Return the trigger kind/value pair derived from configuration.

        Returns:
            tuple[ValueTypeTriggerKind, str]: Trigger kind and trigger value
            pair extracted from the stored trigger string.

        """

        token = self.trigger
        if TRIGGER_SEPARATOR not in token:
            return ValueTypeTriggerKind.METHOD, token
        prefix, value = (segment.strip() for segment in token.split(TRIGGER_SEPARATOR, 1))
        try:
            kind = ValueTypeTriggerKind(prefix)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ConfigError(f"Unsupported implication trigger kind '{prefix}'") from exc
        if not value:
            msg = "generic_value_types.implications.trigger must include a value"
            raise ConfigError(msg)
        return kind, value


class GenericValueTypesRule(BaseModel):
    """Describe explicit dunder expectations for value-type rules."""

    pattern: str
    traits: tuple[str, ...] = Field(default_factory=tuple)
    require: tuple[str, ...] = Field(default_factory=tuple)
    recommend: tuple[str, ...] = Field(default_factory=tuple)
    allow_missing: tuple[str, ...] = Field(default_factory=tuple)
    description: str | None = None

    @model_validator(mode="after")
    def _normalize(self) -> GenericValueTypesRule:
        """Return rule configuration inputs in canonical order.

        Returns:
            GenericValueTypesRule: The normalized rule instance.

        """

        pattern = self.pattern.strip()
        if not pattern:
            msg = "generic_value_types.rules.pattern cannot be blank"
            raise ConfigError(msg)
        self.pattern = pattern
        self.traits = tuple(sorted({trait.strip() for trait in self.traits if trait.strip()}))
        self.require = tuple(sorted({method.strip() for method in self.require if method.strip()}))
        self.recommend = tuple(sorted({method.strip() for method in self.recommend if method.strip()}))
        self.allow_missing = tuple(sorted({method.strip() for method in self.allow_missing if method.strip()}))
        if self.description is not None:
            description = self.description.strip()
            self.description = description or None
        return self


class GenericValueTypesConfig(BaseModel):
    """Provide configuration for the generic value-type recommender."""

    enabled: bool = False
    rules: tuple[GenericValueTypesRule, ...] = Field(default_factory=tuple)
    implications: tuple[GenericValueTypesImplication, ...] = Field(default_factory=lambda: DEFAULT_IMPLICATIONS)


DEFAULT_IMPLICATIONS: Final[tuple[GenericValueTypesImplication, ...]] = (
    GenericValueTypesImplication(
        trigger="method:__iter__",
        require=("__len__", "__contains__"),
        severity=ValueTypeFindingSeverity.WARNING,
    ),
    GenericValueTypesImplication(
        trigger="method:__len__",
        require=("__bool__",),
        severity=ValueTypeFindingSeverity.WARNING,
    ),
    GenericValueTypesImplication(
        trigger="method:__eq__",
        require=("__hash__",),
        recommend=("__repr__", "__str__"),
        severity=ValueTypeFindingSeverity.WARNING,
    ),
)


__all__ = [
    "GenericValueTypesConfig",
    "GenericValueTypesImplication",
    "GenericValueTypesRule",
    "DEFAULT_IMPLICATIONS",
    "ValueTypeFindingSeverity",
    "ValueTypeTriggerKind",
]
