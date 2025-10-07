# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for capturing and comparing tool versions."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from packaging.version import InvalidVersion, Version

from pyqa.core.runtime.process import SubprocessExecutionError, run_command


class VersionResolver:
    """Capture and compare tool versions using standardized semantics."""

    VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)+)")

    def capture(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> str | None:
        """Return the normalized version string from ``command`` if available."""
        try:
            completed = run_command(
                list(command),
                capture_output=True,
                env=env,
            )
        except (OSError, ValueError, SubprocessExecutionError):
            return None
        output = completed.stdout.strip() or completed.stderr.strip()
        if not output:
            return None
        first_line = output.splitlines()[0].strip()
        return self.normalize(first_line)

    def normalize(self, raw: str | None) -> str | None:
        """Return a normalized semantic version extracted from ``raw``."""
        if not raw:
            return None
        match = self.VERSION_PATTERN.search(raw)
        candidate = match.group(1) if match else raw.strip()
        try:
            Version(candidate)
        except InvalidVersion:
            return None
        return candidate

    def is_compatible(self, actual: str | None, expected: str | None) -> bool:
        """Return ``True`` when ``actual`` satisfies the ``expected`` minimum."""
        if expected is None:
            return True
        if actual is None:
            return False
        try:
            return Version(actual) >= Version(expected)
        except InvalidVersion:
            return False


__all__ = ["VersionResolver"]
