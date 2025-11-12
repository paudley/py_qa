# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Fragment resolution helpers for catalog documents."""

from __future__ import annotations

from tooling_spec.catalog.resolver import (
    EXTENDS_KEY,
    merge_json_objects,
    resolve_tool_mapping,
    to_plain_json,
)

__all__ = (
    "EXTENDS_KEY",
    "merge_json_objects",
    "resolve_tool_mapping",
    "to_plain_json",
)
