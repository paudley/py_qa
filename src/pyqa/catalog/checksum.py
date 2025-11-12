# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Checksum utilities for catalog contents."""

from __future__ import annotations

from tooling_spec.catalog.checksum import compute_catalog_checksum as _compute_catalog_checksum

compute_catalog_checksum = _compute_catalog_checksum

__all__ = ("compute_catalog_checksum",)
