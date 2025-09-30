# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utilities for repairing SPDX and copyright headers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .licenses import (
    LicensePolicy,
    expected_notice,
    extract_spdx_identifiers,
    normalise_notice,
)

_HASH_STYLE_EXTS: Sequence[str] = (
    ".py",
    ".pyi",
    ".pyw",
    ".sh",
    ".bash",
    ".zsh",
    ".rb",
    ".pl",
    ".pm",
    ".ps1",
    ".psm1",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
)

_SLASH_STYLE_EXTS: Sequence[str] = (
    ".c",
    ".h",
    ".cc",
    ".hh",
    ".cpp",
    ".hpp",
    ".cxx",
    ".hxx",
    ".java",
    ".cs",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".swift",
    ".kt",
    ".kts",
    ".dart",
    ".proto",
)

_HTML_STYLE_EXTS: Sequence[str] = (
    ".html",
    ".htm",
    ".xml",
    ".xhtml",
    ".svg",
    ".md",
    ".markdown",
    ".vue",
)

_RST_STYLE_EXTS: Sequence[str] = (".rst",)

_DASH_STYLE_EXTS: Sequence[str] = (".sql", ".psql", ".pgsql")

_NAME_STYLE_OVERRIDES = {
    "Dockerfile": "hash",
    "Makefile": "hash",
    "BUILD": "hash",
}

_ENCODING_PATTERN = re.compile(r"#.*coding[:=]")


class LicenseFixError(RuntimeError):
    """Raised when a file cannot be automatically repaired."""


class UnsupportedLicenseFixError(LicenseFixError):
    """Raised when there is no known commenting strategy for a file."""


class ConflictingLicenseError(LicenseFixError):
    """Raised when an existing conflicting SPDX identifier is discovered."""

    def __init__(self, identifiers: Iterable[str]) -> None:
        formatted = ", ".join(sorted({identifier for identifier in identifiers if identifier}))
        super().__init__(f"Conflicting SPDX identifier(s) present: {formatted}")


def _default_year() -> int:
    return datetime.now().year


@dataclass(slots=True)
class LicenseHeaderFixer:
    """Add or update SPDX tags and copyright notices in source files."""

    policy: LicensePolicy
    current_year: int = field(default_factory=_default_year)

    def apply(self, path: Path, content: str) -> str | None:
        style = _style_for_path(path)
        if not style:
            suffix = path.suffix or path.name
            raise UnsupportedLicenseFixError(f"Unsupported file type for license header: {suffix}")

        identifiers = extract_spdx_identifiers(content)
        if self.policy.spdx_id:
            allowed = {spdx for spdx in (self.policy.spdx_id, *(self.policy.allow_alternate_spdx or ())) if spdx}
            conflicting = [identifier for identifier in identifiers if identifier not in allowed]
            if conflicting:
                raise ConflictingLicenseError(conflicting)

        spdx_line = self._build_spdx_line(identifiers)
        notice_line = self._build_notice_line(content)
        if spdx_line is None and notice_line is None:
            return None

        updated = _inject_header(content, style, spdx_line, notice_line)
        if updated == content:
            return None
        return updated

    def _build_spdx_line(self, identifiers: set[str]) -> str | None:
        if not (self.policy.require_spdx and self.policy.spdx_id):
            return None
        if self.policy.spdx_id in identifiers:
            return None
        return f"SPDX-License-Identifier: {self.policy.spdx_id}"

    def _build_notice_line(self, content: str) -> str | None:
        if not self.policy.require_notice:
            return None
        observed = self.policy.match_notice(content)
        expected = expected_notice(self.policy, observed, current_year=self.current_year)
        if not expected:
            return None
        if observed and normalise_notice(observed) == normalise_notice(expected):
            return None
        return expected


