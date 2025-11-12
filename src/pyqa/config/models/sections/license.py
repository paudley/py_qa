# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose licensing policy configuration models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LicenseConfig(BaseModel):
    """Manage repository-wide licensing policy settings."""

    model_config = ConfigDict(validate_assignment=True)

    spdx: str | None = None
    notice: str | None = None
    copyright: str | None = None
    year: str | None = None
    require_spdx: bool = True
    require_notice: bool = True
    allow_alternate_spdx: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)


__all__ = ["LicenseConfig"]
