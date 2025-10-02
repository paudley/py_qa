# SPDX-License-Identifier: MIT
"""Data structures for the git hooks CLI command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

DEFAULT_HOOKS_DIR: Final[Path] = Path(".git/hooks")


@dataclass(slots=True)
class HookCLIOptions:
    """Capture CLI options for hook installation.

    Attributes:
        root: The repository root where hooks should be installed.
        hooks_dir: Optional override for the hooks directory. ``None`` implies
            the default directory returned by :data:`DEFAULT_HOOKS_DIR`.
        dry_run: Indicates whether the installation should avoid filesystem
            writes.
        emoji: Indicates whether emoji output should be rendered.
    """

    root: Path
    hooks_dir: Path | None
    dry_run: bool
    emoji: bool

    @classmethod
    def from_cli(
        cls,
        root: Path,
        hooks_dir: Path,
        *,
        dry_run: bool,
        emoji: bool,
    ) -> "HookCLIOptions":
        """Return options parsed from CLI arguments.

        Args:
            root: Repository root provided via the CLI.
            hooks_dir: Hooks directory override supplied via ``--hooks-dir``.
            dry_run: Whether to perform a dry-run installation.
            emoji: Whether to emit emoji in logging helpers.

        Returns:
            A ``HookCLIOptions`` instance with normalized paths.
        """

        resolved_root = root.resolve()
        override = hooks_dir if hooks_dir != DEFAULT_HOOKS_DIR else None
        return cls(
            root=resolved_root,
            hooks_dir=override.resolve() if override is not None else None,
            dry_run=dry_run,
            emoji=emoji,
        )


__all__ = ["DEFAULT_HOOKS_DIR", "HookCLIOptions"]
