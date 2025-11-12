# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Ensure the default spaCy model is available via autodownload."""

from __future__ import annotations

import importlib
import sys

import pytest

from pyqa.analysis.spacy import loader as spacy_loader


def test_autoloads_spacy_model() -> None:
    """Fail loudly when the default spaCy model cannot be loaded."""

    previous_spacy = sys.modules.pop("spacy", None)
    spacy_loader._STATE.language_cache.clear()
    spacy_loader._STATE.loader = spacy_loader._SENTINEL
    try:
        importlib.invalidate_caches()
        language = spacy_loader.load_language("en_core_web_sm")
        if language is None:
            pytest.fail(
                "spaCy model 'en_core_web_sm' unavailable. "
                "The autodownload routine must succeed so run "
                "`uv run python -m spacy download en_core_web_sm` and retry.",
            )
        doc = language("PyQA keeps docstrings healthy.")
        assert len(doc) >= 2
    finally:
        if previous_spacy is not None:
            sys.modules["spacy"] = previous_spacy
        else:
            sys.modules.pop("spacy", None)
