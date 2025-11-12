# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Default configuration factories."""

from __future__ import annotations

from ..models import Config
from ..types import ConfigValue


def default_config() -> Config:
    """Create a configuration instance populated with project defaults.

    Returns:
        Config: Newly constructed configuration model containing project defaults.
    """

    return Config()


def default_config_payload() -> dict[str, ConfigValue]:
    """Produce a serialisable payload representing :func:`default_config`.

    Returns:
        dict[str, ConfigValue]: Dictionary representation of the default configuration.
    """

    return default_config().to_dict()


__all__ = ["default_config", "default_config_payload"]
