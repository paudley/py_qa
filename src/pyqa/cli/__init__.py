# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""pyqa CLI package exports."""

from __future__ import annotations

from typing import Final

from ..config import Config
from .app import app
from .config_builder import build_config
from .options import LintOptions

__all__: Final[list[str]] = ["LintOptions", "app", "build_config", "_build_config"]


def _build_config(*, options: LintOptions) -> Config:
    """Return a configuration derived from ``options``.

    Args:
        options: Normalised lint options that describe the desired execution
            behaviour.

    Returns:
        Config: Configuration object produced by :func:`build_config`.
    """

    return build_config(options)
