# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""License and copyright verification utilities."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Final

from pyqa.config import LicenseConfig
from pyqa.constants import ALWAYS_EXCLUDE_DIRS

KNOWN_LICENSE_SNIPPETS: Final[Mapping[str, str]] = {
    "MIT": "Permission is hereby granted, free of charge",
    "Apache-2.0": "Licensed under the Apache License, Version 2.0",
    "BSD-3-Clause": "Redistribution and use in source and binary forms",
}


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


@dataclass
class LicenseMetadata:
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
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            relative = Path(path.name)
        relative_str = str(relative)
        if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
            return True
        return any(fnmatch(relative_str, pattern) for pattern in self.skip_globs)

    def match_notice(self, content: str) -> str | None:
        for line in content.splitlines():
            match = _COPYRIGHT_PATTERN.search(line)
            if match:
                return _strip_comment_prefix(line.strip())
        return None


def load_project_license(root: Path) -> LicenseMetadata:
    """Attempt to load license metadata from pyproject.toml or fallback."""
    pyproject = root / "pyproject.toml"
    spdx_id: str | None = None
    copyright_str: str | None = None
    overrides: Mapping[str, object] = {}
    license_text: str | None = None

    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project", {})
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
    """Derive a license enforcement policy from project metadata and overrides."""
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
    license_field = project.get("license")
    if isinstance(license_field, str):
        return license_field.strip()
    if isinstance(license_field, Mapping):
        if "text" in license_field:
            return _infer_license_id(str(license_field["text"]))
        if "file" in license_field:
            return None  # to be extracted via file
    return None


def _extract_authors(project: Mapping[str, object]) -> str | None:
    authors = project.get("authors")
    if isinstance(authors, list) and authors:
        first = authors[0]
        if isinstance(first, Mapping):
            name = first.get("name")
            if isinstance(name, str):
                return name
    return None


def _resolve_license_file(root: Path) -> Path | None:
    for candidate in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        path = root / candidate
        if path.exists():
            return path
    return None


def _infer_license_id(text: str) -> str | None:
    lower = text.lower()
    for spdx, snippet in KNOWN_LICENSE_SNIPPETS.items():
        if snippet.lower() in lower:
            return spdx
    return None


