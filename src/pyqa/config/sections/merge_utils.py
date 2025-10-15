# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Provide shared helpers for configuration section mergers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Generic, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from ..models import ConfigError
from ..types import ConfigValue

ModelScalarUpdate: TypeAlias = ConfigValue | Path | BaseModel
ModelSequenceUpdate: TypeAlias = Sequence[ConfigValue | Path | BaseModel]
ModelMappingUpdate: TypeAlias = Mapping[str, ConfigValue | Path | BaseModel]
ModelUpdateValue: TypeAlias = ModelScalarUpdate | ModelSequenceUpdate | ModelMappingUpdate

ConfigMapping: TypeAlias = Mapping[str, ConfigValue]
SectionDiff: TypeAlias = dict[str, ConfigValue]
SectionName: TypeAlias = str
FieldName: TypeAlias = str
ModelT = TypeVar("ModelT", bound=BaseModel)


class PathResolver(BaseModel):
    """Resolve path-like configuration values relative to a project root."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_root: Path

    @model_validator(mode="after")
    def _normalise_root(self) -> PathResolver:
        """Normalize the resolver by coercing the project root to absolute.

        Returns:
            PathResolver: Resolver instance with an absolute project root.

        """

        object.__setattr__(self, "project_root", self.project_root.resolve())
        return self

    def resolve(self, value: Path | str) -> Path:
        """Resolve ``value`` against the configured project root.

        Args:
            value: Path-like object to resolve relative to the project root.

        Returns:
            Path: Absolute path derived from ``value``.

        """

        candidate = value if isinstance(value, Path) else Path(value)
        candidate = candidate.expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.project_root / candidate).resolve()

    def resolve_optional(self, value: Path | str | None) -> Path | None:
        """Resolve ``value`` when provided, returning ``None`` otherwise.

        Args:
            value: Optional path-like object to resolve.

        Returns:
            Optional[Path]: Absolute path when ``value`` is provided.

        """

        if value is None:
            return None
        return self.resolve(value)

    def resolve_iterable(self, values: Iterable[Path | str]) -> list[Path]:
        """Resolve a collection of path-like values.

        Args:
            values: Iterable of path-like objects to resolve.

        Returns:
            list[Path]: Absolute paths corresponding to ``values``.

        """

        return [self.resolve(value) for value in values]


def _ensure_optional_path(value: ConfigValue | Path | None, context: str) -> Path | str | None:
    """Ensure optional path-like configuration values are valid.

    Args:
        value: Value supplied for a path-aware configuration option.
        context: Dot-delimited configuration key for error reporting.

    Returns:
        Optional[Path | str]: Original value when valid or ``None``.

    Raises:
        ConfigError: If ``value`` is neither ``None`` nor path-like.

    """

    if value is None:
        return None
    if isinstance(value, (str, Path)):
        return value
    raise ConfigError(f"{context} must be a path-like string")


def _model_replace(
    instance: ModelT,
    updates: Mapping[str, ModelUpdateValue] | None = None,
) -> ModelT:
    """Return a cloned model instance with the provided updates applied.

    Args:
        instance: Pydantic model instance to clone.
        updates: Mapping of field overrides applied to the clone.

    Returns:
        ModelT: Cloned instance containing requested overrides.

    """

    if not isinstance(instance, BaseModel):  # defensive guard for legacy usage
        raise TypeError("_model_replace expects a Pydantic BaseModel instance")
    return instance.model_copy(update=dict(updates or {}), deep=True)


def _coerce_optional_str_value(
    value: ConfigValue,
    current: str | None,
    context: str,
) -> str | None:
    """Coerce optional string values while preserving ``None`` defaults.

    Args:
        value: Raw configuration value.
        current: Existing value preserved when ``value`` is ``None``.
        context: Dot-delimited configuration key for error reporting.

    Returns:
        Optional[str]: Normalised string value or ``None``.

    Raises:
        ConfigError: If ``value`` cannot be converted into a string.

    """

    if value is None:
        return current
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    raise ConfigError(f"{context} must be a string")


def _coerce_optional_bool(value: ConfigValue, current: bool, context: str) -> bool:
    """Return optional boolean values while preserving defaults.

    Args:
        value: Raw configuration value.
        current: Existing value preserved when ``value`` is ``None``.
        context: Dot-delimited configuration key for error reporting.

    Returns:
        bool: Boolean value recognised by the configuration model.

    Raises:
        ConfigError: If ``value`` cannot be interpreted as a boolean.

    """

    if value is None:
        return current
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{context} must be a boolean")


class _SectionMerger(Generic[ModelT], ABC):
    """Provide base utilities for section-specific merge implementations."""

    section: SectionName

    def describe_section(self) -> SectionName:
        """Describe the section identifier managed by the merger.

        Returns:
            SectionName: Identifier for the section managed by the merger.

        """

        return self.section

    @abstractmethod
    def merge(self, current: ModelT, raw: ConfigValue) -> tuple[ModelT, SectionDiff]:
        """Merge ``raw`` values into ``current`` returning the new state and diff.

        Args:
            current: Existing configuration model instance.
            raw: Raw section payload sourced from configuration files.

        Returns:
            tuple[ModelT, SectionDiff]: Merged model alongside the applied diff.

        """

    @staticmethod
    def _ensure_mapping(raw: ConfigValue, section: str) -> ConfigMapping:
        """Validate ``raw`` ensuring it is a mapping for ``section`` processing.

        Args:
            raw: Raw configuration payload for the section.
            section: Section identifier used for error messaging.

        Returns:
            ConfigMapping: Mapping view of the section payload.

        Raises:
            ConfigError: If ``raw`` is not a mapping.

        """

        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{section} section must be a table")
        result: dict[str, ConfigValue] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                raise ConfigError(f"{section} section keys must be strings")
            result[key] = value
        return result

    @staticmethod
    def _diff_model(current: BaseModel, updated: BaseModel) -> SectionDiff:
        """Computes the field-level diff between ``current`` and ``updated`` models.

        Args:
            current: Baseline Pydantic model instance.
            updated: Updated model instance.

        Returns:
            SectionDiff: Mapping containing only the fields that changed.

        """

        current_data = current.model_dump(mode="python")
        updated_data = updated.model_dump(mode="python")
        result: SectionDiff = {}
        for key, value in updated_data.items():
            if current_data.get(key) != value:
                result[key] = value
        return result


__all__ = [
    "ConfigMapping",
    "FieldName",
    "ModelMappingUpdate",
    "ModelScalarUpdate",
    "ModelSequenceUpdate",
    "ModelUpdateValue",
    "ModelT",
    "PathResolver",
    "SectionDiff",
    "SectionName",
    "_SectionMerger",
    "_coerce_optional_bool",
    "_coerce_optional_str_value",
    "_ensure_optional_path",
    "_model_replace",
]
