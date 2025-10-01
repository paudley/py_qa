# SPDX-License-Identifier: MIT
"""Helpers for rendering diagnostics across output modes."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from ..config import OutputConfig
from ..logging import colorize
from ..models import Diagnostic
from ..severity import Severity
from .highlighting import (
    LOCATION_SEPARATOR,
    format_code_value,
    highlight_for_output,
    location_function_spans,
)

MISSING_CODE_PLACEHOLDER: Final[str] = "-"


def join_output(lines: Sequence[str]) -> str:
    """Join output lines for deterministic console rendering."""

    return "\n".join(lines)


def severity_color(sev: Severity) -> str:
    """Return the rich colour name associated with a severity level."""

    return {
        Severity.ERROR: "red",
        Severity.WARNING: "yellow",
        Severity.NOTICE: "blue",
        Severity.NOTE: "cyan",
    }.get(sev, "yellow")


def raw_location(diagnostic: Diagnostic) -> str:
    """Return the raw location string used for diagnostic dumps."""

    if not diagnostic.file:
        return ""
    location = diagnostic.file
    if diagnostic.line is not None:
        location += f"{LOCATION_SEPARATOR}{int(diagnostic.line)}"
        if diagnostic.column is not None:
            location += f"{LOCATION_SEPARATOR}{int(diagnostic.column)}"
    return location


def clean_message(code: str | None, message: str) -> str:
    """Strip redundant prefixes and whitespace from diagnostic messages."""

    if not message:
        return message

    first_line, newline, remainder = message.partition("\n")
    working = first_line.lstrip()
    normalized_code = (code or "").strip()

    if normalized_code and normalized_code != MISSING_CODE_PLACEHOLDER:
        patterns = [
            f"{normalized_code}: ",
            f"{normalized_code}:",
            f"{normalized_code} - ",
            f"{normalized_code} -",
            f"{normalized_code} ",
            f"[{normalized_code}] ",
            f"[{normalized_code}]",
        ]
        for pattern in patterns:
            if working.startswith(pattern):
                working = working[len(pattern) :]
                break
        else:
            working = working.removeprefix(normalized_code)

    cleaned_first = working.lstrip()
    if newline:
        return cleaned_first + "\n" + remainder
    return cleaned_first


def format_diagnostic_line(
    diagnostic: Diagnostic,
    location: str,
    location_width: int,
    cfg: OutputConfig,
) -> str:
    """Return a formatted diagnostic line for quiet/pretty output."""

    severity_display = colorize(
        diagnostic.severity.value,
        severity_color(diagnostic.severity),
        cfg.color,
    )
    code_value = (diagnostic.code or "").strip()
    code_display = (
        f" [{format_code_value(code_value, cfg.color)}]" if code_value else ""
    )
    padded_location = location.ljust(location_width) if location_width else location
    padding = " " if padded_location else ""
    message = clean_message(code_value, diagnostic.message)
    location_display = highlight_for_output(
        padded_location,
        color=cfg.color,
        extra_spans=location_function_spans(padded_location),
    )
    message_display = highlight_for_output(message, color=cfg.color)
    return f"  {severity_display} {location_display}{padding}{message_display}{code_display}"


def dump_diagnostics(diags: Iterable[Diagnostic], cfg: OutputConfig) -> None:
    """Print formatted diagnostics in pretty or quiet modes."""

    collected = list(diags)
    if not collected:
        return

    locations = [raw_location(diag) for diag in collected]
    location_width = max((len(loc) for loc in locations), default=0)

    for diag, location in zip(collected, locations, strict=False):
        line = format_diagnostic_line(diag, location, location_width, cfg)
        print(line)


__all__ = [
    "MISSING_CODE_PLACEHOLDER",
    "clean_message",
    "dump_diagnostics",
    "format_diagnostic_line",
    "join_output",
    "raw_location",
    "severity_color",
]
