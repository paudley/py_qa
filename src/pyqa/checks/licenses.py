# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""License and copyright verification utilities."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Final

try:
    from pyqa.config import LicenseConfig
    from pyqa.constants import ALWAYS_EXCLUDE_DIRS
except ModuleNotFoundError:  # pragma: no cover - fallback for direct invocation
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from pyqa.config import LicenseConfig
    from pyqa.constants import ALWAYS_EXCLUDE_DIRS


KNOWN_LICENSE_SNIPPETS: Final[Mapping[str, str]] = {
    "MIT": "Permission is hereby granted, free of charge",
    "Apache-2.0": "Licensed under the Apache License, Version 2.0",
    "BSD-3-Clause": "Redistribution and use in source and binary forms",
}

PYPROJECT_FILENAME: Final[str] = "pyproject.toml"
PROJECT_TABLE_KEY: Final[str] = "project"
LICENSE_FIELD_KEY: Final[str] = "license"
LICENSE_TEXT_KEY: Final[str] = "text"
LICENSE_FILE_KEY: Final[str] = "file"
AUTHORS_KEY: Final[str] = "authors"
SPDX_TAG_LABEL: Final[str] = "SPDX-License-Identifier"
SPDX_TAG_PREFIX: Final[str] = f"{SPDX_TAG_LABEL.lower()}:"
HTML_COMMENT_START: Final[str] = "<!--"
HTML_COMMENT_END: Final[str] = "-->"
C_BLOCK_COMMENT_START: Final[str] = "/*"
C_BLOCK_COMMENT_END: Final[str] = "*/"
RST_COMMENT_PREFIX: Final[str] = ".."
COLON_CHAR: Final[str] = ":"
COMMENT_PREFIXES: Final[tuple[str, ...]] = (
    "#",
    "//",
    C_BLOCK_COMMENT_START,
    "*",
    "--",
    ";",
    HTML_COMMENT_START,
    RST_COMMENT_PREFIX,
)


_COPYRIGHT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"copyright\s*\(c\)\s*(?P<body>.+)",
    re.IGNORECASE,
)

_SPDX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"SPDX-License-Identifier:\s*([^\s*]+)",
    re.IGNORECASE,
)

_NOTICE_PREFIX: Final[re.Pattern[str]] = re.compile(
    r"copyright\s*\(c\)\s*",
    re.IGNORECASE,
)

_YEAR_RANGE: Final[re.Pattern[str]] = re.compile(
    r"(?P<start>\d{4})(?:\s*[-–]\s*(?P<end>\d{4}))?",
)


@dataclass(slots=True)
class LicenseMetadata:
    """Aggregate license metadata resolved from repository configuration."""

    spdx_id: str | None
    copyright_notice: str | None
    license_text: str | None
    overrides: Mapping[str, object]


@dataclass(slots=True)
class LicensePolicy:
    """Derived enforcement rules for repository licensing."""

    spdx_id: str | None
    canonical_notice: str | None
    license_snippet: str | None
    require_spdx: bool = True
    require_notice: bool = True
    skip_globs: tuple[str, ...] = field(default_factory=tuple)
    allow_alternate_spdx: tuple[str, ...] = field(default_factory=tuple)

    def should_skip(self, path: Path, root: Path) -> bool:
        """Return whether *path* should be skipped under this policy.

        Args:
            path: Absolute path to the file under review.
            root: Repository root directory used for relative comparisons.

        Returns:
            bool: ``True`` when the file should not be evaluated for licensing.
        """

        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            relative = Path(path.name)
        relative_str = str(relative)
        if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
            return True
        return any(fnmatch(relative_str, pattern) for pattern in self.skip_globs)

    def match_notice(self, content: str) -> str | None:
        """Return the first copyright notice discovered in *content*.

        Args:
            content: File contents inspected for a notice.

        Returns:
            str | None: Matched copyright notice, or ``None`` when absent.
        """

        for line in content.splitlines():
            match = _COPYRIGHT_PATTERN.search(line)
            if match:
                return _strip_comment_prefix(line.strip())
        return None


