# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Custom exceptions raised by tooling catalog operations."""

from __future__ import annotations

from importlib import import_module
from typing import cast


class _FallbackCatalogIntegrityError(RuntimeError):
    """Fallback integrity error used when the pyqa runtime is unavailable."""

    def __init__(self, message: str | None = None) -> None:
        """Create the integrity error with an optional ``message``."""

        super().__init__(message or "catalog integrity violation")


def _load_catalog_integrity_error() -> type[RuntimeError]:
    """Return the integrity error class shared with the pyqa runtime."""

    try:  # pragma: no cover - dependency optional for tooling_spec
        module = import_module("pyqa.catalog.errors")
    except ImportError:
        fallback = _FallbackCatalogIntegrityError
        fallback.__name__ = "CatalogIntegrityError"
        fallback.__qualname__ = "CatalogIntegrityError"
        return fallback

    error_cls = getattr(module, "CatalogIntegrityError")
    error_cls.__doc__ = "Raised when catalog metadata violates semantic invariants."
    return cast(type[RuntimeError], error_cls)


CatalogIntegrityError = _load_catalog_integrity_error()


class CatalogValidationError(RuntimeError):
    """Raised when a catalog document fails structural schema validation."""


__all__ = ("CatalogIntegrityError", "CatalogValidationError")
