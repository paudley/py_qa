# SPDX-License-Identifier: MIT
"""Shared helpers for loading configuration with CLI-friendly errors."""

from __future__ import annotations

from pathlib import Path

from ..config_loader import ConfigError, ConfigLoader, ConfigLoadResult
from .shared import CLIError, CLILogger


def load_config_result(
    root: Path,
    *,
    logger: CLILogger,
    strict: bool = False,
    failure_context: str = "Configuration",
) -> ConfigLoadResult:
    """Load configuration for ``root`` and raise ``CLIError`` on failure.

    Args:
        root: Project root directory to inspect for configuration files.
        logger: CLI logger used to report failures to the caller.
        strict: When ``True``, propagate configuration warnings as errors.
        failure_context: Human-readable label describing the configuration
            section being loaded. Defaults to ``"Configuration"``.

    Returns:
        ConfigLoadResult: Loaded configuration and provenance metadata.

    Raises:
        CLIError: If loading fails because the configuration is invalid.
    """

    loader = ConfigLoader.for_root(root)
    try:
        return loader.load_with_trace(strict=strict)
    except ConfigError as exc:  # pragma: no cover - CLI failure path
        logger.fail(f"{failure_context} invalid: {exc}")
        raise CLIError(str(exc)) from exc


__all__ = ["load_config_result"]
