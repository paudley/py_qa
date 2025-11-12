# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Interfaces and constants describing internal lint tooling."""

from __future__ import annotations

from typing import Final

INTERNAL_LINTER_TOOL_NAMES: Final[tuple[str, ...]] = (
    "docstrings",
    "pyqa-interfaces",
    "pyqa-di",
    "pyqa-module-docs",
    "pyqa-python-hygiene",
    "suppressions",
    "types",
    "missing",
    "closures",
    "conditional-imports",
    "signatures",
    "cache",
    "pyqa-value-types",
    "generic-value-types",
    "license-header",
    "copyright",
    "python-hygiene",
    "file-size",
    "pyqa-schema-sync",
)


__all__ = ["INTERNAL_LINTER_TOOL_NAMES"]
