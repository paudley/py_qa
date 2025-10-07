# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""spaCy-backed helpers used by pyqa analysis flows."""

from __future__ import annotations

from .loader import load_language
from .message_spans import build_spacy_spans, iter_signature_tokens

__all__ = [
    "build_spacy_spans",
    "iter_signature_tokens",
    "load_language",
]
