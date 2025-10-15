# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Aggregate configuration section models and related defaults."""

from __future__ import annotations

from .clean import DEFAULT_CLEAN_PATTERNS, DEFAULT_CLEAN_TREES, CleanConfig
from .complexity import ComplexityConfig
from .dedupe import DedupeConfig
from .execution import ExecutionConfig, default_parallel_jobs
from .file_discovery import FileDiscoveryConfig
from .license import LicenseConfig
from .output import OutputConfig
from .quality import (
    DEFAULT_PROTECTED_BRANCHES,
    DEFAULT_QUALITY_CHECKS,
    DEFAULT_SCHEMA_TARGETS,
    QualityConfigSection,
)
from .severity import SeverityConfig
from .strictness import StrictnessConfig
from .update import DEFAULT_UPDATE_SKIP_PATTERNS, UpdateConfig

__all__ = [
    "CleanConfig",
    "ComplexityConfig",
    "DEFAULT_CLEAN_PATTERNS",
    "DEFAULT_CLEAN_TREES",
    "DEFAULT_PROTECTED_BRANCHES",
    "DEFAULT_QUALITY_CHECKS",
    "DEFAULT_SCHEMA_TARGETS",
    "DEFAULT_UPDATE_SKIP_PATTERNS",
    "DedupeConfig",
    "ExecutionConfig",
    "FileDiscoveryConfig",
    "LicenseConfig",
    "OutputConfig",
    "QualityConfigSection",
    "SeverityConfig",
    "StrictnessConfig",
    "UpdateConfig",
    "default_parallel_jobs",
]
