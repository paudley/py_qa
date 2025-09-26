# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utility helpers shared across tool environment modules."""

from __future__ import annotations

import re

from ..tools.base import Tool


def _slugify(value: str) -> str:
    """Return a filesystem-friendly slug for *value*."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value)


def _extract_version(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)+)", text)
    return match.group(1) if match else None


def _split_package_spec(spec: str) -> tuple[str, str | None]:
    """Split a package specifier into name and version components."""
    if spec.startswith("git+") or spec.startswith("file:") or spec.startswith("http"):
        return spec, None
    if spec.startswith("@"):
        if spec.count("@") >= 2:
            name, version = spec.rsplit("@", 1)
            return name, version
        return spec, None
    if "@" in spec:
        name, version = spec.rsplit("@", 1)
        return name, version
    return spec, None


def desired_version(tool: Tool) -> str | None:
    """Determine the target version expected for *tool*."""
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