def load_project_license(root: Path) -> LicenseMetadata:
    """Return license metadata derived from project configuration files.

    Args:
        root: Repository root directory.

    Returns:
        LicenseMetadata: Aggregated metadata from ``pyproject.toml`` and
        conventional license files.
    """

    pyproject = root / PYPROJECT_FILENAME
    spdx_id: str | None = None
    copyright_str: str | None = None
    overrides: Mapping[str, object] = {}
    license_text: str | None = None

    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get(PROJECT_TABLE_KEY, {})
        if isinstance(project, Mapping):
            spdx_id = _extract_project_license(project)
            copyright_str = _extract_authors(project)
        overrides = _extract_license_overrides(data)

    license_file = _resolve_license_file(root)
    if license_file:
        text = license_file.read_text(encoding="utf-8")
        license_text = text
        if not spdx_id:
            spdx_id = _infer_license_id(text)
        if not copyright_str:
            copyright_str = _extract_license_copyright(text)

    return LicenseMetadata(
        spdx_id=spdx_id,
        copyright_notice=copyright_str,
        license_text=license_text,
        overrides=overrides,
    )


def load_license_policy(
    root: Path,
    overrides: LicenseConfig | Mapping[str, object] | None = None,
) -> LicensePolicy:
    """Derive a license enforcement policy from project metadata and overrides.

    Args:
        root: Repository root directory.
        overrides: Optional configuration overriding metadata-derived values.

    Returns:
        LicensePolicy: Policy describing enforcement expectations.
    """
    metadata = load_project_license(root)
    if isinstance(overrides, LicenseConfig):
        config: dict[str, object] = _license_config_to_mapping(overrides)
    elif overrides is not None:
        config = dict(overrides)
    else:
        config = dict(metadata.overrides)

    spdx_id = _coerce_optional_str(config.pop("spdx", None)) or metadata.spdx_id
    allow_alternate = tuple(_coerce_str_list(config.pop("allow_alternate_spdx", ())))

    canonical_notice = _build_canonical_notice(config, metadata)
    license_snippet = None
    if spdx_id and spdx_id in KNOWN_LICENSE_SNIPPETS:
        license_snippet = KNOWN_LICENSE_SNIPPETS[spdx_id]
    elif metadata.license_text:
        license_snippet = metadata.license_text[:400]

    skip_globs = tuple(_coerce_str_list(config.pop("exceptions", ())))

    require_spdx = bool(config.pop("require_spdx", True))
    require_notice = bool(config.pop("require_notice", True))

    if config:
        unknown = ", ".join(sorted(config))
        raise ValueError(f"Unknown license configuration keys: {unknown}")

    return LicensePolicy(
        spdx_id=spdx_id,
        canonical_notice=canonical_notice,
        license_snippet=license_snippet,
        require_spdx=require_spdx,
        require_notice=require_notice,
        skip_globs=skip_globs,
        allow_alternate_spdx=allow_alternate,
    )


def _extract_project_license(project: Mapping[str, object]) -> str | None:
    """Return the SPDX identifier derived from the project's license field.

    Args:
        project: ``[project]`` table loaded from ``pyproject.toml``.

    Returns:
        str | None: SPDX identifier when one can be resolved; otherwise ``None``.
    """

    license_field = project.get(LICENSE_FIELD_KEY)
    if isinstance(license_field, str):
        return license_field.strip()
    if isinstance(license_field, Mapping):
        if LICENSE_TEXT_KEY in license_field:
            return _infer_license_id(str(license_field[LICENSE_TEXT_KEY]))
        if LICENSE_FILE_KEY in license_field:
            return None  # to be extracted via file
    return None


def _extract_authors(project: Mapping[str, object]) -> str | None:
    """Return the first author name declared in project metadata.

    Args:
        project: ``[project]`` table from ``pyproject.toml``.

    Returns:
        str | None: Author name when available.
    """

    authors = project.get(AUTHORS_KEY)
    if isinstance(authors, list) and authors:
        first = authors[0]
        if isinstance(first, Mapping):
            name = first.get("name")
            if isinstance(name, str):
                return name
    return None


def _resolve_license_file(root: Path) -> Path | None:
    """Return the path to a known license file within *root*.

    Args:
        root: Repository root directory.

    Returns:
        Path | None: Path to the first recognised license file, or ``None``
        when no file exists.
    """

    for candidate in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        path = root / candidate
        if path.exists():
            return path
    return None


def _infer_license_id(text: str) -> str | None:
    """Infer an SPDX identifier from license *text* content.

    Args:
        text: License text body.

    Returns:
        str | None: Resolved SPDX identifier, or ``None`` when heuristics fail.
    """

    lower = text.lower()
    for spdx, snippet in KNOWN_LICENSE_SNIPPETS.items():
        if snippet.lower() in lower:
            return spdx
    return None


