# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""pyqa CLI package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config_builder import build_config
from .options import LintOptions

__all__ = ["LintOptions", "app", "build_config", "_build_config"]


if TYPE_CHECKING:  # pragma: no cover - import cycle guard during type checking
    from .app import app as app


def __getattr__(name: str):
    """Return lazily-imported CLI attributes.

    This package traditionally exposed the Typer application instance as
    ``pyqa.cli.app``. Importing the Typer graph when the package is imported
    eagerly causes ``python -m`` entry points to warn because ``pyqa.cli.app``
    appears in ``sys.modules`` before the ``runpy`` bootstrap executes. To keep
    the public API stable while avoiding the warning, we resolve ``app`` only
    when it is accessed via attribute lookup.

    Args:
        name: Attribute requested by the caller.

    Returns:
        Any: The requested attribute when supported (currently only ``app``).

    Raises:
        AttributeError: If ``name`` is not a lazily-supported attribute.
    """

    if name == "app":
        from .app import app as typer_app

        return typer_app
    raise AttributeError(f"module 'pyqa.cli' has no attribute {name!r}")


def _build_config(**kwargs):
    """Construct ``LintOptions`` from keyword arguments and build a config.

    Historically ``pyqa.cli._build_config`` accepted keyword arguments matching
    the ``LintOptions`` dataclass and returned the synthesized configuration. We
    continue to honour that contract for external integrations, delegating to
    :func:`build_config` after instantiating :class:`LintOptions`.

    Args:
        **kwargs: Keyword arguments compatible with :class:`LintOptions`.

    Returns:
        Config: Configuration generated from the provided keyword arguments.
    """

    return build_config(LintOptions(**kwargs))
