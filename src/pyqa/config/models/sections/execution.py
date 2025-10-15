# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose execution and tool selection configuration models."""

from __future__ import annotations

import math
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def default_parallel_jobs() -> int:
    """Calculate a conservative default for concurrent lint workers.

    Returns:
        int: Projected job count representing roughly 75% of available CPUs
        while ensuring at least one worker.

    """

    cores = os.cpu_count() or 1
    proposed = max(1, math.floor(cores * 0.75))
    return proposed


class ExecutionConfig(BaseModel):
    """Manage execution controls dictating which tools run and how they behave."""

    model_config = ConfigDict(validate_assignment=True)

    only: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    enable: list[str] = Field(default_factory=list)
    pyqa_rules: bool = False
    strict: bool = False
    jobs: int = Field(default_factory=default_parallel_jobs)
    fix_only: bool = False
    check_only: bool = False
    force_all: bool = False
    respect_config: bool = False
    cache_enabled: bool = True
    cache_dir: Path = Field(default_factory=lambda: Path(".lint-cache"))
    bail: bool = False
    use_local_linters: bool = False
    line_length: int = 120
    sql_dialect: str = "postgresql"
    python_version: str | None = None


__all__ = ["ExecutionConfig", "default_parallel_jobs"]
