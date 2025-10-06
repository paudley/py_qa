# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Reporting output helpers for diagnostics and highlighting."""

from .diagnostics import (
    MISSING_CODE_PLACEHOLDER,
    clean_message,
    dump_diagnostics,
    format_diagnostic_line,
    join_output,
    raw_location,
    severity_color,
)
from .highlighting import (
    ANNOTATION_ENGINE,
    ANNOTATION_SPAN_STYLE,
    CODE_TINT,
    LITERAL_TINT,
    LOCATION_SEPARATOR,
    apply_highlighting_text,
    collect_highlight_spans,
    format_code_value,
    highlight_for_output,
    location_function_spans,
    strip_literal_quotes,
)
from .modes import render_pretty_mode, render_quiet_mode, render_raw_mode

__all__ = (
    "MISSING_CODE_PLACEHOLDER",
    "clean_message",
    "dump_diagnostics",
    "format_diagnostic_line",
    "join_output",
    "raw_location",
    "severity_color",
    "ANNOTATION_ENGINE",
    "ANNOTATION_SPAN_STYLE",
    "CODE_TINT",
    "LITERAL_TINT",
    "LOCATION_SEPARATOR",
    "apply_highlighting_text",
    "collect_highlight_spans",
    "format_code_value",
    "highlight_for_output",
    "location_function_spans",
    "strip_literal_quotes",
    "render_pretty_mode",
    "render_quiet_mode",
    "render_raw_mode",
)
