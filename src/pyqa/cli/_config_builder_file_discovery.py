# SPDX-License-Identifier: MIT
"""Helpers for composing file discovery overrides from CLI options."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TypedDict

from ..config import FileDiscoveryConfig
from ..config_utils import _existing_unique_paths as shared_existing_unique_paths
from ..config_utils import _unique_paths as shared_unique_paths
from ._config_builder_constants import DEFAULT_EXCLUDES, LintOptionKey
from ._config_builder_shared import (
    ensure_abs,
    is_within_any,
    model_clone,
    select_flag,
    select_value,
)
from .options import LintGitOptions, LintOptions, LintTargetOptions


class FileDiscoveryOverrides(TypedDict):
    """Mapping of file discovery override fields."""

    roots: tuple[Path, ...]
    excludes: tuple[Path, ...]
    explicit_files: tuple[Path, ...]
    boundaries: tuple[Path, ...]
    paths_from_stdin: bool
    changed_only: bool
    diff_ref: str | None
    include_untracked: bool
    base_branch: str | None


def apply_file_discovery_overrides(
    current: FileDiscoveryConfig,
    overrides: FileDiscoveryOverrides,
) -> FileDiscoveryConfig:
    """Return ``current`` updated with the supplied override mapping."""

    return model_clone(
        current,
        roots=list(overrides["roots"]),
        excludes=list(overrides["excludes"]),
        explicit_files=list(overrides["explicit_files"]),
        limit_to=list(overrides["boundaries"]),
        paths_from_stdin=overrides["paths_from_stdin"],
        changed_only=overrides["changed_only"],
        diff_ref=overrides["diff_ref"],
        include_untracked=overrides["include_untracked"],
        base_branch=overrides["base_branch"],
    )


def collect_file_discovery_overrides(
    current: FileDiscoveryConfig,
    options: LintOptions,
    project_root: Path,
) -> FileDiscoveryOverrides:
    """Return the file discovery overrides derived from CLI inputs.

    Args:
        current: Existing file discovery configuration prior to overrides.
        options: Composed CLI options bundle derived from user arguments.
        project_root: Resolved project root used for relative path handling.

    Returns:
        FileDiscoveryOverrides: Mapping of normalized overrides covering roots,
        explicit paths, and git-discovery toggles.
    """

    provided = options.provided
    target_options = options.target_options
    git_options = options.git_options

    roots: list[Path] = resolve_roots(
        current,
        project_root,
        target_options,
        provided,
    )
    explicit_files, boundaries = resolve_explicit_files(
        current,
        target_options,
        project_root,
        roots,
        provided,
    )
    excludes = resolve_excludes(
        current,
        project_root,
        target_options,
        git_options,
        provided,
    )

    overrides: FileDiscoveryOverrides = {
        "roots": tuple(shared_unique_paths(roots)),
        "excludes": tuple(shared_unique_paths(excludes)),
        "explicit_files": tuple(shared_existing_unique_paths(explicit_files)),
        "boundaries": tuple(shared_unique_paths(boundaries)),
        "paths_from_stdin": select_flag(
            target_options.paths_from_stdin,
            current.paths_from_stdin,
            LintOptionKey.PATHS_FROM_STDIN,
            provided,
        ),
        "changed_only": select_flag(
            git_options.changed_only,
            current.changed_only,
            LintOptionKey.CHANGED_ONLY,
            provided,
        ),
        "diff_ref": select_value(
            git_options.diff_ref,
            current.diff_ref,
            LintOptionKey.DIFF_REF,
            provided,
        ),
        "include_untracked": select_flag(
            git_options.include_untracked,
            current.include_untracked,
            LintOptionKey.INCLUDE_UNTRACKED,
            provided,
        ),
        "base_branch": select_value(
            git_options.base_branch,
            current.base_branch,
            LintOptionKey.BASE_BRANCH,
            provided,
        ),
    }
    return overrides


def resolve_roots(
    current: FileDiscoveryConfig,
    project_root: Path,
    target_options: LintTargetOptions,
    provided_flags: frozenset[str],
) -> list[Path]:
    """Resolve the root directories that should be scanned for files.

    Args:
        current: Baseline discovery configuration sourced from config files.
        project_root: Repository root used for normalizing relative entries.
        target_options: CLI-supplied filesystem target overrides.
        provided_flags: CLI flag names explicitly provided by the user.

    Returns:
        list[Path]: Ordered list of discovery roots deduplicated by path.
    """

    roots = shared_unique_paths(ensure_abs(project_root, path) for path in current.roots)
    if project_root not in roots:
        roots.insert(0, project_root)

    if LintOptionKey.DIRS.value in provided_flags:
        resolved_dirs = (
            directory if directory.is_absolute() else (project_root / directory) for directory in target_options.dirs
        )
        roots.extend(path.resolve() for path in resolved_dirs)

    normalized_roots: list[Path] = shared_unique_paths(roots)
    return normalized_roots


def resolve_explicit_files(
    current: FileDiscoveryConfig,
    target_options: LintTargetOptions,
    project_root: Path,
    roots: list[Path],
    provided_flags: frozenset[str],
) -> tuple[list[Path], list[Path]]:
    """Resolve explicit file selections and derived discovery boundaries.

    Args:
        current: Baseline discovery configuration sourced from config files.
        target_options: CLI-supplied filesystem target overrides.
        project_root: Repository root used for normalizing relative entries.
        roots: Mutable list of discovery roots that may be expanded.
        provided_flags: CLI flag names explicitly provided by the user.

    Returns:
        tuple[list[Path], list[Path]]: Normalized explicit files and derived
        directory boundaries that constrain discovery when applicable.
    """

    explicit_files: list[Path] = shared_existing_unique_paths(current.explicit_files)
    user_dirs: list[Path] = []
    user_files: list[Path] = []

    if LintOptionKey.PATHS.value in provided_flags:
        for raw_path in target_options.paths:
            resolved_path = (raw_path if raw_path.is_absolute() else project_root / raw_path).resolve()
            if resolved_path.is_dir():
                roots.append(resolved_path)
                user_dirs.append(resolved_path)
            else:
                user_files.append(resolved_path)
                if resolved_path not in explicit_files:
                    explicit_files.append(resolved_path)

    boundaries: list[Path] = shared_unique_paths(
        boundary for boundary in derive_boundaries(user_dirs, user_files) if boundary
    )
    if not boundaries:
        return explicit_files, []

    filtered_roots = _filter_roots_within_boundaries(roots, boundaries)
    filtered_files = [path for path in explicit_files if is_within_any(path, boundaries)]
    roots.clear()
    roots.extend(filtered_roots)
    return filtered_files, boundaries


def derive_boundaries(user_dirs: Sequence[Path], user_files: Sequence[Path]) -> Iterable[Path]:
    """Yield discovery boundaries derived from explicit user selections."""

    parents = [file_path.parent for file_path in user_files]
    for candidate in (*user_dirs, *parents):
        if candidate:
            yield candidate


def resolve_excludes(
    current: FileDiscoveryConfig,
    project_root: Path,
    target_options: LintTargetOptions,
    git_options: LintGitOptions,
    provided_flags: frozenset[str],
) -> list[Path]:
    """Resolve excluded paths by combining defaults, config, and CLI input.

    Args:
        current: Baseline discovery configuration sourced from config files.
        project_root: Repository root used for normalizing relative entries.
        target_options: CLI-supplied filesystem target overrides.
        git_options: CLI-supplied git discovery overrides.
        provided_flags: CLI flag names explicitly provided by the user.

    Returns:
        list[Path]: Deduplicated absolute paths excluded from discovery.
    """

    excludes: list[Path] = shared_unique_paths(path.resolve() for path in current.excludes)
    for default_path in DEFAULT_EXCLUDES:
        resolved = ensure_abs(project_root, default_path).resolve()
        if resolved not in excludes:
            excludes.append(resolved)
    if LintOptionKey.EXCLUDE.value in provided_flags:
        for path in target_options.exclude:
            resolved = ensure_abs(project_root, path).resolve()
            if resolved not in excludes:
                excludes.append(resolved)
    if git_options.no_lint_tests:
        tests_path = ensure_abs(project_root, Path("tests")).resolve()
        if tests_path not in excludes:
            excludes.append(tests_path)
    return excludes


def _filter_roots_within_boundaries(
    roots: Sequence[Path],
    boundaries: Sequence[Path],
) -> list[Path]:
    """Filter root directories so they reside within supplied boundaries."""

    matching = [path for path in roots if is_within_any(path, boundaries)]
    if matching:
        merged = list(matching)
        merged.extend(path for path in boundaries if path not in matching and path.is_dir())
        unique_paths: list[Path] = shared_unique_paths(merged)
        return unique_paths
    boundary_dirs = [path for path in boundaries if path.is_dir()]
    unique_boundaries: list[Path] = shared_unique_paths(boundary_dirs)
    return unique_boundaries


__all__ = [
    "FileDiscoveryOverrides",
    "apply_file_discovery_overrides",
    "collect_file_discovery_overrides",
    "resolve_roots",
    "resolve_explicit_files",
    "derive_boundaries",
    "resolve_excludes",
]
