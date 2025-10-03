# SPDX-License-Identifier: MIT
"""pyqa CLI package exports."""

from __future__ import annotations

from .app import app
from .config_builder import build_config
from .options import LintOptions

__all__ = ["LintOptions", "app", "build_config", "_build_config"]


def _build_config(**kwargs):
    """Construct ``LintOptions`` from keyword arguments and build a config."""

    return build_config(LintOptions(**kwargs))
