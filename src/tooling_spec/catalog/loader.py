# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""High-level loader that materialises catalog definitions."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Final, Literal, cast

from .checksum import compute_catalog_checksum
from .errors import CatalogIntegrityError, CatalogValidationError
from .io import load_document
from .model_catalog import CatalogFragment, CatalogSnapshot
from .model_strategy import StrategyDefinition
from .model_tool import ToolDefinition
from .plugins import (
    CatalogPluginContext,
    combine_checksums,
    load_plugin_contributions,
    merge_contributions,
)
from .resolver import resolve_tool_mapping, to_plain_json
from .scanner import CatalogScanner
from .schema import SchemaRepository
from .types import JSONValue
from .utils import expect_mapping

jsonschema_module = importlib.import_module("jsonschema")
jsonschema_exceptions: ModuleType = cast(ModuleType, jsonschema_module.exceptions)
JsonSchemaValidationError = cast(type[Exception], getattr(jsonschema_exceptions, "ValidationError"))

ValidatorKind = Literal["tool", "strategy"]
TOOL_VALIDATOR: Final[ValidatorKind] = "tool"
STRATEGY_VALIDATOR: Final[ValidatorKind] = "strategy"


@dataclass(slots=True)
class ToolCatalogLoader:
    """Loader that validates and materialises tool and strategy catalog entries."""

    catalog_root: Path
    schema_root: Path | None = None
    _schemas: SchemaRepository = field(init=False, repr=False)
    _scanner: CatalogScanner = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize schema repositories and scanners after dataclass setup."""

        self._schemas = SchemaRepository.load(
            catalog_root=self.catalog_root,
            schema_root=self.schema_root,
        )
        self.schema_root = self._schemas.schema_root
        self._scanner = CatalogScanner(self.catalog_root)

    def load_fragments(self) -> tuple[CatalogFragment, ...]:
        """Collect catalog fragments from disk.

        Returns:
            tuple[CatalogFragment, ...]: Fragments contributed by the catalog.
        """

        fragments: list[CatalogFragment] = []
        for path in self._scanner.fragment_documents():
            document = load_document(path)
            mapping = expect_mapping(document, key="<root>", context=str(path))
            fragment_name = path.stem.lstrip("_") or path.stem
            fragments.append(
                CatalogFragment(
                    name=fragment_name,
                    data=mapping,
                    source=path,
                ),
            )
        return tuple(fragments)

    def load_strategy_definitions(self) -> tuple[StrategyDefinition, ...]:
        """Collect catalog-defined strategies from disk.

        Returns:
            tuple[StrategyDefinition, ...]: Strategy definitions discovered under ``catalog_root``.
        """

        definitions: list[StrategyDefinition] = []
        for path in self._scanner.strategy_documents():
            document = load_document(path)
            self._validate_document(document, validator=STRATEGY_VALIDATOR, path=path)
            mapping = expect_mapping(document, key="<root>", context=str(path))
            definition = StrategyDefinition.from_mapping(mapping, source=path)
            definition.resolve_callable()
            definitions.append(definition)
        return tuple(definitions)

    def load_tool_definitions(
        self,
        *,
        fragments: Sequence[CatalogFragment] | None = None,
    ) -> tuple[ToolDefinition, ...]:
        """Load all tool definitions contained in the catalog root.

        Args:
            fragments: Optional pre-loaded fragments used to resolve ``extends`` directives.

        Returns:
            tuple[ToolDefinition, ...]: Tool definitions discovered under ``catalog_root``.
        """

        fragment_sequence = fragments if fragments is not None else self.load_fragments()
        fragment_lookup = {fragment.name: fragment for fragment in fragment_sequence}
        definitions: list[ToolDefinition] = []
        for path in self._scanner.tool_documents():
            document = load_document(path)
            mapping = expect_mapping(document, key="<root>", context=str(path))
            resolved_mapping = resolve_tool_mapping(
                mapping,
                context=str(path),
                fragments=fragment_lookup,
            )
            plain_mapping = expect_mapping(
                to_plain_json(resolved_mapping),
                key="<root>",
                context=str(path),
            )
            self._validate_document(plain_mapping, validator=TOOL_VALIDATOR, path=path)
            definitions.append(
                ToolDefinition.from_mapping(
                    resolved_mapping,
                    source=path,
                    catalog_root=self.catalog_root,
                ),
            )
        return tuple(definitions)

    def load_snapshot(self) -> CatalogSnapshot:
        """Produce a catalog snapshot containing tools, strategies, and fragments.

        Returns:
            CatalogSnapshot: Snapshot containing catalog artifacts and checksums.
        """

        fragments = self.load_fragments()
        strategies = self.load_strategy_definitions()
        tools = self.load_tool_definitions(fragments=fragments)
        checksum = self.compute_checksum()

        context = CatalogPluginContext(
            catalog_root=self.catalog_root,
            schema_root=self.schema_root if self.schema_root is not None else self._schemas.schema_root,
            fragments=fragments,
            strategies=strategies,
            tools=tools,
            checksum=checksum,
        )
        contributions = load_plugin_contributions(context)
        if contributions:
            fragments, strategies, tools = merge_contributions(
                base_fragments=fragments,
                base_strategies=strategies,
                base_tools=tools,
                contributions=contributions,
            )
            checksum = combine_checksums(checksum, contributions)

        return CatalogSnapshot(
            _tools=tools,
            _strategies=strategies,
            _fragments=fragments,
            checksum=checksum,
        )

    def compute_checksum(self) -> str:
        """Calculate a checksum representing the current catalog contents.

        Returns:
            str: Hex-encoded checksum covering catalog-relevant files.
        """

        paths = self._scanner.catalog_files()
        return compute_catalog_checksum(self.catalog_root, paths)

    def _validate_document(
        self,
        document: Mapping[str, JSONValue] | JSONValue,
        *,
        validator: ValidatorKind,
        path: Path,
    ) -> None:
        """Validate a document against the requested schema validator.

        Args:
            document: Raw JSON payload to validate.
            validator: Validator kind indicating whether the document is a tool or strategy.
            path: Filesystem path used in error reporting.

        Raises:
            CatalogValidationError: When the document fails schema validation.
            ValueError: If an unknown validator kind is supplied.
        """

        if validator is TOOL_VALIDATOR:
            schema_validator = self._schemas.tool_validator
        elif validator is STRATEGY_VALIDATOR:
            schema_validator = self._schemas.strategy_validator
        else:  # pragma: no cover - defensive programming
            raise ValueError(f"unknown validator kind '{validator}'")
        try:
            schema_validator.validate(document)
        except JsonSchemaValidationError as exc:
            raise CatalogValidationError(f"{path}: {exc}") from exc


__all__ = [
    "CatalogIntegrityError",
    "CatalogValidationError",
    "JSONValue",
    "ToolCatalogLoader",
]
