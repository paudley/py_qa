# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Schema loading utilities for validating catalog documents."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from .io import load_schema
from .types import JSONValue


class SchemaValidationError(Protocol):
    """Represent schema validation errors surfaced by jsonschema."""

    @property
    def message(self) -> str:
        """Return the descriptive validation error message.

        Returns:
            str: Human-readable message describing the validation failure.
        """

    @classmethod
    def __subclasshook__(cls, subclass: type, /) -> bool:
        """Return ``True`` when ``subclass`` exposes a jsonschema error interface.

        Args:
            subclass: Candidate class inspected during ``issubclass`` checks.

        Returns:
            bool: ``True`` when ``subclass`` defines a ``message`` attribute.
        """

        return hasattr(subclass, "message")


@runtime_checkable
class SchemaValidator(Protocol):
    """Protocol describing the minimal interface exposed by jsonschema validators."""

    def validate(self, instance: JSONValue) -> None:
        """Validate ``instance`` against the bound schema.

        Args:
            instance: JSON payload to validate against the schema.

        Raises:
            Exception: Implementations may raise jsonschema validation errors when invalid.
        """

    def iter_errors(self, instance: JSONValue) -> Iterable[SchemaValidationError]:
        """Iterate over validation errors for ``instance``.

        Args:
            instance: JSON payload to validate against the schema.

        Returns:
            Iterable[SchemaValidationError]: Iterator yielding validation errors.
        """

    @classmethod
    def __subclasshook__(cls, subclass: type, /) -> bool:
        """Return ``True`` when ``subclass`` provides jsonschema validator hooks.

        Args:
            subclass: Candidate class inspected during ``issubclass`` checks.

        Returns:
            bool: ``True`` when ``subclass`` implements ``validate`` and ``iter_errors``.
        """

        return hasattr(subclass, "validate") and hasattr(subclass, "iter_errors")


SchemaValidatorFactory = Callable[[JSONValue], SchemaValidator]


jsonschema_module = importlib.import_module("jsonschema")
Draft202012Validator = cast(SchemaValidatorFactory, jsonschema_module.Draft202012Validator)


@dataclass(slots=True)
class SchemaRepository:
    """Manage catalog JSON schema validators for tools and strategies."""

    schema_root: Path
    tool_validator: SchemaValidator
    strategy_validator: SchemaValidator

    @classmethod
    def load(cls, *, catalog_root: Path, schema_root: Path | None = None) -> SchemaRepository:
        """Load schema validators from disk.

        Args:
            catalog_root: Root directory containing the catalog.
            schema_root: Optional override for the schema directory.

        Returns:
            SchemaRepository: Repository configured with tool and strategy validators.
        """
        resolved_root = schema_root or (catalog_root.parent / "schema")
        tool_schema_path = resolved_root / "tool_definition.schema.json"
        strategy_schema_path = resolved_root / "strategy_definition.schema.json"
        tool_schema = load_schema(tool_schema_path)
        strategy_schema = load_schema(strategy_schema_path)
        return cls(
            schema_root=resolved_root,
            tool_validator=Draft202012Validator(tool_schema),
            strategy_validator=Draft202012Validator(strategy_schema),
        )


__all__ = ["SchemaRepository"]