def _style_for_path(path: Path) -> str | None:
    explicit = _NAME_STYLE_OVERRIDES.get(path.name)
    if explicit:
        return explicit

    suffix = path.suffix.lower()
    if suffix in _HASH_STYLE_EXTS:
        return "hash"
    if suffix in _SLASH_STYLE_EXTS:
        return "slash"
    if suffix in _HTML_STYLE_EXTS:
        return "html"
    if suffix in _RST_STYLE_EXTS:
        return "rst"
    if suffix in _DASH_STYLE_EXTS:
        return "dash"
    return None


def _inject_header(content: str, style: str, spdx_line: str | None, notice_line: str | None) -> str:
    header_lines = [_format_comment(style, entry) for entry in (spdx_line, notice_line) if entry]
    if not header_lines:
        return content

    body = content
    has_bom = False
    if body.startswith("\ufeff"):
        has_bom = True
        body = body[1:]

    trailing_newline = body.endswith("\n")
    lines = body.splitlines()
    insert_at = _insertion_index(style, lines, keep_existing_spdx=spdx_line is None)
    insert_at = _prune_existing_header(
        lines,
        insert_at,
        style,
        remove_spdx=spdx_line is not None,
        remove_notice=notice_line is not None,
    )

    if insert_at < len(lines) and lines[insert_at].strip():
        header_lines.append("")

    lines[insert_at:insert_at] = header_lines
    new_body = "\n".join(lines)
    if trailing_newline or content.endswith("\n"):
        new_body += "\n"
    if has_bom:
        new_body = "\ufeff" + new_body
    return new_body


def _insertion_index(style: str, lines: list[str], *, keep_existing_spdx: bool) -> int:
    if not lines:
        return 0

    index = 0
    if style == "hash":
        while index < len(lines):
            stripped = lines[index].lstrip()
            if stripped.startswith("#!"):
                index += 1
                continue
            if _ENCODING_PATTERN.match(stripped):
                index += 1
                continue
            if not stripped:
                index += 1
                continue
            break
    else:
        while index < len(lines) and not lines[index].strip():
            index += 1

    if keep_existing_spdx:
        while index < len(lines):
            comment = _extract_comment(style, lines[index])
            if comment and comment.lower().startswith("spdx-license-identifier:"):
                index += 1
                continue
            break
    return index


def _prune_existing_header(
    lines: list[str],
    start: int,
    style: str,
    *,
    remove_spdx: bool,
    remove_notice: bool,
) -> int:
    removed = False
    index = start
    while index < len(lines):
        comment = _extract_comment(style, lines[index])
        if comment is None:
            break
        lowered = comment.lower()
        if lowered.startswith("spdx-license-identifier:"):
            if remove_spdx:
                lines.pop(index)
                removed = True
                continue
            index += 1
            continue
        if lowered.startswith("copyright"):
            if remove_notice:
                lines.pop(index)
                removed = True
                continue
            break
        break

    if removed and index < len(lines) and not lines[index].strip():
        lines.pop(index)
    return index


def _format_comment(style: str, text: str) -> str:
    if style == "hash":
        return f"# {text}" if text else "#"
    if style == "slash":
        return f"// {text}" if text else "//"
    if style == "html":
        return f"<!-- {text} -->"
    if style == "rst":
        return f".. {text}" if text else ".."
    if style == "dash":
        return f"-- {text}" if text else "--"
    raise ValueError(f"Unknown comment style: {style}")


def _extract_comment(style: str, line: str) -> str | None:
    stripped = line.strip()
    if style == "hash":
        if stripped.startswith("#") and not stripped.startswith("#!"):
            return stripped[1:].lstrip()
        return None
    if style == "slash":
        if stripped.startswith("//"):
            return stripped[2:].lstrip()
        return None
    if style == "html":
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            return stripped[4:-3].strip()
        return None
    if style == "rst":
        if stripped.startswith(".."):
            return stripped[2:].lstrip()
        return None
    if style == "dash":
        if stripped.startswith("--"):
            return stripped[2:].lstrip()
        return None
    return None
