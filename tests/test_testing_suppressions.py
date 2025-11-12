# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests covering suppression utilities exposed by ``pyqa.testing``."""

from __future__ import annotations

import re

from pyqa.interfaces.internal_linting import INTERNAL_LINTER_TOOL_NAMES
from pyqa.testing import flatten_test_suppressions


def test_internal_linters_include_test_suppressions() -> None:
    """Ensure every internal linter emits a default suppression for test paths."""

    suppressions = flatten_test_suppressions()
    filtered = flatten_test_suppressions(("python",))
    for tool_name in INTERNAL_LINTER_TOOL_NAMES:
        expected = rf"^{re.escape(tool_name)}, (?:.+/)?tests?/.*$"
        patterns = suppressions.get(tool_name)
        assert patterns is not None, f"{tool_name} missing suppression list"
        assert expected in patterns, f"{tool_name} missing default test suppression"
        filtered_patterns = filtered.get(tool_name)
        assert filtered_patterns is not None, f"{tool_name} missing filtered suppression list"
        assert expected in filtered_patterns, f"{tool_name} missing filtered test suppression"
        assert len(patterns) == len(set(patterns)), f"{tool_name} suppression patterns duplicated"
