# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utilities for repairing SPDX and copyright headers."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Final, Protocol, cast


class LicensePolicyProtocol(Protocol):
    """Contract describing the license policy data required by the fixer."""

    spdx_id: str | None
    allow_alternate_spdx: tuple[str, ...]
    require_spdx: bool
    require_notice: bool

    def match_notice(self, content: str) -> str | None:  # pragma: no cover - protocol definition
        """Return the matched copyright notice or ``None`` when missing."""
        raise NotImplementedError

    def should_skip(self, path: Path, root: Path) -> bool:  # pragma: no cover - protocol definition
        """Return whether the given path should be excluded from enforcement."""
        raise NotImplementedError


try:
    _licenses_module = import_module("pyqa.checks.licenses")
except ModuleNotFoundError:  # pragma: no cover - fallback for direct invocation
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    _licenses_module = import_module("pyqa.checks.licenses")

LicensePolicy = cast(type[LicensePolicyProtocol], _licenses_module.LicensePolicy)
expected_notice = _licenses_module.expected_notice
extract_spdx_identifiers = _licenses_module.extract_spdx_identifiers
normalise_notice = _licenses_module.normalise_notice


class CommentStyle(str, Enum):
    """Enumerate supported comment styles for license headers."""

    HASH = "hash"
    SLASH = "slash"
    HTML = "html"
    RST = "rst"
    DASH = "dash"

    def render(self, text: str) -> str:
        """Return ``text`` formatted according to the comment style.

        Args:
            text: Comment payload to render.

        Returns:
            str: Comment line using this style.
        """
        template = RENDER_TOKENS[self]
        if not text:
            return template.empty_line
        return f"{template.prefix}{text}{template.suffix}"

    def extract(self, line: str) -> str | None:
        """Extract the comment payload from ``line`` for the comment style.

        Args:
            line: Source line being analysed.

        Returns:
            str | None: Extracted comment text or ``None`` when the line does
            not contain a comment of this style.
        """

        stripped = line.strip()
        if not stripped:
            return None
        extractor = _COMMENT_EXTRACTORS[self]
        return extractor(stripped)


STYLE_EXTENSIONS: Final[dict[CommentStyle, tuple[str, ...]]] = {
    CommentStyle.HASH: (
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
    ),
    CommentStyle.SLASH: (
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
    ),
    CommentStyle.HTML: (
        ".html",
        ".htm",
        ".xml",
        ".xhtml",
        ".svg",
        ".md",
        ".markdown",
        ".vue",
    ),
    CommentStyle.RST: (".rst",),
    CommentStyle.DASH: (".sql", ".psql", ".pgsql"),
}


NAME_STYLE_OVERRIDES: Final[dict[str, CommentStyle]] = {
    "Dockerfile": CommentStyle.HASH,
    "Makefile": CommentStyle.HASH,
    "BUILD": CommentStyle.HASH,
}


_ENCODING_PATTERN: Final[re.Pattern[str]] = re.compile(r"#.*coding[:=]")
_SPDX_PREFIX: Final[str] = "spdx-license-identifier:"


@dataclass(frozen=True, slots=True)
class RenderTemplate:
    """Describes the tokens required to render header comment lines."""

    prefix: str
    suffix: str
    empty_line: str


RENDER_TOKENS: Final[dict[CommentStyle, RenderTemplate]] = {
    CommentStyle.HASH: RenderTemplate(prefix="# ", suffix="", empty_line="#"),
    CommentStyle.SLASH: RenderTemplate(prefix="// ", suffix="", empty_line="//"),
    CommentStyle.HTML: RenderTemplate(prefix="<!-- ", suffix=" -->", empty_line="<!--  -->"),
    CommentStyle.RST: RenderTemplate(prefix=".. ", suffix="", empty_line=".."),
    CommentStyle.DASH: RenderTemplate(prefix="-- ", suffix="", empty_line="--"),
}


def _extract_hash_comment(line: str) -> str | None:
    """Return a hash-style comment payload from ``line`` when present."""

    if line.startswith("#!"):
        return None
    if line.startswith("#"):
        return line[1:].lstrip()
    return None


def _extract_slash_comment(line: str) -> str | None:
    """Return a C/Java style comment payload from ``line`` when present."""

    if line.startswith("//"):
        return line[2:].lstrip()
    return None


def _extract_html_comment(line: str) -> str | None:
    """Return an HTML-style comment payload from ``line`` when present."""

    if line.startswith("<!--") and line.endswith("-->"):
        return line[4:-3].strip()
    return None


