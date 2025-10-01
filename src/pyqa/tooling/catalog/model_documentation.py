# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Documentation resources resolved from catalog metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .errors import CatalogIntegrityError
from .types import JSONValue
from .utils import expect_mapping, optional_string


@dataclass(frozen=True, slots=True)
class DocumentationEntry:
    """Documentation resource resolved from catalog metadata."""

    format: str
    content: str

    @staticmethod
    def from_mapping(
        data: Mapping[str, JSONValue],
        *,
        context: str,
        catalog_root: Path,
        source: Path,
    ) -> DocumentationEntry:
        """Create documentation entry metadata from JSON data.

        Args:
            data: Mapping describing the documentation entry.
            context: Human-readable context used in error messages.
            catalog_root: Root path for catalog-relative includes.
            source: Path to the originating JSON document.

        Returns:
            DocumentationEntry: Frozen documentation payload referenced by the catalog.

        Raises:
            CatalogIntegrityError: If the documentation mapping is invalid or unreadable.

        """

        format_value = optional_string(data.get("format"), key="format", context=context) or "text"
        text_value = data.get("text")
        if isinstance(text_value, str):
            return DocumentationEntry(format=format_value, content=text_value)
        path_value = data.get("path")
        if isinstance(path_value, str):
            doc_path = Path(path_value)
            if not doc_path.is_absolute():
                doc_path = (catalog_root / path_value).resolve()
                if not doc_path.exists():
                    doc_path = (source.parent / path_value).resolve()
            if not doc_path.is_file():
                raise CatalogIntegrityError(
                    f"{context}: documentation path '{path_value}' not found",
                )
            try:
                content = doc_path.read_text(encoding="utf-8")
            except OSError as exc:  # pragma: no cover - filesystem failure
                raise CatalogIntegrityError(
                    f"{context}: unable to read documentation '{doc_path}'",
                ) from exc
            return DocumentationEntry(format=format_value, content=content)
        raise CatalogIntegrityError(
            f"{context}: documentation entry must define either 'text' or 'path'",
        )


@dataclass(frozen=True, slots=True)
class DocumentationBundle:
    """Grouped documentation resources for a tool."""

    help: DocumentationEntry | None
    command: DocumentationEntry | None
    shared: DocumentationEntry | None

    @staticmethod
    def from_mapping(
        data: Mapping[str, JSONValue],
        *,
        context: str,
        catalog_root: Path,
        source: Path,
    ) -> DocumentationBundle:
        """Create a ``DocumentationBundle`` from JSON data.

        Args:
            data: Mapping describing the documentation bundle metadata.
            context: Human-readable context used in error messages.
            catalog_root: Root directory that hosts documentation assets.
            source: Path to the catalog document referencing the bundle.

        Returns:
            DocumentationBundle: Frozen documentation bundle with resolved content.

        Raises:
            CatalogIntegrityError: If none of the documentation entries are present or
                a referenced entry is invalid.

        """

        help_entry = documentation_entry(
            data.get("help"),
            context=f"{context}.help",
            catalog_root=catalog_root,
            source=source,
        )
        command_entry = documentation_entry(
            data.get("commandHelp"),
            context=f"{context}.commandHelp",
            catalog_root=catalog_root,
            source=source,
        )
        shared_entry = documentation_entry(
            data.get("shared"),
            context=f"{context}.shared",
            catalog_root=catalog_root,
            source=source,
        )
        if help_entry is None and command_entry is None and shared_entry is None:
            raise CatalogIntegrityError(
                f"{context}: documentation block must include at least one entry",
            )
        return DocumentationBundle(help=help_entry, command=command_entry, shared=shared_entry)


def documentation_entry(
    value: JSONValue | None,
    *,
    context: str,
    catalog_root: Path,
    source: Path,
) -> DocumentationEntry | None:
    """Return an optional documentation entry from the provided value.

    Args:
        value: JSON value that should describe the documentation entry.
        context: Human-readable context used in error messages.
        catalog_root: Root directory that hosts documentation assets.
        source: Path to the catalog document referencing the entry.

    Returns:
        DocumentationEntry | None: Parsed documentation entry or ``None`` when the
            value is not provided.

    Raises:
        CatalogIntegrityError: If the value is not a mapping or is otherwise invalid.

    """

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError(f"{context}: documentation entry must be an object")
    mapping = expect_mapping(value, key="documentation", context=context)
    return DocumentationEntry.from_mapping(
        mapping,
        context=context,
        catalog_root=catalog_root,
        source=source,
    )


__all__ = [
    "DocumentationBundle",
    "DocumentationEntry",
    "documentation_entry",
]
