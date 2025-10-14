# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Default configuration factories."""

from __future__ import annotations

from ..models import Config
from ..types import ConfigValue


def default_config() -> Config:
    """Return a fresh configuration instance populated with project defaults."""

    return Config()


def default_config_payload() -> dict[str, ConfigValue]:
    """Return the dictionary representation of :func:`default_config`."""

    return default_config().to_dict()


__all__ = ["default_config", "default_config_payload"]
