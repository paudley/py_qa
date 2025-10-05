# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Public export surface for pyqa's catalog tooling components."""

from __future__ import annotations

from .errors import CatalogIntegrityError, CatalogValidationError
from .loader import ToolCatalogLoader
from .metadata import (
    CatalogOption,
    catalog_duplicate_hint_codes,
    catalog_duplicate_tools,
    catalog_general_suppressions,
    catalog_test_suppressions,
    catalog_tool_options,
    clear_catalog_metadata_cache,
)
from .model_catalog import CatalogFragment, CatalogSnapshot
from .model_tool import ToolDefinition

__all__ = [
    "CatalogFragment",
    "CatalogIntegrityError",
    "CatalogOption",
    "CatalogSnapshot",
    "CatalogValidationError",
    "ToolCatalogLoader",
    "ToolDefinition",
    "catalog_duplicate_hint_codes",
    "catalog_duplicate_tools",
    "catalog_general_suppressions",
    "catalog_test_suppressions",
    "catalog_tool_options",
    "clear_catalog_metadata_cache",
]
