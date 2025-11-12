# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Custom exceptions raised by tooling catalog operations."""

from __future__ import annotations


class CatalogValidationError(RuntimeError):
    """Raised when a catalog document fails schema validation."""


class CatalogIntegrityError(RuntimeError):
    """Raised when a catalog document passes schema validation but fails semantic checks."""


__all__ = ["CatalogIntegrityError", "CatalogValidationError"]
