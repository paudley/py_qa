# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for filtering diagnostics and normalising duplicate-code entries."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from ..filesystem.paths import normalize_path_key
from ..models import Diagnostic

_DUPLICATE_PREFIX: Final[str] = "=="
_TRAILING_SPAN = re.compile(r":(?P<start>\d+)(?::(?P<end>\d+))?\s*$")

PYLINT_TOOL: Final[str] = "pylint"
TOMBI_TOOL: Final[str] = "tombi"
TOMBI_OUT_OF_ORDER_MSG: Final[str] = "defining tables out-of-order is discouraged"
_INIT_BASENAMES: Final[frozenset[str]] = frozenset({"__init__.py", "__init__.pyi"})
DUPLICATE_CODES: Final[frozenset[str]] = frozenset({"R0801", "DUPLICATE-CODE"})
SUPPRESSED_TEST_CODES: Final[frozenset[str]] = DUPLICATE_CODES | {"W0613", "W0212"}
TEST_PATH_FRAGMENT: Final[str] = "/tests/"
PATH_SEPARATOR: Final[str] = "/"
SEARCH_PREFIXES: Final[tuple[str, ...]] = ("", "src/", "tests/", "tooling/", "docs/", "ref_docs/")
PY_SOURCE_SUFFIXES: Final[frozenset[str]] = frozenset({".py", ".pyi"})
DEFAULT_FALLBACK_SUFFIX: Final[str] = ".py"


@dataclass(slots=True)
class DuplicateCodeEntry:
    """Duplicate-code entry extracted from a diagnostic message."""

    key: str
    path: str
    line: int | None


@dataclass(slots=True)
class DuplicateCodeDeduper:
    """Stateful helper that suppresses redundant duplicate-code diagnostics."""

    root: Path
    seen_groups: set[tuple[str, ...]] = field(default_factory=set)

    def keep(self, diagnostic: Diagnostic) -> bool:
        """Return ``True`` when *diagnostic* should be retained.

        Args:
            diagnostic: Diagnostic emitted by pylint that may reference
                duplicate code segments.

        Returns:
            bool: ``True`` when the diagnostic should be kept. Returns ``False``
            when the diagnostic is redundant or only references commented code.
        """

        entries = collect_duplicate_entries(diagnostic.message, self.root)
        if any(_is_init_path(entry.path) for entry in entries):
            return False
        if not entries:
            return False
        group_key = duplicate_group_key(entries)
        if group_key:
            if group_key in self.seen_groups:
                return False
            self.seen_groups.add(group_key)
            preferred = select_duplicate_primary(entries, diagnostic, self.root)
            if preferred is not None:
                diagnostic.file = preferred.path
                if preferred.line is not None:
                    diagnostic.line = preferred.line

        if duplicate_context_is_commented(diagnostic, self.root):
            return False
        return True


def filter_diagnostics(
    diagnostics: Sequence[Diagnostic],
    tool_name: str,
    patterns: Sequence[str],
    root: Path,
) -> list[Diagnostic]:
    """Return diagnostics filtered by suppression patterns and heuristics.

    Args:
        diagnostics: Diagnostics emitted by a tool run.
        tool_name: Name of the tool associated with ``diagnostics``.
        patterns: Regular expression patterns describing suppressions.
        root: Project root used to resolve absolute file paths.

    Returns:
        list[Diagnostic]: Filtered diagnostics that should be reported.
    """

    if not diagnostics:
        return []

    compiled = [re.compile(pattern) for pattern in patterns] if patterns else []
    deduper = DuplicateCodeDeduper(root)

    kept: list[Diagnostic] = []
    for diagnostic in diagnostics:
        tool = diagnostic.tool or tool_name
        candidate = _candidate_signature(diagnostic, tool)
        if compiled and any(pattern.search(candidate) for pattern in compiled):
            continue

        upper_code = (diagnostic.code or "").upper()
        if tool == PYLINT_TOOL and upper_code in DUPLICATE_CODES:
            if not deduper.keep(diagnostic):
                continue

        if _suppress_tombi_out_of_order(diagnostic, tool):
            continue

        if (
            tool == PYLINT_TOOL
            and upper_code in SUPPRESSED_TEST_CODES
            and diagnostic.file
            and is_test_path(diagnostic.file)
        ):
            continue

        kept.append(diagnostic)
    return kept


