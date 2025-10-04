# SPDX-License-Identifier: MIT
"""Data structures for the check-quality CLI workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from ..config import Config
from .shared import Depends

ROOT_OPTION = Annotated[
    Path,
    typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
]
PATHS_ARGUMENT = Annotated[
    list[Path] | None,
    typer.Argument(
        None,
        metavar="[PATHS...]",
        help="Optional file paths to scope the checks.",
    ),
]
STAGED_OPTION = Annotated[
    bool,
    typer.Option(
        False,
        "--staged/--no-staged",
        help=("Use staged files instead of discovering all tracked files when no PATHS are provided."),
    ),
]
FIX_OPTION = Annotated[
    bool,
    typer.Option(
        False,
        "--fix",
        help="Attempt to repair license notices and SPDX tags before re-running checks.",
        is_flag=True,
    ),
]
CHECK_OPTION = Annotated[
    list[str] | None,
    typer.Option(
        None,
        "--check",
        "-c",
        help="Limit execution to specific checks (e.g. license,file-size,schema,python).",
    ),
]
NO_SCHEMA_OPTION = Annotated[
    bool,
    typer.Option(False, "--no-schema", help="Skip schema validation."),
]
EMOJI_OPTION = Annotated[
    bool,
    typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji in output."),
]


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
    def from_cli(cls, params: QualityCLIInputParams) -> QualityCLIOptions:
        """Return options parsed from Typer callback arguments.

        Args:
            params: Structured CLI parameters collected from Typer dependencies.

        Returns:
            QualityCLIOptions: Normalized options with a resolved project root.
        """

        return cls(
            root=params.root.resolve(),
            raw_paths=params.paths,
            staged=params.staged,
            fix=params.fix,
            requested_checks=params.requested_checks,
            include_schema=params.include_schema,
            emoji=params.emoji,
        )


@dataclass(slots=True)
class QualityCLIInputParams:
    """Container for raw CLI arguments prior to normalisation."""

    root: Path
    paths: tuple[Path, ...]
    staged: bool
    fix: bool
    requested_checks: tuple[str, ...]
    include_schema: bool
    emoji: bool


@dataclass(slots=True)
class _QualityPathArgs:
    """Path-related CLI arguments collected from Typer."""

    root: Path
    paths: tuple[Path, ...]
    staged: bool


@dataclass(slots=True)
class _QualityFlagArgs:
    """Flag-based CLI arguments collected from Typer."""

    fix: bool
    requested_checks: tuple[str, ...]
    include_schema: bool
    emoji: bool


def _collect_quality_path_args(
    root: ROOT_OPTION,
    paths: PATHS_ARGUMENT,
    staged: STAGED_OPTION,
) -> _QualityPathArgs:
    """Return normalised path arguments used by the quality CLI."""

    normalized_paths = tuple(paths or [])
    return _QualityPathArgs(root=root, paths=normalized_paths, staged=staged)


def _collect_quality_flag_args(
    fix: FIX_OPTION,
    check: CHECK_OPTION,
    no_schema: NO_SCHEMA_OPTION,
    emoji: EMOJI_OPTION,
) -> _QualityFlagArgs:
    """Return normalised flag arguments used by the quality CLI."""

    requested_checks = tuple(check or [])
    return _QualityFlagArgs(
        fix=fix,
        requested_checks=requested_checks,
        include_schema=not no_schema,
        emoji=emoji,
    )


def _collect_quality_cli_params(
    path_args: Annotated[_QualityPathArgs, Depends(_collect_quality_path_args)],
    flag_args: Annotated[_QualityFlagArgs, Depends(_collect_quality_flag_args)],
) -> QualityCLIInputParams:
    """Collect raw CLI inputs before normalisation."""

    return QualityCLIInputParams(
        root=path_args.root,
        paths=path_args.paths,
        staged=path_args.staged,
        fix=flag_args.fix,
        requested_checks=flag_args.requested_checks,
        include_schema=flag_args.include_schema,
        emoji=flag_args.emoji,
    )


def build_quality_options(
    params: Annotated[QualityCLIInputParams, Depends(_collect_quality_cli_params)],
) -> QualityCLIOptions:
    """Construct ``QualityCLIOptions`` from Typer callback arguments."""

    return QualityCLIOptions.from_cli(params)


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
    "Depends",
    "ROOT_OPTION",
    "PATHS_ARGUMENT",
    "STAGED_OPTION",
    "FIX_OPTION",
    "CHECK_OPTION",
    "NO_SCHEMA_OPTION",
    "EMOJI_OPTION",
    "QualityCLIInputParams",
    "QualityCLIOptions",
    "QualityConfigContext",
    "QualityTargetResolution",
    "build_quality_options",
]
