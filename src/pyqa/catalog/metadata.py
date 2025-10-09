# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers exposing curated catalog metadata to runtime consumers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from pyqa.platform.paths import get_pyqa_root

from .errors import CatalogIntegrityError
from .loader import ToolCatalogLoader
from .model_catalog import CatalogSnapshot

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CatalogOption:
    """Option metadata captured from the catalog for runtime consumers."""

    name: str
    option_type: str
    description: str
    choices: tuple[str, ...]


_DUPLICATE_HINT_KEY: Final[str] = "duplicateHints"


@lru_cache(maxsize=1)
def _cached_tool_options() -> dict[str, tuple[CatalogOption, ...]]:
    """Return cached catalog-defined option metadata keyed by tool name."""
    snapshot = _snapshot_or_error()
    options: dict[str, tuple[CatalogOption, ...]] = {}
    for definition in snapshot.tools:
        if not definition.options:
            continue
        entries = tuple(
            CatalogOption(
                name=option.name,
                option_type=option.option_type,
                description=option.description or "",
                choices=option.choices,
            )
            for option in definition.options
        )
        options[definition.name] = entries
    return options


def catalog_general_suppressions() -> dict[str, tuple[str, ...]]:
    """Return general-purpose suppression patterns keyed by tool name.

    Returns:
        dict[str, tuple[str, ...]]: Mapping of tool names to suppression
        patterns declared in the catalog.

    """
    snapshot = _snapshot_or_error()
    suppressions: dict[str, tuple[str, ...]] = {}
    for definition in snapshot.tools:
        bundle = definition.diagnostics_bundle
        suppression_def = bundle.suppressions
        if suppression_def is None or not suppression_def.general:
            continue
        suppressions[definition.name] = suppression_def.general
    return suppressions


def catalog_test_suppressions() -> dict[str, dict[str, tuple[str, ...]]]:
    """Return language→tool mappings of catalog-defined test suppressions.

    Returns:
        dict[str, dict[str, tuple[str, ...]]]: Nested mapping keyed first by
        language (lower-case) then by tool name containing suppression
        patterns.

    """
    snapshot = _snapshot_or_error()
    mapping: dict[str, dict[str, tuple[str, ...]]] = {}
    for definition in snapshot.tools:
        suppression_def = definition.diagnostics_bundle.suppressions
        if suppression_def is None or not suppression_def.tests:
            continue
        languages = definition.languages or ("*",)
        for language in languages:
            tool_map = mapping.setdefault(language.lower(), {})
            existing = list(tool_map.get(definition.name, ()))
            existing.extend(suppression_def.tests)
            tool_map[definition.name] = tuple(_dedupe_preserving_order(existing))
    return mapping


def catalog_duplicate_tools() -> dict[str, tuple[str, ...]]:
    """Return mapping of tools to other tools that emit duplicate diagnostics.

    Returns:
        dict[str, tuple[str, ...]]: Mapping of tool names to duplicate tool
        names as declared in catalog metadata.

    """
    snapshot = _snapshot_or_error()
    duplicates: dict[str, tuple[str, ...]] = {}
    for definition in snapshot.tools:
        suppression_def = definition.diagnostics_bundle.suppressions
        if suppression_def is None or not suppression_def.duplicates:
            continue
        duplicates[definition.name] = suppression_def.duplicates
    return duplicates


def catalog_duplicate_hint_codes() -> dict[str, tuple[str, ...]]:
    """Return hint codes that should trigger duplicate-advice messaging.

    Returns:
        dict[str, tuple[str, ...]]: Mapping of tool identifiers to the set of
        diagnostic codes that should generate duplicate advice.

    """
    snapshot = _snapshot_or_error()
    hints: dict[str, tuple[str, ...]] = {}
    for definition in snapshot.tools:
        diagnostics = definition.diagnostics_bundle.diagnostics
        if diagnostics is None or not diagnostics.dedupe:
            continue
        raw = diagnostics.dedupe.get(_DUPLICATE_HINT_KEY)
        if not raw:
            continue
        tokens = [token.strip() for token in raw.split(",") if token.strip()]
        if tokens:
            hints[definition.name.lower()] = tuple(dict.fromkeys(tokens))
    return hints