def _extract_license_copyright(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("copyright"):
            return line
    return None


def verify_file_license(
    path: Path,
    content: str,
    policy: LicensePolicy,
    root: Path,
    *,
    current_year: int | None = None,
) -> list[str]:
    """Return list of issues detected for *path* under the provided *policy*."""
    if policy.should_skip(path, root):
        return []

    issues: list[str] = []
    lower_content = content.lower()
    year = current_year or datetime.now().year

    if policy.require_spdx:
        identifiers = extract_spdx_identifiers(content)
        expected_id = policy.spdx_id
        expected_tag = f"SPDX-License-Identifier: {expected_id}" if expected_id else None
        allowed = {spdx for spdx in (expected_id, *(policy.allow_alternate_spdx or ())) if spdx}

        if expected_id:
            conflicting = sorted(identifier for identifier in identifiers if identifier not in allowed)
            if conflicting:
                formatted = ", ".join(conflicting)
                issues.append(
                    f"Found SPDX license identifier(s) {formatted}; expected '{expected_id}'.",
                )
            elif not identifiers.intersection(allowed) and not _matches_snippet(
                lower_content,
                policy.license_snippet,
            ):
                issues.append(f"Missing SPDX license tag '{expected_tag}'")
        elif not identifiers and not _matches_snippet(lower_content, policy.license_snippet):
            issues.append(
                "Missing SPDX license tag; configure a project SPDX identifier or header snippet.",
            )

    if policy.require_notice:
        observed = policy.match_notice(content)
        expected = expected_notice(policy, observed, current_year=year)
        if not observed:
            if expected:
                issues.append(f"Missing copyright notice '{expected}'")
            elif policy.canonical_notice:
                issues.append(f"Missing copyright notice '{policy.canonical_notice}'")
            else:
                issues.append("Missing copyright notice")
        elif expected and not _notices_equal(observed, expected):
            issues.append(
                f"Mismatched copyright notice. Found '{observed}' but expected '{expected}'.",
            )

    return issues


def _matches_snippet(lower_content: str, snippet: str | None) -> bool:
    if not snippet:
        return False
    return snippet.lower() in lower_content


def _notices_equal(left: str, right: str) -> bool:
    return normalise_notice(left) == normalise_notice(right)


def normalise_notice(value: str) -> str:
    stripped = _strip_comment_prefix(value)
    return re.sub(r"\s+", " ", stripped).strip().lower()


def extract_spdx_identifiers(content: str) -> set[str]:
    """Return SPDX identifiers found in comment lines within *content*."""
    identifiers: set[str] = set()
    for line in content.splitlines():
        payload = _comment_payload(line)
        if payload is None:
            stripped = line.lstrip()
            if not stripped.lower().startswith("spdx-license-identifier:"):
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
    stripped = line.lstrip()
    if not stripped:
        return None
    for prefix in ("#", "//", "/*", "*", "--", ";", "<!--", ".."):
        if stripped.startswith(prefix):
            payload = stripped[len(prefix) :].lstrip()
            if prefix == "<!--" and payload.endswith("-->"):
                payload = payload[:-3].rstrip()
            if prefix == "/*" and payload.endswith("*/"):
                payload = payload[:-2].rstrip()
            return payload
    return None


@dataclass(frozen=True)
class _NoticeParts:
    start: int | None
    end: int | None
    owner: str | None


def expected_notice(
    policy: LicensePolicy,
    observed_notice: str | None,
    *,
    current_year: int | None = None,
) -> str | None:
    """Build the canonical notice string expected for a file under *policy*."""
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
    if start_candidates:
        start_year = min(start_candidates)
    else:
        start_year = year

    end_candidates = [value for value in (observed.end, baseline.end) if value]
    end_year = max(end_candidates) if end_candidates else None
    if end_year is not None and end_year < start_year:
        end_year = start_year

    latest = max(filter(None, (end_year, year)), default=year)
    latest = max(latest, start_year)

    if latest == start_year:
        year_expression = f"{start_year}"
    else:
        year_expression = f"{start_year}-{latest}"

    return f"Copyright (c) {year_expression} {owner}".strip()


def _parse_notice(value: str | None) -> _NoticeParts:
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
    year_match = re.search(r"(\d{4}(?:\s*[-–]\s*\d{4}|\s*\+?|\s*present)?)", notice)
    if year_match:
        return year_match.group(1).replace("  ", " ").strip()
    return None


def _extract_license_overrides(data: Mapping[str, object]) -> Mapping[str, object]:
    tool = data.get("tool")
    if isinstance(tool, Mapping):
        pyqa = tool.get("pyqa")
        if isinstance(pyqa, Mapping):
            license_cfg = pyqa.get("license")
            if isinstance(license_cfg, Mapping):
                return dict(license_cfg)
    return {}


def _coerce_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    raise ValueError("Expected string value")


def _coerce_str_list(value: object) -> Sequence[str]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("Expected string in list")
            item = item.strip()
            if item:
                result.append(item)
        return tuple(result)
    raise ValueError("Expected list of strings")


def _strip_comment_prefix(line: str) -> str:
    cleaned = line.lstrip()
    patterns = ("#", "//", "/*", "*", "--", ";", "<!--")
    for token in patterns:
        if cleaned.startswith(token):
            cleaned = cleaned[len(token) :].lstrip(" -*#/")
            break
    if cleaned.startswith('"') and ":" in cleaned:
        _, remainder = cleaned.split(":", 1)
        cleaned = remainder.strip()
        if cleaned.endswith(","):
            cleaned = cleaned[:-1].rstrip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
    if cleaned.endswith("*/"):
        cleaned = cleaned[:-2].rstrip()
    if cleaned.endswith("-->"):
        cleaned = cleaned[:-3].rstrip()
    return cleaned.strip()


def _license_config_to_mapping(config: LicenseConfig) -> dict[str, object]:
    payload = config.model_dump(mode="python")
    # Drop keys with falsy values to reduce noise when merging defaults
    return {key: value for key, value in payload.items() if value not in (None, [], "")}
