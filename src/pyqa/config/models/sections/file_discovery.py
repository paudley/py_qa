# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose configuration describing project file discovery behaviour."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FileDiscoveryConfig(BaseModel):
    """Manage discovery inputs that control which files pyqa inspects."""

    model_config = ConfigDict(validate_assignment=True)

    roots: list[Path] = Field(default_factory=lambda: [Path()])
    excludes: list[Path] = Field(default_factory=list)
    paths_from_stdin: bool = False
    changed_only: bool = False
    diff_ref: str = "HEAD"
    include_untracked: bool = True
    base_branch: str | None = None
    pre_commit: bool = False
    respect_gitignore: bool = False
    explicit_files: list[Path] = Field(default_factory=list)
    limit_to: list[Path] = Field(default_factory=list)


__all__ = ["FileDiscoveryConfig"]
