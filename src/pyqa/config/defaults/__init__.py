# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Default configuration factories."""

from __future__ import annotations

from typing import Any

from ..models import Config


def default_config() -> Config:
    """Return a fresh configuration instance populated with project defaults."""

    return Config()


def default_config_payload() -> dict[str, Any]:
    """Return the dictionary representation of :func:`default_config`."""

    return default_config().to_dict()


__all__ = ["default_config", "default_config_payload"]
