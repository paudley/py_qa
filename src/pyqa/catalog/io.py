# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""I/O helpers for reading catalog JSON documents and schemas."""

from __future__ import annotations

from tooling_spec.catalog.io import load_document as _load_document
from tooling_spec.catalog.io import load_schema as _load_schema

load_document = _load_document
load_schema = _load_schema

__all__ = ("load_document", "load_schema")
