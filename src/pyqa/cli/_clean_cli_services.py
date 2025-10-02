# SPDX-License-Identifier: MIT
"""Helper services for the sparkly-clean CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from ..clean import CleanConfig, CleanResult
from ..config_loader import ConfigError, ConfigLoader
from ..filesystem.paths import display_relative_path
from ..logging import fail, warn
from ..constants import PY_QA_DIR_NAME


def load_clean_config(root: Path, *, emoji: bool) -> CleanConfig:
    """Load the project clean configuration or exit on failure.

    Args:
        root: Resolved project root where configuration files should be read.
        emoji: Whether the CLI should render emoji when reporting failures.

    Returns:
        A ``CleanConfig`` instance retrieved from the configuration loader.

    Raises:
        typer.Exit: Raised with a non-zero exit code if configuration loading
            fails. The ``fail`` logger call informs the user before exiting.
    """

    loader = ConfigLoader.for_root(root)
    try:
        load_result = loader.load_with_trace()
    except ConfigError as exc:  # pragma: no cover - CLI path
        fail(f"Configuration invalid: {exc}", use_emoji=emoji)
        raise typer.Exit(code=1) from exc
    return load_result.config.clean


def emit_py_qa_warning(result: CleanResult, root: Path, *, emoji: bool) -> None:
    """Emit a warning for py-qa protected paths.

    Args:
        result: The clean execution result produced by ``sparkly_clean``.
        root: The project root used to generate human-readable paths.
        emoji: Indicates whether logging helpers may include emoji.

    Returns:
        None. The function performs logging side effects only.
    """

    if not result.ignored_py_qa:
        return
    ignored = [display_relative_path(path, root) for path in result.ignored_py_qa]
    unique = ", ".join(dict.fromkeys(ignored))
    warn(
        (
            f"Ignoring path(s) {unique}: '{PY_QA_DIR_NAME}' directories are skipped "
            "unless sparkly-clean runs inside the py_qa workspace."
        ),
        use_emoji=emoji,
    )


def emit_dry_run_summary(result: CleanResult, *, emoji: bool) -> None:
    """Log the paths that would be removed during a dry run.

    Args:
        result: The clean execution result with populated ``skipped`` entries.
        emoji: Indicates whether logging helpers may include emoji.

    Returns:
        None. The function performs logging side effects only.
    """

    for path in sorted(result.skipped):
        warn(f"DRY RUN: would remove {path}", use_emoji=emoji)


__all__ = [
    "load_clean_config",
    "emit_py_qa_warning",
    "emit_dry_run_summary",
]
