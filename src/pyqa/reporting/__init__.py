# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Reporting helpers: console renderers and reusable advice builders."""

from .advice import AdviceBuilder, AdviceEntry, generate_advice
from .formatters import render

__all__ = [
    "AdviceBuilder",
    "AdviceEntry",
    "generate_advice",
    "render",
]