def _extract_rst_comment(line: str) -> str | None:
    """Return an reStructuredText comment payload from ``line`` when present."""

    if line.startswith(".."):
        return line[2:].lstrip()
    return None


def _extract_dash_comment(line: str) -> str | None:
    """Return a SQL-style dash comment payload from ``line`` when present."""

    if line.startswith("--"):
        return line[2:].lstrip()
    return None


_COMMENT_EXTRACTORS: Final[dict[CommentStyle, Callable[[str], str | None]]] = {
    CommentStyle.HASH: _extract_hash_comment,
    CommentStyle.SLASH: _extract_slash_comment,
    CommentStyle.HTML: _extract_html_comment,
    CommentStyle.RST: _extract_rst_comment,
    CommentStyle.DASH: _extract_dash_comment,
}


class LicenseFixError(RuntimeError):
    """Raised when a file cannot be automatically repaired."""


class UnsupportedLicenseFixError(LicenseFixError):
    """Raised when there is no known commenting strategy for a file."""


class ConflictingLicenseError(LicenseFixError):
    """Raised when an existing conflicting SPDX identifier is discovered."""

    def __init__(self, identifiers: Iterable[str]) -> None:
        """Initialise the error with the conflicting SPDX identifiers.

        Args:
            identifiers: Collection of identifiers detected in the file.
        """

        formatted = ", ".join(sorted({identifier for identifier in identifiers if identifier}))
        super().__init__(f"Conflicting SPDX identifier(s) present: {formatted}")


class PruneDecision(str, Enum):
    """Enumerate pruning decisions for existing header lines."""

    DELETE = "delete"
    ADVANCE = "advance"
    STOP = "stop"


def _default_year() -> int:
    """Return the current calendar year.

    Returns:
        int: Calendar year derived from the active system clock.
    """

    return datetime.now().year


@dataclass(slots=True)
class LicenseHeaderFixer:
    """Add or update SPDX tags and copyright notices in source files."""

    policy: LicensePolicyProtocol
    current_year: int = field(default_factory=_default_year)

    def apply(self, path: Path, content: str) -> str | None:
        """Return updated content with repaired license header when needed.

        Args:
            path: Path to the file being evaluated.
            content: Current text content of the file.

        Returns:
            str | None: Newly generated content including the corrected
            header, or ``None`` when no modifications are required.
        """

        style = _style_for_path(path)
        if not style:
            suffix = path.suffix or path.name
            raise UnsupportedLicenseFixError(f"Unsupported file type for license header: {suffix}")

        identifiers = extract_spdx_identifiers(content)
        if self.policy.spdx_id:
            alternate_ids = self.policy.allow_alternate_spdx or ()
            allowed = {spdx for spdx in (self.policy.spdx_id, *alternate_ids) if spdx}
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
        """Return the SPDX header line when one should be inserted.

        Args:
            identifiers: Existing SPDX identifiers discovered in the file.

        Returns:
            str | None: SPDX header line, or ``None`` when no line is required.
        """

        if not (self.policy.require_spdx and self.policy.spdx_id):
            return None
        if self.policy.spdx_id in identifiers:
            return None
        return f"SPDX-License-Identifier: {self.policy.spdx_id}"

    def _build_notice_line(self, content: str) -> str | None:
        """Return the expected copyright notice line when needed.

        Args:
            content: File content under inspection.

        Returns:
            str | None: Canonical copyright notice to insert, or ``None`` when
            no notice change is required.
        """

        if not self.policy.require_notice:
            return None
        observed = self.policy.match_notice(content)
        expected = expected_notice(self.policy, observed, current_year=self.current_year)
        if not expected:
            return None
        if observed and normalise_notice(observed) == normalise_notice(expected):
            return None
        return expected


def _style_for_path(path: Path) -> CommentStyle | None:
    """Return the comment style associated with *path*.

    Args:
        path: File path being analysed.

    Returns:
        CommentStyle | None: Comment style for the file, or ``None`` when the
        file is unsupported.
    """

    explicit = NAME_STYLE_OVERRIDES.get(path.name)
    if explicit is not None:
        return explicit

    suffix = path.suffix.lower()
    for style, extensions in STYLE_EXTENSIONS.items():
        if suffix in extensions:
            return style
    return None


def _inject_header(
    content: str,
    style: CommentStyle,
    spdx_line: str | None,
    notice_line: str | None,
) -> str:
    """Insert or update the license header using the provided comment style.

    Args:
        content: Original file content.
        style: Comment style used to render comment lines.
        spdx_line: SPDX identifier line, when present.
        notice_line: Copyright notice line, when present.

    Returns:
        str: File content with the appropriate header inserted.
    """

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