def _extract_license_copyright(text: str) -> str | None:
    """Return the first copyright notice discovered in license *text*.

    Args:
        text: License file contents.

    Returns:
        str | None: Matched copyright notice, or ``None`` when absent.
    """

    for raw_line in text.splitlines():
        candidate = raw_line.strip()
        if candidate.lower().startswith("copyright"):
            return candidate
    return None


def verify_file_license(
    path: Path,
    content: str,
    policy: LicensePolicy,
    root: Path,
    *,
    current_year: int | None = None,
) -> list[str]:
    """Return lint findings for *path* under the provided licensing *policy*.

    Args:
        path: File path associated with ``content``.
        content: Text content of the file under inspection.
        policy: Licensing policy derived for the repository.
        root: Repository root directory.
        current_year: Optional override for the current calendar year.

    Returns:
        list[str]: Human-readable issues describing detected policy violations.
    """

    if policy.should_skip(path, root):
        return []

    year = current_year or datetime.now().year
    lower_content = content.lower()

    issues = _collect_spdx_issues(content, lower_content, policy)
    issues.extend(_collect_notice_issues(content, policy, year))
    return issues


def _collect_spdx_issues(content: str, lower_content: str, policy: LicensePolicy) -> list[str]:
    """Return SPDX-related issues for *content* under *policy*.

    Args:
        content: Original file content.
        lower_content: Lower-cased version of ``content`` for snippet search.
        policy: Licensing policy describing expected identifiers.

    Returns:
        list[str]: SPDX-related policy violations.
    """

    issues: list[str] = []
    if not policy.require_spdx:
        return issues

    identifiers = extract_spdx_identifiers(content)
    expected_id = policy.spdx_id
    alternate_spdx = policy.allow_alternate_spdx or ()
    allowed = {spdx for spdx in (expected_id, *alternate_spdx) if spdx}
    snippet = policy.license_snippet

    if expected_id:
        conflicting = sorted(identifier for identifier in identifiers if identifier not in allowed)
        if conflicting:
            formatted = ", ".join(conflicting)
            message = f"Found SPDX license identifier(s) {formatted}; expected '{expected_id}'."
            issues.append(message)
        if not identifiers.intersection(allowed) and not _matches_snippet(lower_content, snippet):
            expected_tag = f"{SPDX_TAG_LABEL}: {expected_id}"
            issues.append(f"Missing SPDX license tag '{expected_tag}'")
        return issues

    if not identifiers and not _matches_snippet(lower_content, snippet):
        issues.append(
            "Missing SPDX license tag; configure a project SPDX identifier or header snippet.",
        )
    return issues


def _collect_notice_issues(content: str, policy: LicensePolicy, current_year: int) -> list[str]:
    """Return notice-related issues for *content* under *policy*.

    Args:
        content: File content inspected for notice text.
        policy: Licensing policy describing notice expectations.
        current_year: Calendar year used when synthesising expected notices.

    Returns:
        list[str]: Policy violations involving copyright notices.
    """

    issues: list[str] = []
    if not policy.require_notice:
        return issues

    observed = policy.match_notice(content)
    expected = expected_notice(policy, observed, current_year=current_year)

    if not observed:
        if expected:
            issues.append(f"Missing copyright notice '{expected}'")
        if policy.canonical_notice:
            issues.append(f"Missing copyright notice '{policy.canonical_notice}'")
        if not issues:
            issues.append("Missing copyright notice")
        return issues

    if expected and not _notices_equal(observed, expected):
        issues.append(
            f"Mismatched copyright notice. Found '{observed}' but expected '{expected}'.",
        )

    return issues


def _matches_snippet(lower_content: str, snippet: str | None) -> bool:
    """Return whether ``lower_content`` contains the provided license snippet.

    Args:
        lower_content: Content lowered to simplify substring detection.
        snippet: Optional snippet expected to appear in the content.

    Returns:
        bool: ``True`` when the snippet is present.
    """

    if not snippet:
        return False
    return snippet.lower() in lower_content


def _notices_equal(left: str, right: str) -> bool:
    """Return whether two notices are equivalent after normalisation.

    Args:
        left: First notice string.
        right: Second notice string.

    Returns:
        bool: ``True`` when both notices are equivalent.
    """

    return normalise_notice(left) == normalise_notice(right)


