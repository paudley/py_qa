# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Compatibility shim exposing catalog loader primitives."""

from __future__ import annotations

from typing import Final

from .catalog import models as catalog_models
from .catalog.errors import CatalogIntegrityError, CatalogValidationError
from .catalog.loader import ToolCatalogLoader
from .catalog.models import CATALOG_MODEL_EXPORTS
from .catalog.types import JSONPrimitive, JSONValue


def _register_exports() -> None:
    """Populate ``pyqa.tooling.loader`` with catalog model exports."""

    module_globals = globals()
    for export_name in CATALOG_MODEL_EXPORTS:
        module_globals[export_name] = getattr(catalog_models, export_name)
    module_globals.update(
        CatalogIntegrityError=CatalogIntegrityError,
        CatalogValidationError=CatalogValidationError,
        JSONPrimitive=JSONPrimitive,
        JSONValue=JSONValue,
        ToolCatalogLoader=ToolCatalogLoader,
    )


_register_exports()

__all__: Final[list[str]] = [  # pyright: ignore[reportUnsupportedDunderAll]
    *CATALOG_MODEL_EXPORTS,
    "CatalogIntegrityError",
    "CatalogValidationError",
    "JSONPrimitive",
    "JSONValue",
    "ToolCatalogLoader",
]