def _is_init_path(path: str) -> bool:
    """Return ``True`` when ``path`` references a package ``__init__`` file."""

    candidate = Path(path).name.lower()
    return candidate in _INIT_BASENAMES


def _suppress_tombi_out_of_order(diagnostic: Diagnostic, tool: str) -> bool:
    """Return ``True`` when tombi should skip the out-of-order warning."""

    if tool != TOMBI_TOOL or not diagnostic.file:
        return False
    file_path = diagnostic.file.strip().lower()
    if not file_path.endswith("pyproject.toml"):
        return False
    message = diagnostic.message.lower()
    return TOMBI_OUT_OF_ORDER_MSG in message


def _candidate_signature(diagnostic: Diagnostic, tool: str) -> str:
    """Return a stable string representation used for suppression checks.

    Args:
        diagnostic: Diagnostic to normalise for suppression matching.
        tool: Name of the tool that produced ``diagnostic``.

    Returns:
        str: Stable string containing tool, location, code, and message.
    """

    location = _format_location(diagnostic, diagnostic.file or "<unknown>")
    code = diagnostic.code or "-"
    message = diagnostic.message.splitlines()[0].strip()
    return f"{tool}, {location}, {code}, {message}"


def _format_location(diagnostic: Diagnostic, default_path: str) -> str:
    """Return a stable location string for ``diagnostic``.

    Args:
        diagnostic: Diagnostic whose location should be formatted.
        default_path: Default path used when the diagnostic omits file data.

    Returns:
        str: Location string combining file, line, and function details.
    """

    components = [default_path]
    if diagnostic.line is not None:
        components.append(str(diagnostic.line))
    if diagnostic.function:
        components.append(diagnostic.function)
    return ":".join(components)


def duplicate_context_is_commented(diagnostic: Diagnostic, root: Path) -> bool:
    """Return ``True`` when the duplicate context only contains comments.

    Args:
        diagnostic: Duplicate-code diagnostic emitted by pylint.
        root: Project root used to resolve file paths when reading sources.

    Returns:
        bool: ``True`` when the diagnostic context is purely commented code.
    """

    snippet = _extract_duplicate_snippet(diagnostic.message)
    context_line = (diagnostic.function or "").lstrip()
    if context_line.startswith("#"):
        return True
    if snippet and snippet[0].startswith("#"):
        return True
    if diagnostic.line is not None and diagnostic.file:
        source_line = read_source_line(root, diagnostic.file, diagnostic.line)
        if source_line is not None and source_line.lstrip().startswith("#"):
            return True
    return False


def _extract_duplicate_snippet(message: str) -> list[str]:
    """Return non-empty snippet lines extracted from a duplicate message.

    Args:
        message: Diagnostic message that may contain duplicate-code details.

    Returns:
        list[str]: Snippet lines excluding headers and annotations.
    """

    snippet: list[str] = []
    for entry in message.splitlines()[1:]:
        stripped = entry.lstrip()
        if not stripped or stripped.startswith(_DUPLICATE_PREFIX):
            continue
        snippet.append(stripped)
    return snippet


def read_source_line(root: Path, file_str: str, line_no: int) -> str | None:
    """Return the specified ``line_no`` from ``file_str`` relative to ``root``.

    Args:
        root: Project root used to resolve ``file_str`` when relative.
        file_str: File path provided by the diagnostic payload.
        line_no: One-based source line requested from ``file_str``.

    Returns:
        str | None: Requested line stripped of the trailing newline, or ``None``
        when the file cannot be read.
    """

    candidate = Path(file_str)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    try:
        handle = candidate.open("r", encoding="utf-8", errors="ignore")
    except OSError:
        return None
    with handle:
        for index, line in enumerate(handle, start=1):
            if index == line_no:
                return line.rstrip("\n")
    return None


