# SPDX-License-Identifier: MIT
"""Helpers for capturing and comparing tool versions."""

from __future__ import annotations

import re
from subprocess import CalledProcessError
from typing import Mapping, Sequence

from packaging.version import InvalidVersion, Version

from ..subprocess_utils import run_command


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
                env=dict(env) if env else None,
            )
        except (OSError, ValueError, CalledProcessError):
            return None
        output = completed.stdout.strip() or completed.stderr.strip()
        if not output:
            return None
        first_line = output.splitlines()[0].strip()
        return self.normalize(first_line)

    def normalize(self, raw: str | None) -> str | None:
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
        if expected is None:
            return True
        if actual is None:
            return False
        try:
            return Version(actual) >= Version(expected)
        except InvalidVersion:
            return False


__all__ = ["VersionResolver"]