def _insertion_index(
    style: CommentStyle,
    lines: Sequence[str],
    *,
    keep_existing_spdx: bool,
) -> int:
    """Return the index where a header should be inserted.

    Args:
        style: Comment style used for the header.
        lines: Current file lines.
        keep_existing_spdx: Whether existing SPDX lines should remain.

    Returns:
        int: Index suitable for inserting the new header.
    """

    if not lines:
        return 0

    start_index = _first_content_index(style, lines)
    if not keep_existing_spdx:
        return start_index

    return _skip_existing_spdx(style, lines, start_index)


def _first_content_index(style: CommentStyle, lines: Sequence[str]) -> int:
    """Return the index of the first meaningful line for the given style.

    Args:
        style: Comment style guiding which prelude lines to ignore.
        lines: File lines inspected for the header position.

    Returns:
        int: Index of the first line that should precede a header.
    """

    if style is CommentStyle.HASH:
        for index, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith("#!"):
                continue
            if _ENCODING_PATTERN.match(stripped):
                continue
            if not stripped:
                continue
            return index
        return len(lines)

    for index, line in enumerate(lines):
        if line.strip():
            return index
    return len(lines)


def _skip_existing_spdx(style: CommentStyle, lines: Sequence[str], start_index: int) -> int:
    """Advance past contiguous SPDX comment lines starting at *start_index*.

    Args:
        style: Comment style used to extract comment payloads.
        lines: File lines inspected for SPDX metadata.
        start_index: Index from which to begin scanning.

    Returns:
        int: Updated insertion index after skipping existing SPDX lines.
    """

    index = start_index
    for line in lines[start_index:]:
        comment = style.extract(line)
        if comment and comment.lower().startswith(_SPDX_PREFIX):
            index += 1
            continue
        break
    return index


def _prune_existing_header(
    lines: list[str],
    start: int,
    style: CommentStyle,
    *,
    remove_spdx: bool,
    remove_notice: bool,
) -> int:
    """Remove conflicting header lines and return the next insertion index.

    Args:
        lines: Mutable list of file lines.
        start: Starting index for pruning operations.
        style: Comment style used to interpret existing lines.
        remove_spdx: When ``True`` remove existing SPDX lines.
        remove_notice: When ``True`` remove existing copyright notices.

    Returns:
        int: Index at which a new header should be inserted after pruning.
    """

    indices_to_remove: list[int] = []
    scan_index = start

    for index in range(start, len(lines)):
        comment = style.extract(lines[index])
        if comment is None:
            break
        decision = _classify_header_comment(
            comment,
            remove_spdx=remove_spdx,
            remove_notice=remove_notice,
        )
        if decision is PruneDecision.DELETE:
            indices_to_remove.append(index)
            continue
        if decision is PruneDecision.ADVANCE:
            scan_index = index + 1
            continue
        break

    for index in reversed(indices_to_remove):
        lines.pop(index)
        if index < scan_index:
            scan_index -= 1

    if indices_to_remove:
        scan_index = max(scan_index, start)
        if scan_index < len(lines) and not lines[scan_index].strip():
            lines.pop(scan_index)

    return scan_index


def _classify_header_comment(
    comment: str,
    *,
    remove_spdx: bool,
    remove_notice: bool,
) -> PruneDecision:
    """Return pruning directive for a single comment line.

    Args:
        comment: Comment payload extracted from the source file.
        remove_spdx: Whether conflicting SPDX lines should be removed.
        remove_notice: Whether conflicting copyright notices should be removed.

    Returns:
        PruneDecision: Decision on whether to delete, advance, or stop scanning.

    """

    lowered = comment.lower()
    if lowered.startswith(_SPDX_PREFIX):
        return PruneDecision.DELETE if remove_spdx else PruneDecision.ADVANCE
    if lowered.startswith("copyright"):
        return PruneDecision.DELETE if remove_notice else PruneDecision.STOP
    return PruneDecision.STOP


def _format_comment(style: CommentStyle, text: str) -> str:
    """Format ``text`` according to the provided comment ``style``.

    Args:
        style: Comment style used to render the text.
        text: Comment payload to format.

    Returns:
        str: Comment line using the requested style.
    """

    return style.render(text)


def _extract_comment(style: CommentStyle, line: str) -> str | None:
    """Extract the comment payload for ``line`` using ``style``.

    Args:
        style: Comment style used to interpret the line.
        line: Source line being inspected.

    Returns:
        str | None: Comment payload or ``None`` when the line does not match
        the provided style.
    """

    return style.extract(line)