def collect_duplicate_entries(message: str, root: Path) -> list[DuplicateCodeEntry]:
    """Extract duplicate-code entry metadata from *message*.

    Args:
        message: Diagnostic message emitted by pylint duplicate-code checks.
        root: Project root used to resolve candidate file paths.

    Returns:
        list[DuplicateCodeEntry]: Parsed duplicate entries contained in
        ``message``.
    """

    entries: list[DuplicateCodeEntry] = []
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    details: list[str] = []

    for line in lines[1:]:
        if line.startswith(_DUPLICATE_PREFIX):
            details.append(line[2:].strip())

    if not details and lines:
        _, _, suffix = lines[0].partition(":")
        if suffix:
            details.extend(token.strip() for token in suffix.split(",") if token.strip())

    for detail in details:
        name, span = split_duplicate_code_entry(detail)
        if not name:
            continue
        path = resolve_duplicate_target(name, root)
        span_token = span.strip()
        try:
            key_path = normalize_path_key(path, base_dir=root)
        except ValueError:
            key_path = path.replace("\\", "/")
        key = key_path.lower()
        if span_token:
            key = f"{key}|{span_token.lower()}"
        entries.append(
            DuplicateCodeEntry(
                key=key,
                path=path,
                line=parse_duplicate_line(span_token),
            ),
        )
    return entries


def duplicate_group_key(entries: Sequence[DuplicateCodeEntry]) -> tuple[str, ...]:
    """Return a stable key describing a duplicate-code diagnostic group.

    Args:
        entries: Duplicate entries associated with a diagnostic.

    Returns:
        tuple[str, ...]: Sorted key describing the duplicate group.
    """

    if not entries:
        return ()
    unique_keys = {entry.key for entry in entries}
    return tuple(sorted(unique_keys))


def select_duplicate_primary(
    entries: Sequence[DuplicateCodeEntry],
    diagnostic: Diagnostic,
    root: Path,
) -> DuplicateCodeEntry | None:
    """Choose the entry that should anchor the duplicate diagnostic.

    Args:
        entries: Candidate duplicate entries extracted from the message.
        diagnostic: Diagnostic currently under consideration.
        root: Project root used for relative path normalisation.

    Returns:
        DuplicateCodeEntry | None: Preferred entry to anchor the diagnostic or
        ``None`` when no entry is suitable.
    """

    if not entries:
        return None

    current = normalise_duplicate_path(diagnostic.file or "", root)
    for entry in entries:
        if current and normalise_duplicate_path(entry.path, root) == current:
            return entry

    for entry in entries:
        if not is_test_path(entry.path):
            return entry

    return entries[0]


def normalise_duplicate_path(path: str, root: Path) -> str:
    """Return a normalised comparison key for ``path`` relative to ``root``.

    Args:
        path: Input path to normalise.
        root: Project root used to compute relative keys.

    Returns:
        str: Normalised key used for duplicate grouping.
    """

    if not path:
        return ""
    try:
        return normalize_path_key(path, base_dir=root)
    except ValueError:
        return path.replace("\\", "/")


def is_test_path(path: str) -> bool:
    """Return ``True`` when ``path`` points inside a tests directory.

    Args:
        path: Path string to evaluate.

    Returns:
        bool: ``True`` when ``path`` references a test directory.
    """

    normalized = path.replace("\\", "/").lower()
    return normalized.startswith("tests/") or TEST_PATH_FRAGMENT in normalized


def resolve_duplicate_target(name: str, root: Path) -> str:
    """Resolve a pylint duplicate-code target to a stable display path.

    Args:
        name: Raw target name extracted from the diagnostic.
        root: Project root used for path resolution.

    Returns:
        str: Normalised path representation for the duplicate target.
    """

    variants = generate_duplicate_variants(name)
    existing = _find_existing_variant(variants, root)
    if existing:
        return existing

    prefixed = _search_prefixed_variants(variants, root)
    if prefixed:
        return prefixed

    fallback = _select_fallback_variant(variants, name)
    return _normalise_fallback(fallback, root)


def _find_existing_variant(variants: Sequence[str], root: Path) -> str | None:
    """Return the first existing variant when one is available.

    Args:
        variants: Candidate variant paths produced from the diagnostic payload.
        root: Project root used to normalise resolved paths.

    Returns:
        str | None: Normalised path when an existing variant is found, otherwise ``None``.
    """

    for variant in variants:
        candidate = Path(variant)
        if candidate.is_absolute() and candidate.exists():
            return normalize_path_key(candidate, base_dir=root)
    return None


def _search_prefixed_variants(variants: Sequence[str], root: Path) -> str | None:
    """Search canonical prefixes for the supplied variants.

    Args:
        variants: Candidate variant paths derived from the diagnostic payload.
        root: Project root used to construct search paths.

    Returns:
        str | None: Normalised path when a prefixed variant exists, otherwise ``None``.
    """

    for variant in variants:
        for prefix in SEARCH_PREFIXES:
            candidate = (root / prefix / variant).resolve()
            if candidate.exists():
                return normalize_path_key(candidate, base_dir=root)
    return None


