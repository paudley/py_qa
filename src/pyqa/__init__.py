# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Core package metadata and convenience hooks."""

from __future__ import annotations

from importlib import metadata

__all__ = ["__version__"]

try:
    __version__ = metadata.version("pyqa-lint")
except metadata.PackageNotFoundError:  # pragma: no cover - local development fallback
    __version__ = "0.0.0"
