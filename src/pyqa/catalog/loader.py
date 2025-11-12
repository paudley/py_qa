# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""High-level loader that materialises catalog definitions."""

from __future__ import annotations

from tooling_spec.catalog import loader as _spec_loader
from tooling_spec.catalog.loader import (
    CatalogIntegrityError,
    CatalogValidationError,
    JSONValue,
    ToolCatalogLoader,
)

from .plugins import load_plugin_contributions

setattr(_spec_loader, "load_plugin_contributions", load_plugin_contributions)

__all__ = (
    "CatalogIntegrityError",
    "CatalogValidationError",
    "JSONValue",
    "ToolCatalogLoader",
)