def catalog_duplicate_preference() -> tuple[str, ...]:
    """Return ordered tool names indicating duplicate resolution preference.

    Returns:
        tuple[str, ...]: Sequence of tool names ranked by preference for
        retaining diagnostics when duplicates are detected.

    """
    snapshot = _snapshot_or_error()
    phase_priority = {
        "format": 0,
        "lint": 1,
        "analysis": 2,
        "security": 3,
        "test": 4,
        "coverage": 5,
        "utility": 6,
    }
    ranked: list[tuple[str, tuple[str, ...], str]] = []
    duplicate_map = catalog_duplicate_tools()
    for definition in snapshot.tools:
        duplicates = duplicate_map.get(definition.name)
        if not duplicates:
            continue
        ranked.append((definition.name, duplicates, definition.phase))
    ranked.sort(
        key=lambda item: (
            phase_priority.get(item[2], len(phase_priority)),
            -len(item[1]),
            item[0],
        ),
    )
    ordered: list[str] = []
    for tool, _, _ in ranked:
        if tool not in ordered:
            ordered.append(tool)
    return tuple(ordered)


def catalog_tool_options() -> dict[str, tuple[CatalogOption, ...]]:
    """Return catalog-defined option metadata keyed by tool name.

    Returns:
        dict[str, tuple[CatalogOption, ...]]: Mapping where the key is the tool
        identifier and the value is a tuple of catalog option descriptors.

    """
    return _cached_tool_options().copy()


def clear_catalog_metadata_cache() -> None:
    """Clear cached catalog metadata to force a reload on next access."""
    _load_snapshot.cache_clear()
    _cached_tool_options.cache_clear()


@lru_cache(maxsize=1)
def _load_snapshot() -> CatalogSnapshot | None:
    """Load the catalog snapshot from disk if available.

    Returns:
        CatalogSnapshot | None: Materialised snapshot when the catalog is
        present and valid; otherwise ``None``.

    """
    catalog_root, schema_root = _catalog_paths()
    if not catalog_root.exists():
        return None
    try:
        loader = ToolCatalogLoader(catalog_root=catalog_root, schema_root=schema_root)
    except FileNotFoundError:
        return None
    try:
        return loader.load_snapshot()
    except (CatalogIntegrityError, ValueError, OSError) as exc:
        LOGGER.warning("catalog snapshot load failed: %s", exc)
        return None


def _snapshot_or_error() -> CatalogSnapshot:
    """Return the cached snapshot or raise if the catalog is unavailable.

    Returns:
        CatalogSnapshot: Materialised catalog snapshot.

    Raises:
        RuntimeError: If the catalog metadata cannot be loaded.

    """
    snapshot = _load_snapshot()
    if snapshot is None:
        raise RuntimeError("Catalog metadata is unavailable; ensure tooling/catalog exists.")
    return snapshot


def _catalog_paths() -> tuple[Path, Path]:
    """Return catalog and schema roots relative to the project layout.

    Returns:
        tuple[Path, Path]: Paths to the catalog and schema directories.

    """
    project_root = get_pyqa_root()
    catalog_root = project_root / "tooling" / "catalog"
    schema_root = project_root / "tooling" / "schema"
    return catalog_root, schema_root


def _dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    """Return *values* with duplicates removed while preserving order.

    Args:
        values: Iterable of string values that may include duplicates.

    Returns:
        list[str]: Values with duplicates removed while retaining the first
        occurrence order.

    """
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


__all__ = (
    "CatalogOption",
    "catalog_duplicate_hint_codes",
    "catalog_duplicate_preference",
    "catalog_duplicate_tools",
    "catalog_general_suppressions",
    "catalog_test_suppressions",
    "catalog_tool_options",
    "clear_catalog_metadata_cache",
)
