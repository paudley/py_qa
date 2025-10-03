# SPDX-License-Identifier: MIT
"""Helper services for the sparkly-clean CLI."""

from __future__ import annotations

from pathlib import Path

from ..clean import CleanConfig, CleanResult
from ..config_loader import ConfigError, ConfigLoader
from ..constants import PY_QA_DIR_NAME
from ..filesystem.paths import display_relative_path
from .shared import CLIError, CLILogger


def load_clean_config(root: Path, *, logger: CLILogger) -> CleanConfig:
    """Load the project clean configuration or raise ``CLIError`` on failure.

    Args:
        root: Resolved project root where configuration files should be read.
        logger: Logger used for emitting user-facing messages when needed.

    Returns:
        A ``CleanConfig`` instance retrieved from the configuration loader.

    Raises:
        CLIError: Raised when the configuration cannot be loaded.
    """

    loader = ConfigLoader.for_root(root)
    try:
        load_result = loader.load_with_trace()
    except ConfigError as exc:  # pragma: no cover - CLI path
        logger.fail(f"Configuration invalid: {exc}")
        raise CLIError(str(exc)) from exc
    return load_result.config.clean


def emit_py_qa_warning(result: CleanResult, root: Path, *, logger: CLILogger) -> None:
    """Emit a warning for py-qa protected paths.

    Args:
        result: The clean execution result produced by ``sparkly_clean``.
        root: The project root used to generate human-readable paths.
        logger: Logger used to emit the warning.

    Returns:
        None. The function performs logging side effects only.
    """

    if not result.ignored_py_qa:
        return
    ignored = [display_relative_path(path, root) for path in result.ignored_py_qa]
    unique = ", ".join(dict.fromkeys(ignored))
    logger.warn(
        f"Ignoring path(s) {unique}: '{PY_QA_DIR_NAME}' directories are skipped "
        "unless sparkly-clean runs inside the py_qa workspace."
    )


def emit_dry_run_summary(result: CleanResult, *, logger: CLILogger) -> None:
    """Log the paths that would be removed during a dry run.

    Args:
        result: The clean execution result with populated ``skipped`` entries.
        logger: Logger used to emit messages.

    Returns:
        None. The function performs logging side effects only.
    """

    for path in sorted(result.skipped):
        logger.warn(f"DRY RUN: would remove {path}")


__all__ = [
    "load_clean_config",
    "emit_py_qa_warning",
    "emit_dry_run_summary",
]