def normalise_notice(value: str) -> str:
    """Return a canonical form of a copyright notice.

    Args:
        value: Original notice string.

    Returns:
        str: Lower-cased, whitespace-normalised notice text.
    """

    stripped = _strip_comment_prefix(value)
    return re.sub(r"\s+", " ", stripped).strip().lower()


def extract_spdx_identifiers(content: str) -> set[str]:
    """Return SPDX identifiers found in comment lines within *content*.

    Args:
        content: File content searched for SPDX headers.

    Returns:
        set[str]: Unique SPDX identifiers discovered in the content.
    """
    identifiers: set[str] = set()
    for line in content.splitlines():
        payload = _comment_payload(line)
        if payload is None:
            stripped = line.lstrip()
            if not stripped.lower().startswith(SPDX_TAG_PREFIX):
                continue
            payload = stripped
        match = _SPDX_PATTERN.search(payload)
        if not match:
            continue
        candidate = match.group(1).strip().rstrip('"').rstrip("'/")
        if candidate:
            identifiers.add(candidate)
    return identifiers


def _comment_payload(line: str) -> str | None:
    """Return the comment payload extracted from ``line`` when possible.

    Args:
        line: Source line inspected for a comment payload.

    Returns:
        str | None: Comment payload with surrounding delimiters removed.
    """

    stripped = line.lstrip()
    if not stripped:
        return None
    for prefix in COMMENT_PREFIXES:
        if not stripped.startswith(prefix):
            continue
        payload = stripped[len(prefix) :].lstrip()
        if prefix == HTML_COMMENT_START and payload.endswith(HTML_COMMENT_END):
            payload = payload[: -len(HTML_COMMENT_END)].rstrip()
        if prefix == C_BLOCK_COMMENT_START and payload.endswith(C_BLOCK_COMMENT_END):
            payload = payload[: -len(C_BLOCK_COMMENT_END)].rstrip()
        return payload
    return None


@dataclass(frozen=True)
class _NoticeParts:
    """Structured representation of the components of a notice string."""

    start: int | None
    end: int | None
    owner: str | None


def expected_notice(
    policy: LicensePolicy,
    observed_notice: str | None,
    *,
    current_year: int | None = None,
) -> str | None:
    """Return the canonical notice string expected for a file under *policy*.

    Args:
        policy: Licensing policy describing notice expectations.
        observed_notice: Existing notice detected within the file.
        current_year: Year used when constructing notice ranges.

    Returns:
        str | None: Canonical notice or ``None`` when no notice is required.
    """
    if not policy.require_notice:
        return None

    base_notice = policy.canonical_notice or observed_notice
    if not base_notice:
        return None

    baseline = _parse_notice(base_notice)
    observed = _parse_notice(observed_notice)

    owner = baseline.owner or observed.owner
    if owner is None:
        return base_notice

    year = current_year or datetime.now().year
    start_candidates = [value for value in (observed.start, baseline.start) if value]
    start_year = min(start_candidates) if start_candidates else year

    end_candidates = [value for value in (observed.end, baseline.end) if value is not None]
    end_year = max(end_candidates) if end_candidates else None
    if end_year is not None and end_year < start_year:
        end_year = start_year

    latest_candidates = [candidate for candidate in (end_year, year) if candidate is not None]
    latest = max(latest_candidates) if latest_candidates else year
    latest = max(latest, start_year)

    year_expression = f"{start_year}" if latest == start_year else f"{start_year}-{latest}"

    return f"Copyright (c) {year_expression} {owner}".strip()


def _parse_notice(value: str | None) -> _NoticeParts:
    """Return structured components extracted from a notice string.

    Args:
        value: Notice string to parse.

    Returns:
        _NoticeParts: Parsed year range and owner metadata.
    """

    if not value:
        return _NoticeParts(None, None, None)

    stripped = value.strip()
    match = _NOTICE_PREFIX.match(stripped)
    if not match:
        return _NoticeParts(None, None, stripped or None)

    body = stripped[match.end() :].strip()
    if not body:
        return _NoticeParts(None, None, None)

    year_match = _YEAR_RANGE.match(body)
    if not year_match:
        return _NoticeParts(None, None, body or None)

    start_year = int(year_match.group("start"))
    end_year: int | None = None
    end_str = year_match.group("end")
    if end_str and end_str.isdigit():
        end_year = int(end_str)

    owner = body[year_match.end() :].strip() or None
    return _NoticeParts(start_year, end_year, owner)


