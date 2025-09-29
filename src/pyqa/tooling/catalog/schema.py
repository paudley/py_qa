# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Schema loading utilities for validating catalog documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from .io import load_schema


@dataclass(slots=True)
class SchemaRepository:
    """Container for catalog JSON schema validators."""

    schema_root: Path
    tool_validator: Draft202012Validator
    strategy_validator: Draft202012Validator

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
