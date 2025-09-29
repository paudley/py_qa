"""High-level loader that materialises catalog definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence, cast

from jsonschema import exceptions as jsonschema_exceptions

from .checksum import compute_catalog_checksum
from .errors import CatalogIntegrityError, CatalogValidationError
from .io import load_document
from .models import (
    CatalogFragment,
    CatalogSnapshot,
    StrategyDefinition,
    ToolDefinition,
)
from .resolver import resolve_tool_mapping, to_plain_json
from .scanner import CatalogScanner
from .schema import SchemaRepository
from .types import JSONValue
from .utils import expect_mapping


@dataclass(slots=True)
class ToolCatalogLoader:
    """Loader that validates and materialises tool and strategy catalog entries."""

    catalog_root: Path
    schema_root: Path | None = None
    _schemas: SchemaRepository = field(init=False, repr=False)
    _scanner: CatalogScanner = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._schemas = SchemaRepository.load(
            catalog_root=self.catalog_root,
            schema_root=self.schema_root,
        )
        self.schema_root = self._schemas.schema_root
        self._scanner = CatalogScanner(self.catalog_root)

    def load_fragments(self) -> tuple[CatalogFragment, ...]:
        """Load shared catalog fragments."""

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
                )
            )
        return tuple(fragments)

    def load_strategy_definitions(self) -> tuple[StrategyDefinition, ...]:
        """Load catalog-defined strategies from disk."""

        definitions: list[StrategyDefinition] = []
        for path in self._scanner.strategy_documents():
            document = load_document(path)
            self._validate_document(document, validator="strategy", path=path)
            mapping = expect_mapping(document, key="<root>", context=str(path))
            definition = StrategyDefinition.from_mapping(mapping, source=path)
            _validate_strategy_implementation(definition)
            definitions.append(definition)
        return tuple(definitions)

    def load_tool_definitions(
        self,
        *,
        fragments: Sequence[CatalogFragment] | None = None,
    ) -> tuple[ToolDefinition, ...]:
        """Load all tool definitions contained in the catalog root."""

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
            plain_mapping = cast(Mapping[str, JSONValue], to_plain_json(resolved_mapping))
            self._validate_document(plain_mapping, validator="tool", path=path)
            definitions.append(
                ToolDefinition.from_mapping(
                    resolved_mapping,
                    source=path,
                    catalog_root=self.catalog_root,
                )
            )
        return tuple(definitions)

    def load_snapshot(self) -> CatalogSnapshot:
        """Load tools, strategies, and fragments with checksum metadata."""

        fragments = self.load_fragments()
        strategies = self.load_strategy_definitions()
        tools = self.load_tool_definitions(fragments=fragments)
        checksum = self.compute_checksum()
        return CatalogSnapshot(
            tools=tools,
            strategies=strategies,
            fragments=fragments,
            checksum=checksum,
        )

    def compute_checksum(self) -> str:
        """Return a checksum representing the current catalog contents."""

        paths = self._scanner.catalog_files()
        return compute_catalog_checksum(self.catalog_root, paths)

    def _validate_document(
        self,
        document: Mapping[str, JSONValue] | JSONValue,
        *,
        validator: str,
        path: Path,
    ) -> None:
        if validator == "tool":
            schema_validator = self._schemas.tool_validator
        elif validator == "strategy":
            schema_validator = self._schemas.strategy_validator
        else:  # pragma: no cover - defensive programming
            raise ValueError(f"unknown validator kind '{validator}'")
        try:
            schema_validator.validate(document)
        except jsonschema_exceptions.ValidationError as exc:
            raise CatalogValidationError(f"{path}: {exc.message}") from exc


__all__ = ["ToolCatalogLoader"]


def _validate_strategy_implementation(definition: StrategyDefinition) -> None:
    """Validate that a strategy definition points to an importable implementation."""

    import importlib

    try:
        if definition.entry is not None:
            module = importlib.import_module(definition.implementation)
            if not hasattr(module, definition.entry):
                raise CatalogIntegrityError(
                    f"{definition.source}: missing entry '{definition.entry}' on module '{definition.implementation}'"
                )
            getattr(module, definition.entry)
            return

        module_path, _, attribute_name = definition.implementation.rpartition(".")
        if not module_path:
            raise CatalogIntegrityError(
                f"{definition.source}: implementation '{definition.implementation}' must include a module path"
            )
        module = importlib.import_module(module_path)
        getattr(module, attribute_name)
    except (ImportError, AttributeError) as exc:
        raise CatalogIntegrityError(
            f"{definition.source}: unable to import strategy implementation '{definition.implementation}'"
        ) from exc
