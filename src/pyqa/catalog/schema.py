# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Schema loading utilities for validating catalog documents."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from .io import load_schema
from .types import JSONValue


@runtime_checkable
class SchemaValidator(Protocol):
    """Protocol describing the minimal interface exposed by jsonschema validators."""

    def validate(self, instance: JSONValue) -> None:
        """Validate ``instance`` against the bound schema."""

    def iter_errors(self, instance: JSONValue) -> object:
        """Yield validation errors for ``instance`` without raising immediately."""


SchemaValidatorFactory = Callable[[JSONValue], SchemaValidator]


jsonschema_module = importlib.import_module("jsonschema")
Draft202012Validator = cast(SchemaValidatorFactory, jsonschema_module.Draft202012Validator)


@dataclass(slots=True)
class SchemaRepository:
    """Container for catalog JSON schema validators."""

    schema_root: Path
    tool_validator: SchemaValidator
    strategy_validator: SchemaValidator

    @classmethod
    def load(cls, *, catalog_root: Path, schema_root: Path | None = None) -> SchemaRepository:
        """Load schema validators from disk."""
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
