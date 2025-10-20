# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for capturing and comparing tool versions."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from packaging.version import InvalidVersion, Version

from pyqa.core.runtime.process import CommandOptions, SubprocessExecutionError, run_command


class VersionResolver:
    """Capture and compare tool versions using standardized semantics."""

    VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)+)")

    def capture(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> str | None:
        """Return the normalised version string produced by ``command`` when available.

        Args:
            command: Command sequence executed to report version information.
            env: Optional environment overrides supplied to the command invocation.

        Returns:
            str | None: Normalised version string when parsing succeeds, otherwise ``None``.
        """
        try:
            completed = run_command(
                list(command),
                options=CommandOptions(capture_output=True, env=env),
            )
        except (OSError, ValueError, SubprocessExecutionError):
            return None
        output = completed.stdout.strip() or completed.stderr.strip()
        if not output:
            return None
        first_line = output.splitlines()[0].strip()
        return self.normalize(first_line)

    def normalize(self, raw: str | None) -> str | None:
        """Return the normalised semantic version extracted from ``raw``.

        Args:
            raw: Raw version text captured from tooling output.

        Returns:
            str | None: Semantic version string, or ``None`` if parsing fails.
        """
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
        """Return whether ``actual`` satisfies the ``expected`` minimum version.

        Args:
            actual: Actual version string captured from tooling output.
            expected: Minimum version string required for compatibility.

        Returns:
            bool: ``True`` when the actual version meets or exceeds the expectation.
        """
        if expected is None:
            return True
        if actual is None:
            return False
        try:
            return Version(actual) >= Version(expected)
        except InvalidVersion:
            return False


__all__ = ["VersionResolver"]
