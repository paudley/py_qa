# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Language detection utilities for selecting relevant toolchains."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .constants import LANGUAGE_EXTENSIONS, LANGUAGE_FILENAMES, LANGUAGE_MARKERS


def detect_languages(root: Path, files: Iterable[Path]) -> set[str]:
    """Infer languages present in *files* or by marker files under *root*."""

    root = root.resolve()
    languages: set[str] = set()
    for language, markers in LANGUAGE_MARKERS.items():
        if any((root / marker).exists() for marker in markers):
            languages.add(language)
    for path in files:
        suffix = path.suffix.lower()
        for language, extensions in LANGUAGE_EXTENSIONS.items():
            if suffix in extensions:
                languages.add(language)
        name = path.name.lower()
        for language, names in LANGUAGE_FILENAMES.items():
            if name in names:
                languages.add(language)
    return languages


__all__ = ["detect_languages"]
