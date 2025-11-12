# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime dependency factories for the lint CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ....core.shared import Depends
from ..params import LintExecutionRuntimeParams, RuntimeCacheParams, RuntimeConcurrencyParams
from .constants import CACHE_DIR_HELP, JOBS_HELP, STRICT_CONFIG_HELP, USE_LOCAL_LINTERS_HELP


def _runtime_concurrency_dependency(
    jobs: Annotated[int | None, typer.Option(None, "--jobs", "-j", min=1, help=JOBS_HELP)],
    bail: Annotated[bool, typer.Option(False, "--bail", help="Exit on first tool failure.")],
    use_local_linters: Annotated[
        bool,
        typer.Option(False, "--use-local-linters", help=USE_LOCAL_LINTERS_HELP),
    ],
) -> RuntimeConcurrencyParams:
    """Return concurrency parameters controlling parallel execution.

    Args:
        jobs: Optional explicit job count provided by the user.
        bail: Flag indicating whether execution should abort on first failure.
        use_local_linters: Whether vendored linters should be preferred.

    Returns:
        RuntimeConcurrencyParams: Structured concurrency parameters.
    """

    return RuntimeConcurrencyParams(jobs=jobs, bail=bail, use_local_linters=use_local_linters)


def _runtime_cache_dependency(
    no_cache: Annotated[bool, typer.Option(False, help="Disable on-disk result caching.")],
    cache_dir: Annotated[Path, typer.Option(Path(".lint-cache"), "--cache-dir", help=CACHE_DIR_HELP)],
) -> RuntimeCacheParams:
    """Return runtime cache parameters derived from CLI options.

    Args:
        no_cache: Flag indicating whether caching should be disabled.
        cache_dir: Directory used to persist cached results.

    Returns:
        RuntimeCacheParams: Structured cache settings for lint execution.
    """

    return RuntimeCacheParams(no_cache=no_cache, cache_dir=cache_dir)


def _execution_runtime_dependency(
    concurrency: Annotated[RuntimeConcurrencyParams, Depends(_runtime_concurrency_dependency)],
    cache: Annotated[RuntimeCacheParams, Depends(_runtime_cache_dependency)],
    strict_config: Annotated[bool, typer.Option(False, "--strict-config", help=STRICT_CONFIG_HELP)],
) -> LintExecutionRuntimeParams:
    """Combine concurrency and cache settings into execution parameters.

    Args:
        concurrency: Structured concurrency parameters.
        cache: Cache configuration parameters.
        strict_config: Whether configuration warnings should become errors.

    Returns:
        LintExecutionRuntimeParams: Execution runtime configuration consumed by the lint command.
    """

    return LintExecutionRuntimeParams(
        jobs=concurrency.jobs,
        bail=concurrency.bail,
        no_cache=cache.no_cache,
        cache_dir=cache.cache_dir,
        use_local_linters=concurrency.use_local_linters,
        strict_config=strict_config,
    )


__all__ = [
    "_execution_runtime_dependency",
    "_runtime_cache_dependency",
    "_runtime_concurrency_dependency",
]
