# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helper services for the sparkly-clean CLI."""

from __future__ import annotations

from pathlib import Path

from pyqa.core.config.constants import PYQA_LINT_DIR_NAME

from ....clean import CleanResult
from ....config import CleanConfig
from ....filesystem.paths import display_relative_path
from ...core._config_loading import load_config_result
from ...core.shared import CLILogger


def load_clean_config(root: Path, *, logger: CLILogger) -> CleanConfig:
    """Return the resolved sparkly-clean configuration for ``root``.

    Args:
        root: Resolved project root where configuration files should be read.
        logger: Logger used for emitting user-facing messages when failures
            occur during configuration loading.

    Returns:
        CleanConfig: Configuration payload extracted from ``.pyqa_lint`` files.
    """

    return load_config_result(root, logger=logger).config.clean


def emit_pyqa_lint_warning(result: CleanResult, root: Path, *, logger: CLILogger) -> None:
    """Emit a warning for pyqa-lint protected paths.

    Args:
        result: The clean execution result produced by ``sparkly_clean``.
        root: The project root used to generate human-readable paths.
        logger: Logger used to emit the warning.
    """

    if not result.ignored_pyqa_lint:
        return
    ignored = [display_relative_path(path, root) for path in result.ignored_pyqa_lint]
    unique = ", ".join(dict.fromkeys(ignored))
    logger.warn(
        f"Ignoring path(s) {unique}: '{PYQA_LINT_DIR_NAME}' directories are skipped "
        "unless sparkly-clean runs inside the pyqa_lint workspace."
    )


def emit_dry_run_summary(result: CleanResult, *, logger: CLILogger) -> None:
    """Log the paths that would be removed during a dry run.

    Args:
        result: The clean execution result with populated ``skipped`` entries.
        logger: Logger used to emit messages.
    """

    for path in sorted(result.skipped):
        logger.warn(f"DRY RUN: would remove {path}")


__all__ = [
    "load_clean_config",
    "emit_pyqa_lint_warning",
    "emit_dry_run_summary",
]
