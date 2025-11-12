# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Diagnostics package exposing normalisation and deduplication helpers."""

from __future__ import annotations

from .core import IssueTag, build_severity_rules, dedupe_outcomes, normalize_diagnostics
from .filtering import (
    DuplicateCodeDeduper,
    DuplicateCodeEntry,
    collect_duplicate_entries,
    duplicate_context_is_commented,
    duplicate_group_key,
    filter_diagnostics,
    generate_duplicate_variants,
    is_test_path,
    parse_duplicate_line,
    read_source_line,
    resolve_duplicate_target,
    select_duplicate_primary,
    split_duplicate_code_entry,
)
from .json_import import JsonDiagnosticExtractor, JsonDiagnosticsConfigError
from .pipeline import DiagnosticPipeline

__all__ = (
    "IssueTag",
    "build_severity_rules",
    "dedupe_outcomes",
    "normalize_diagnostics",
    "DiagnosticPipeline",
    "JsonDiagnosticExtractor",
    "JsonDiagnosticsConfigError",
    "DuplicateCodeDeduper",
    "DuplicateCodeEntry",
    "collect_duplicate_entries",
    "duplicate_context_is_commented",
    "duplicate_group_key",
    "filter_diagnostics",
    "generate_duplicate_variants",
    "is_test_path",
    "parse_duplicate_line",
    "read_source_line",
    "resolve_duplicate_target",
    "select_duplicate_primary",
    "split_duplicate_code_entry",
)
