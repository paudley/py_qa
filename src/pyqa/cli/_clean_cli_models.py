# SPDX-License-Identifier: MIT
"""Shared data structures for the sparkly-clean CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


def normalize_cli_values(values: Sequence[str] | None) -> tuple[str, ...]:
    """Return sanitized CLI values.

    Args:
        values: Raw values passed from Typer when options are repeated. Typer
            yields ``None`` when the option is not provided, otherwise a
            sequence including potential blank strings.

    Returns:
        A tuple containing only the non-empty values while preserving the
        original order provided by the CLI.
    """

    if not values:
        return ()
    return tuple(entry for entry in values if entry)


@dataclass(slots=True)
class CleanCLIOptions:
    """Capture CLI overrides supplied to the sparkly-clean command.

    Attributes:
        extra_patterns: Additional glob patterns requested by the user.
        extra_trees: Directory prefixes that should be removed recursively.
        dry_run: Flag indicating the command should only log planned actions.
        emoji: Flag indicating whether emoji output should be enabled.
    """

    extra_patterns: tuple[str, ...]
    extra_trees: tuple[str, ...]
    dry_run: bool
    emoji: bool

    @classmethod
    def from_cli(
        cls,
        patterns: Sequence[str] | None,
        trees: Sequence[str] | None,
        *,
        dry_run: bool,
        emoji: bool,
    ) -> CleanCLIOptions:
        """Return options parsed from CLI arguments.

        Args:
            patterns: Optional tuple of additional glob patterns supplied on
                the command line.
            trees: Optional tuple of directory paths to clean recursively.
            dry_run: Indicates whether the clean command should run in
                inspection-only mode.
            emoji: Indicates whether emoji output should be rendered.

        Returns:
            A fully populated ``CleanCLIOptions`` instance ready for
            consumption by the orchestration layer.
        """

        return cls(
            extra_patterns=normalize_cli_values(patterns),
            extra_trees=normalize_cli_values(trees),
            dry_run=dry_run,
            emoji=emoji,
        )


__all__ = ["CleanCLIOptions", "normalize_cli_values"]
