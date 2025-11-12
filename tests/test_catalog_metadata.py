# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for catalog-derived metadata helpers."""

from __future__ import annotations

import pytest

from pyqa.catalog.metadata import (
    CatalogOption,
    catalog_duplicate_hint_codes,
    catalog_duplicate_preference,
    catalog_duplicate_tools,
    catalog_general_suppressions,
    catalog_test_suppressions,
    catalog_tool_options,
    clear_catalog_metadata_cache,
)
from pyqa.catalog.loader import ToolCatalogLoader


def test_catalog_duplicate_metadata() -> None:
    """Catalog duplicate metadata should expose tools, hints, and preference."""
    clear_catalog_metadata_cache()
    duplicates = catalog_duplicate_tools()
    assert duplicates.get("ruff") == ("pylint",)
    assert duplicates.get("pyright") == ("mypy",)

    hints = catalog_duplicate_hint_codes()
    assert "B014" in hints.get("ruff", ())
    assert hints.get("pylint") == ("R0801",)

    preference = catalog_duplicate_preference()
    assert preference and preference[0] == "ruff"
    assert "pyright" in preference


def test_catalog_suppressions_merges_fragments() -> None:
    """General suppressions inherited from fragments should surface per tool."""
    clear_catalog_metadata_cache()
    general = catalog_general_suppressions()
    assert any(".github" in pattern for pattern in general.get("ruff", ()))


def test_catalog_test_suppressions_language_map() -> None:
    """Test suppressions should expose per-language tool mappings."""
    clear_catalog_metadata_cache()
    catalog_map = catalog_test_suppressions()
    python_tools = catalog_map.get("python")
    assert python_tools is not None
    assert "ruff" in python_tools


def test_catalog_tool_options_with_choices() -> None:
    """Catalog tool options should include typed metadata and enumerations."""
    clear_catalog_metadata_cache()
    options = catalog_tool_options()
    ruff_options = options.get("ruff")
    assert ruff_options is not None
    assert any(option.name == "line-length" and option.option_type == "integer" for option in ruff_options)
    target_version = next(
        (option for option in ruff_options if option.name == "target-version"),
        None,
    )
    assert isinstance(target_version, CatalogOption)
    assert "py311" in target_version.choices


def test_catalog_metadata_cache_hit_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Snapshot loads should be cached until the catalog metadata cache clears."""
    clear_catalog_metadata_cache()
    load_count = 0
    original_loader = ToolCatalogLoader.load_snapshot

    def _tracking_loader(self: ToolCatalogLoader):
        nonlocal load_count
        load_count += 1
        return original_loader(self)

    monkeypatch.setattr(ToolCatalogLoader, "load_snapshot", _tracking_loader)

    catalog_tool_options()
    catalog_tool_options()
    assert load_count == 1

    clear_catalog_metadata_cache()
    catalog_tool_options()
    assert load_count == 2
