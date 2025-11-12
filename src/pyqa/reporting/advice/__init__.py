# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""SOLID advice builders and panels."""

from pyqa.interfaces.reporting import DiagnosticRecord

from .builder import AdviceBuilder, AdviceCategory, AdviceEntry, generate_advice
from .panels import render_advice_panel
from .refactor import render_refactor_navigator

__all__ = (
    "AdviceBuilder",
    "AdviceCategory",
    "AdviceEntry",
    "DiagnosticRecord",
    "generate_advice",
    "render_advice_panel",
    "render_refactor_navigator",
)
