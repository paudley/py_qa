# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Ensure the default spaCy model is available via autodownload."""

from __future__ import annotations

import pytest

from pyqa.analysis.spacy.loader import load_language


def test_autoloads_spacy_model() -> None:
    """Fail loudly when the default spaCy model cannot be loaded."""

    language = load_language("en_core_web_sm")
    if language is None:
        pytest.fail(
            "spaCy model 'en_core_web_sm' unavailable. "
            "The autodownload routine must succeed so run "
            "`uv run python -m spacy download en_core_web_sm` and retry.",
        )

    doc = language("PyQA keeps docstrings healthy.")
    assert len(doc) >= 2
