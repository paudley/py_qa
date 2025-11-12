# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Reporting helpers: SOLID advice, presenters, and output adapters."""

from .advice.builder import AdviceBuilder, AdviceEntry, generate_advice
from .advice.panels import render_advice_panel
from .advice.refactor import render_refactor_navigator
from .output.diagnostics import (
    MISSING_CODE_PLACEHOLDER,
    clean_message,
    dump_diagnostics,
    format_diagnostic_line,
    join_output,
    raw_location,
    severity_color,
)
from .output.highlighting import (
    ANNOTATION_ENGINE,
    ANNOTATION_SPAN_STYLE,
    CODE_TINT,
    LOCATION_SEPARATOR,
    apply_highlighting_text,
    collect_highlight_spans,
    format_code_value,
    highlight_for_output,
    location_function_spans,
    strip_literal_quotes,
)
from .output.modes import render_pretty_mode, render_quiet_mode, render_raw_mode
from .presenters.emitters import write_json_report, write_pr_summary, write_sarif_report
from .presenters.formatters import render
from .presenters.stats import emit_stats_panel

__all__ = [
    "AdviceBuilder",
    "AdviceEntry",
    "generate_advice",
    "render_advice_panel",
    "render_refactor_navigator",
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
    "write_json_report",
    "write_pr_summary",
    "write_sarif_report",
    "render",
    "emit_stats_panel",
]
