# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Platform-specific heuristics (paths, languages, etc.)."""

from __future__ import annotations

from .constants import LANGUAGE_EXTENSIONS, LANGUAGE_FILENAMES, LANGUAGE_MARKERS
from .languages import detect_languages
from .paths import get_pyqa_root
from .workspace import is_py_qa_workspace

__all__ = [
    "LANGUAGE_EXTENSIONS",
    "LANGUAGE_FILENAMES",
    "LANGUAGE_MARKERS",
    "detect_languages",
    "get_pyqa_root",
    "is_py_qa_workspace",
]
