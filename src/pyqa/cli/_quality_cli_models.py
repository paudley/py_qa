# SPDX-License-Identifier: MIT
"""Data structures for the check-quality CLI workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Config


@dataclass(slots=True)
class QualityCLIOptions:
    """Capture CLI arguments for the main quality command.

    Attributes:
        root: Resolved project root for configuration discovery.
        raw_paths: Optional paths supplied by the caller.
        staged: Whether the run should consider only staged changes.
        fix: Whether the run should attempt automated fixes when possible.
        requested_checks: Optional subset of checks explicitly requested via
            ``--check`` flags.
        include_schema: Indicates whether schema validation remains enabled
            after considering ``--no-schema``.
        emoji: Indicates whether emoji should be rendered in output.
    """

    root: Path
    raw_paths: tuple[Path, ...]
    staged: bool
    fix: bool
    requested_checks: tuple[str, ...]
    include_schema: bool
    emoji: bool

    @classmethod
    def from_cli(
        cls,
        *,
        root: Path,
        paths: tuple[Path, ...],
        staged: bool,
        fix: bool,
        requested_checks: tuple[str, ...],
        include_schema: bool,
        emoji: bool,
    ) -> "QualityCLIOptions":
        """Return options parsed from Typer callback arguments.

        Args:
            root: Root path supplied by Typer.
            paths: Tuple of path arguments passed on the command line.
            staged: Indicates whether staged files should be preferred.
            fix: Indicates whether automatic fixes should be applied.
            requested_checks: Explicit subset of checks requested by the user.
            include_schema: Flag indicating whether schema validation remains
                enabled after accounting for ``--no-schema``.
            emoji: Flag controlling whether emoji output should be rendered.

        Returns:
            QualityCLIOptions: Normalized options with a resolved project root.
        """

        return cls(
            root=root.resolve(),
            raw_paths=paths,
            staged=staged,
            fix=fix,
            requested_checks=requested_checks,
            include_schema=include_schema,
            emoji=emoji,
        )


@dataclass(slots=True)
class QualityConfigContext:
    """Configuration and warnings used by quality CLI workflows."""

    root: Path
    config: Config
    options: QualityCLIOptions
    warnings: tuple[str, ...]


@dataclass(slots=True)
class QualityTargetResolution:
    """Resolved target paths for the quality CLI.

    Attributes:
        files: Optional explicit path list to hand over to the checker.
        ignored_py_qa: Ordered tuple of ignored paths residing under ``py_qa``.
        had_explicit_paths: Indicates whether the user provided explicit paths.
    """

    files: list[Path] | None
    ignored_py_qa: tuple[str, ...]
    had_explicit_paths: bool


__all__ = [
    "QualityCLIOptions",
    "QualityConfigContext",
    "QualityTargetResolution",
]