def _select_fallback_variant(variants: Sequence[str], original: str) -> str:
    """Select a fallback variant when no filesystem match is found.

    Args:
        variants: Candidate variant paths produced from the message content.
        original: Original name fragment supplied by pylint.

    Returns:
        str: Fallback variant string to normalise for display.
    """

    prioritized = [
        variant for variant in variants if PATH_SEPARATOR in variant and Path(variant).suffix in PY_SOURCE_SUFFIXES
    ]
    if not prioritized:
        prioritized = [variant for variant in variants if PATH_SEPARATOR in variant]
    if not prioritized:
        prioritized = list(variants)
    if prioritized:
        return prioritized[0]
    return original.strip().replace("\\", PATH_SEPARATOR)


def _normalise_fallback(candidate: str, root: Path) -> str:
    """Normalise a fallback variant relative to ``root``.

    Args:
        candidate: Candidate path fragment chosen as fallback.
        root: Project root used to normalise the fallback path.

    Returns:
        str: Normalised fallback path suitable for display.
    """

    normalised = candidate.strip().replace("\\", PATH_SEPARATOR).lstrip("./")
    if Path(normalised).suffix == "":
        normalised = f"{normalised}{DEFAULT_FALLBACK_SUFFIX}"
    try:
        return normalize_path_key(normalised, base_dir=root)
    except ValueError:
        return normalised


def generate_duplicate_variants(name: str) -> list[str]:
    """Return candidate path variants for a duplicate-code entry name.

    Args:
        name: Raw duplicate target name reported by pylint.

    Returns:
        list[str]: Candidate path variants to search for on disk.
    """

    token = name.strip().strip("\"'")
    token = token.replace("\\", PATH_SEPARATOR)
    if not token:
        return []

    base_variants = [token]
    dotted = token.replace(".", PATH_SEPARATOR)
    if dotted != token:
        base_variants.append(dotted)

    seen: set[str] = set()
    variants: list[str] = []
    for variant in base_variants:
        cleaned = variant.lstrip(f".{PATH_SEPARATOR}")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            variants.append(cleaned)
        if cleaned and Path(cleaned).suffix == "":
            with_ext = f"{cleaned}{DEFAULT_FALLBACK_SUFFIX}"
            if with_ext not in seen:
                seen.add(with_ext)
                variants.append(with_ext)
            if not cleaned.endswith("__init__"):
                init_variant = f"{cleaned}{PATH_SEPARATOR}__init__{DEFAULT_FALLBACK_SUFFIX}"
                if init_variant not in seen:
                    seen.add(init_variant)
                    variants.append(init_variant)
    return variants


def split_duplicate_code_entry(entry: str) -> tuple[str, str]:
    """Split ``entry`` into the referenced module/file name and line span.

    Args:
        entry: Raw entry string from the duplicate-code message.

    Returns:
        tuple[str, str]: Name component and span token extracted from ``entry``.
    """

    stripped = entry.strip()
    bracket_index = stripped.find("[")
    if bracket_index != -1:
        name = stripped[:bracket_index].rstrip(":")
        span = stripped[bracket_index:]
        return name.strip(), span.strip()

    match = _TRAILING_SPAN.search(stripped)
    if match:
        name = stripped[: match.start()].rstrip(":")
        start = match.group("start")
        end = match.group("end")
        if end:
            span = f"[{start}:{end}]"
        else:
            span = f"[{start}]"
        return name.strip(), span

    return stripped, ""


def parse_duplicate_line(span: str) -> int | None:
    """Return the starting line from a duplicate-code span like ``[12:18]``.

    Args:
        span: Span token extracted from the duplicate message.

    Returns:
        int | None: Parsed starting line or ``None`` when unavailable.
    """

    cleaned = span.strip()[1:-1] if span.startswith("[") and span.endswith("]") else span.strip()
    head, _, _ = cleaned.partition(":")
    try:
        return int(head)
    except ValueError:
        return None


__all__ = [
    "DuplicateCodeEntry",
    "DuplicateCodeDeduper",
    "collect_duplicate_entries",
    "duplicate_group_key",
    "filter_diagnostics",
    "generate_duplicate_variants",
    "is_test_path",
    "parse_duplicate_line",
    "read_source_line",
    "resolve_duplicate_target",
    "select_duplicate_primary",
    "split_duplicate_code_entry",
]
