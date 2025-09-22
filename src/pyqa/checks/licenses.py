# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""License and copyright verification utilities."""

from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Mapping, Optional, Sequence

from ..config import LicenseConfig
from ..constants import ALWAYS_EXCLUDE_DIRS

KNOWN_LICENSE_SNIPPETS: Mapping[str, str] = {
    "MIT": "Permission is hereby granted, free of charge",
    "Apache-2.0": "Licensed under the Apache License, Version 2.0",
    "BSD-3-Clause": "Redistribution and use in source and binary forms",
}


_COPYRIGHT_PATTERN = re.compile(r"copyright\s*\(c\)\s*(?P<body>.+)", re.IGNORECASE)


@dataclass
class LicenseMetadata:
    spdx_id: Optional[str]
    copyright_notice: Optional[str]
    license_text: Optional[str]
    overrides: Mapping[str, object]


@dataclass(slots=True)
class LicensePolicy:
    """Derived enforcement rules for repository licensing."""

    spdx_id: Optional[str]
    canonical_notice: Optional[str]
    license_snippet: Optional[str]
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

    def match_notice(self, content: str) -> Optional[str]:
        for line in content.splitlines():
            match = _COPYRIGHT_PATTERN.search(line)
            if match:
                return _strip_comment_prefix(line.strip())
        return None


def load_project_license(root: Path) -> LicenseMetadata:
    """Attempt to load license metadata from pyproject.toml or fallback."""

    pyproject = root / "pyproject.toml"
    spdx_id: Optional[str] = None
    copyright_str: Optional[str] = None
    overrides: Mapping[str, object] = {}
    license_text: Optional[str] = None

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


def _extract_project_license(project: Mapping[str, object]) -> Optional[str]:
    license_field = project.get("license")
    if isinstance(license_field, str):
        return license_field.strip()
    if isinstance(license_field, Mapping):
        if "text" in license_field:
            return _infer_license_id(str(license_field["text"]))
        if "file" in license_field:
            return None  # to be extracted via file
    return None


def _extract_authors(project: Mapping[str, object]) -> Optional[str]:
    authors = project.get("authors")
    if isinstance(authors, list) and authors:
        first = authors[0]
        if isinstance(first, Mapping):
            name = first.get("name")
            if isinstance(name, str):
                return name
    return None


def _resolve_license_file(root: Path) -> Optional[Path]:
    for candidate in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        path = root / candidate
        if path.exists():
            return path
    return None


def _infer_license_id(text: str) -> Optional[str]:
    lower = text.lower()
    for spdx, snippet in KNOWN_LICENSE_SNIPPETS.items():
        if snippet.lower() in lower:
            return spdx
    return None


def _extract_license_copyright(text: str) -> Optional[str]:
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
) -> list[str]:
    """Return list of issues detected for *path* under the provided *policy*."""

    if policy.should_skip(path, root):
        return []

    issues: list[str] = []
    lower_content = content.lower()

    if policy.spdx_id and policy.require_spdx:
        tag = f"SPDX-License-Identifier: {policy.spdx_id}"
        if tag not in content:
            if not any(
                alt and f"SPDX-License-Identifier: {alt}" in content for alt in (policy.allow_alternate_spdx or ())
            ) and not _matches_snippet(lower_content, policy.license_snippet):
                issues.append(f"Missing SPDX license tag '{tag}'")

    if policy.require_notice and policy.canonical_notice:
        observed = policy.match_notice(content)
        if not observed:
            issues.append(f"Missing copyright notice '{policy.canonical_notice}'")
        elif not _notices_equal(observed, policy.canonical_notice):
            issues.append(f"Mismatched copyright notice. Found '{observed}' but expected '{policy.canonical_notice}'.")

    return issues


def _matches_snippet(lower_content: str, snippet: Optional[str]) -> bool:
    if not snippet:
        return False
    return snippet.lower() in lower_content


def _notices_equal(left: str, right: str) -> bool:
    return normalise_notice(left) == normalise_notice(right)


def normalise_notice(value: str) -> str:
    stripped = _strip_comment_prefix(value)
    return re.sub(r"\s+", " ", stripped).strip().lower()


def _build_canonical_notice(config: Mapping[str, object], metadata: LicenseMetadata) -> Optional[str]:
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


def _extract_year(notice: str) -> Optional[str]:
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


def _coerce_optional_str(value: object) -> Optional[str]:
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
    if cleaned.endswith("*/"):
        cleaned = cleaned[:-2].rstrip()
    if cleaned.endswith("-->"):
        cleaned = cleaned[:-3].rstrip()
    return cleaned.strip()


def _license_config_to_mapping(config: LicenseConfig) -> dict[str, object]:
    payload = asdict(config)
    # Drop keys with falsy values to reduce noise when merging defaults
    return {key: value for key, value in payload.items() if value not in (None, [], "")}
