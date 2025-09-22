"""pyqa CLI package."""

from __future__ import annotations

from .app import app
from .config_builder import build_config
from .options import LintOptions

__all__ = ["app", "build_config", "LintOptions"]


def _build_config(**kwargs):
    return build_config(LintOptions(**kwargs))


# Backwards compatibility
__all__.append("_build_config")
