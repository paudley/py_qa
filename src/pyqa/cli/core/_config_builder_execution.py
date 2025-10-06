# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for building execution configuration overrides."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final, TypedDict

from ...config import ExecutionConfig
from ._config_builder_constants import LintOptionKey
from ._config_builder_shared import resolve_path, select_flag, select_value
from .options import LintOptions


class ExecutionOverrides(TypedDict):
    """Mapping of execution override fields."""

    only: tuple[str, ...]
    languages: tuple[str, ...]
    fix_only: bool
    check_only: bool
    bail: bool
    jobs: int | None
    cache_enabled: bool
    cache_dir: Path
    use_local_linters: bool
    line_length: int
    sql_dialect: str
    python_version: str | None


def apply_execution_overrides(
    current: ExecutionConfig,
    overrides: ExecutionOverrides,
) -> ExecutionConfig:
    """Return ``current`` updated with the supplied override mapping."""

    return current.model_copy(
        update={
            "only": list(overrides["only"]),
            "languages": list(overrides["languages"]),
            "fix_only": overrides["fix_only"],
            "check_only": overrides["check_only"],
            "bail": overrides["bail"],
            "jobs": overrides["jobs"],
            "cache_enabled": overrides["cache_enabled"],
            "cache_dir": overrides["cache_dir"],
            "use_local_linters": overrides["use_local_linters"],
            "line_length": overrides["line_length"],
            "sql_dialect": overrides["sql_dialect"],
            "python_version": overrides["python_version"],
        },
        deep=True,
    )


def collect_execution_overrides(
    current: ExecutionConfig,
    options: LintOptions,
    project_root: Path,
    has_option: Callable[[LintOptionKey], bool],
) -> ExecutionOverrides:
    """Return the execution overrides derived from CLI inputs.

    Args:
        current: Existing execution configuration prior to applying overrides.
        options: Composed CLI options bundle derived from user arguments.
        project_root: Resolved project root used for relative path handling.
        has_option: Predicate indicating whether a CLI flag was provided.

    Returns:
        ExecutionOverrides: Mapping of normalized execution overrides spanning
        runtime, tool selection, and formatting controls.
    """

    provided = options.provided
    runtime_options = options.execution_options.runtime
    selection = options.selection_options
    formatting = options.execution_options.formatting

    bail_value = select_flag(runtime_options.bail, current.bail, LintOptionKey.BAIL, provided)
    jobs_value = select_value(runtime_options.jobs, current.jobs, LintOptionKey.JOBS, provided)
    if bail_value:
        jobs_value = SERIAL_JOB_COUNT

    cache_dir = (
        resolve_path(project_root, runtime_options.cache_dir).resolve()
        if has_option(LintOptionKey.CACHE_DIR)
        else current.cache_dir
    )

    overrides: ExecutionOverrides = {
        "only": tuple(selection.only) if has_option(LintOptionKey.ONLY) else tuple(current.only),
        "languages": tuple(selection.language) if has_option(LintOptionKey.LANGUAGE) else tuple(current.languages),
        "fix_only": select_flag(
            selection.fix_only,
            current.fix_only,
            LintOptionKey.FIX_ONLY,
            provided,
        ),
        "check_only": select_flag(
            selection.check_only,
            current.check_only,
            LintOptionKey.CHECK_ONLY,
            provided,
        ),
        "bail": bail_value,
        "jobs": jobs_value,
        "cache_enabled": select_flag(
            not runtime_options.no_cache,
            current.cache_enabled,
            LintOptionKey.NO_CACHE,
            provided,
        ),
        "cache_dir": cache_dir,
        "use_local_linters": select_flag(
            runtime_options.use_local_linters,
            current.use_local_linters,
            LintOptionKey.USE_LOCAL_LINTERS,
            provided,
        ),
        "line_length": select_value(
            formatting.line_length,
            current.line_length,
            LintOptionKey.LINE_LENGTH,
            provided,
        ),
        "sql_dialect": select_value(
            formatting.sql_dialect,
            current.sql_dialect,
            LintOptionKey.SQL_DIALECT,
            provided,
        ),
        "python_version": select_value(
            formatting.python_version,
            current.python_version,
            LintOptionKey.PYTHON_VERSION,
            provided,
        ),
    }
    return overrides


SERIAL_JOB_COUNT: Final[int] = 1


__all__ = [
    "ExecutionOverrides",
    "apply_execution_overrides",
    "collect_execution_overrides",
    "SERIAL_JOB_COUNT",
]
