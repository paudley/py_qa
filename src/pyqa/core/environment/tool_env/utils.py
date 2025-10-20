# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utility helpers shared across tool environment modules."""

from __future__ import annotations

import re
from typing import Final

from pyqa.tools.base import Tool

SCOPED_PACKAGE_PREFIX: Final[str] = "@"
PACKAGE_SEPARATOR: Final[str] = "@"
SCOPED_SPLIT_THRESHOLD: Final[int] = 2


def _slugify(value: str) -> str:
    """Return the filesystem-friendly slug for ``value``.

    Args:
        value: Input string requiring sanitisation.

    Returns:
        str: Slug containing only safe filesystem characters.
    """

    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value)


def _extract_version(text: str | None) -> str | None:
    """Return the semantic version embedded in ``text`` when present.

    Args:
        text: Candidate string containing a version specification.

    Returns:
        str | None: Extracted version string, or ``None`` when missing.
    """

    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)+)", text)
    return match.group(1) if match else None


def _split_package_spec(spec: str) -> tuple[str, str | None]:
    """Split the package specifier into name and version components.

    Args:
        spec: Raw package specification, potentially including a version suffix.

    Returns:
        tuple[str, str | None]: Package name and optional version component.
    """
    if spec.startswith("git+") or spec.startswith("file:") or spec.startswith("http"):
        return spec, None
    if spec.startswith(SCOPED_PACKAGE_PREFIX):
        if spec.count(PACKAGE_SEPARATOR) >= SCOPED_SPLIT_THRESHOLD:
            name, version = spec.rsplit(PACKAGE_SEPARATOR, 1)
            return name, version
        return spec, None
    if PACKAGE_SEPARATOR in spec:
        name, version = spec.rsplit(PACKAGE_SEPARATOR, 1)
        return name, version
    return spec, None


def desired_version(tool: Tool) -> str | None:
    """Determine the target version expected for the tool.

    Args:
        tool: Tool metadata describing package and version preferences.

    Returns:
        str | None: Version string when derivable from metadata, otherwise ``None``.
    """
    if tool.package:
        _, specified = _split_package_spec(tool.package)
        extracted = _extract_version(specified)
        if extracted:
            return extracted
    if tool.min_version:
        return tool.min_version
    return None


__all__ = [
    "_extract_version",
    "_slugify",
    "_split_package_spec",
    "desired_version",
]
