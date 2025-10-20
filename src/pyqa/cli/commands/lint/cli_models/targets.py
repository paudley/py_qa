# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Filesystem and git discovery dependencies for lint CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ....core.shared import Depends
from ..params import (
    LintGitParams,
    LintPathParams,
    LintPathToggles,
)
from .constants import RootOption


def _path_toggles_dependency(
    paths_from_stdin: Annotated[
        bool,
        typer.Option(False, help="Read file paths from stdin."),
    ],
    include_dotfiles: Annotated[
        bool,
        typer.Option(False, "--dotfiles", help="Include dotfiles and dot directories during discovery."),
    ],
) -> LintPathToggles:
    """Return discovery toggles controlling path ingestion sources.

    Args:
        paths_from_stdin: Flag indicating whether paths originate from stdin.
        include_dotfiles: Whether dotfiles and dot directories should be included.

    Returns:
        LintPathToggles: Structured toggle values for path discovery.
    """

    return LintPathToggles(
        paths_from_stdin=paths_from_stdin,
        include_dotfiles=include_dotfiles,
    )


def _path_params_dependency(
    paths: Annotated[
        list[Path] | None,
        typer.Argument(None, metavar="[PATH]", help="Specific files or directories to lint."),
    ],
    root: RootOption,
    toggles: Annotated[LintPathToggles, Depends(_path_toggles_dependency)],
    dirs: Annotated[list[Path], typer.Option([], "--dir", help="Add directory to discovery roots (repeatable).")],
    exclude: Annotated[list[Path], typer.Option([], help="Exclude specific paths or globs.")],
) -> LintPathParams:
    """Return normalised filesystem parameters derived from CLI input.

    Args:
        paths: Optional positional path arguments.
        root: Repository root option supplied via CLI.
        toggles: Discovery toggles controlling stdin ingestion and dotfiles.
        dirs: Additional directory discovery roots.
        exclude: Explicit paths or globs to exclude from discovery.

    Returns:
        LintPathParams: Structured path parameters consumed by lint options.
    """

    return LintPathParams(
        paths=list(paths or []),
        root=root,
        paths_from_stdin=toggles.paths_from_stdin,
        dirs=list(dirs),
        exclude=list(exclude),
        include_dotfiles=toggles.include_dotfiles,
    )


def _git_params_dependency(
    changed_only: Annotated[bool, typer.Option(False, help="Limit to files changed according to git.")],
    diff_ref: Annotated[str, typer.Option("HEAD", help="Git ref for change detection.")],
    include_untracked: Annotated[bool, typer.Option(True, help="Include untracked files during git discovery.")],
    base_branch: Annotated[str | None, typer.Option(None, help="Base branch for merge-base diffing.")],
    no_lint_tests: Annotated[
        bool,
        typer.Option(False, "--no-lint-tests", help="Exclude paths containing 'tests' from linting."),
    ],
) -> LintGitParams:
    """Return git-related discovery parameters derived from CLI input.

    Args:
        changed_only: Whether to limit discovery to changed files.
        diff_ref: Git reference used for change detection.
        include_untracked: Whether to include untracked files.
        base_branch: Base branch used to compute merge-base diffs.
        no_lint_tests: Flag indicating whether test directories are excluded.

    Returns:
        LintGitParams: Structured git discovery parameters.
    """

    return LintGitParams(
        changed_only=changed_only,
        diff_ref=diff_ref,
        include_untracked=include_untracked,
        base_branch=base_branch,
        no_lint_tests=no_lint_tests,
    )


__all__ = [
    "PathArgument",
    "RootOption",
    "_git_params_dependency",
    "_path_params_dependency",
    "_path_toggles_dependency",
]
PathArgument = Annotated[
    list[Path] | None,
    typer.Argument(None, metavar="[PATH]", help="Specific files or directories to lint."),
]
