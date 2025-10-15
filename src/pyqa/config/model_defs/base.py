# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Provide base utilities for configuration models."""

from __future__ import annotations


class ConfigError(Exception):
    """Raise this error when configuration input is invalid."""


__all__ = ["ConfigError"]