def _build_canonical_notice(
    config: MutableMapping[str, object],
    metadata: LicenseMetadata,
) -> str | None:
    """Return the canonical notice derived from configuration and metadata.

    Args:
        config: Mutable configuration mapping used to resolve overrides.
        metadata: Metadata discovered from project configuration or files.

    Returns:
        str | None: Canonical notice string when derivable.
    """

    explicit_notice = _coerce_optional_str(config.pop("notice", None))
    if explicit_notice:
        return explicit_notice.strip()

    owner = _coerce_optional_str(config.pop("copyright", None))
    year = _coerce_optional_str(config.pop("year", None))
    if owner and year:
        return f"Copyright (c) {year} {owner}".strip()

    if owner and metadata.copyright_notice:
        extracted_year = _extract_year(metadata.copyright_notice)
        if extracted_year:
            return f"Copyright (c) {extracted_year} {owner}".strip()

    if metadata.copyright_notice:
        return metadata.copyright_notice.strip()

    return None


def _extract_year(notice: str) -> str | None:
    """Return the year or year range extracted from a notice string.

    Args:
        notice: Copyright notice string.

    Returns:
        str | None: Extracted year expression when present.
    """

    year_match = re.search(r"(\d{4}(?:\s*[-–]\s*\d{4}|\s*\+?|\s*present)?)", notice)
    if year_match:
        return year_match.group(1).replace("  ", " ").strip()
    return None


def _extract_license_overrides(data: Mapping[str, object]) -> Mapping[str, object]:
    """Return license override configuration embedded within *data*.

    Args:
        data: Parsed ``pyproject.toml`` payload.

    Returns:
        Mapping[str, object]: Extracted override mapping or an empty mapping.
    """

    tool = data.get("tool")
    if isinstance(tool, Mapping):
        pyqa = tool.get("pyqa")
        if isinstance(pyqa, Mapping):
            license_cfg = pyqa.get("license")
            if isinstance(license_cfg, Mapping):
                return dict(license_cfg)
    return {}


def _coerce_optional_str(value: object) -> str | None:
    """Return a stripped string when ``value`` is a string, otherwise ``None``.

    Args:
        value: Value to normalise.

    Returns:
        str | None: Stripped string or ``None`` when ``value`` is falsy.

    Raises:
        ValueError: If ``value`` is neither ``None`` nor a string.
    """

    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    raise ValueError("Expected string value")


def _coerce_str_list(value: object) -> tuple[str, ...]:
    """Return a tuple of stripped strings derived from ``value``.

    Args:
        value: Candidate sequence of strings.

    Returns:
        tuple[str, ...]: Tuple containing non-empty, stripped string values.

    Raises:
        ValueError: If ``value`` is not ``None`` and not an iterable of strings.
    """

    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                raise ValueError("Expected string in list")
            trimmed = entry.strip()
            if trimmed:
                result.append(trimmed)
        return tuple(result)
    raise ValueError("Expected list of strings")


def _strip_comment_prefix(line: str) -> str:
    """Return ``line`` stripped of leading comment syntax and adornments.

    Args:
        line: Source line potentially containing comment delimiters.

    Returns:
        str: Line contents with surrounding comment delimiters removed.
    """

    cleaned = line.lstrip()
    for prefix in COMMENT_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].lstrip(" -*#/")
            break
    if cleaned.startswith('"') and COLON_CHAR in cleaned:
        _, remainder = cleaned.split(COLON_CHAR, 1)
        cleaned = remainder.strip()
        if cleaned.endswith(","):
            cleaned = cleaned[:-1].rstrip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
    if cleaned.endswith(C_BLOCK_COMMENT_END):
        cleaned = cleaned[: -len(C_BLOCK_COMMENT_END)].rstrip()
    if cleaned.endswith(HTML_COMMENT_END):
        cleaned = cleaned[: -len(HTML_COMMENT_END)].rstrip()
    return cleaned.strip()


def _license_config_to_mapping(config: LicenseConfig) -> dict[str, object]:
    """Return a mapping representation of ``config`` with empty values pruned.

    Args:
        config: License configuration model to serialise.

    Returns:
        dict[str, object]: Mapping containing only truthy configuration values.
    """

    payload = config.model_dump(mode="python")
    return {key: value for key, value in payload.items() if value not in (None, [], "")}
