# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Execution utilities for installing project git hooks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pyqa.core.logging import info, ok, warn

from .models import InstallResult
from .registry import normalise_hook_order


@dataclass(frozen=True, slots=True)
class HookDirectories:
    """Describe filesystem locations used during hook installation."""

    project_root: Path
    git_dir: Path
    target_dir: Path
    template_dir: Path


@dataclass(slots=True)
class HookOperationOutcome:
    """Accumulate filesystem paths affected by a single hook installation."""

    installed: list[Path]
    skipped: list[Path]
    backups: list[Path]


def install_hooks(
    root: Path,
    *,
    hooks_dir: Path | None = None,
    hooks: Iterable[str] | None = None,
    dry_run: bool = False,
) -> InstallResult:
    """Install git hooks by symlinking templates into ``.git/hooks``.

    Args:
        root: Repository root whose hooks should be installed.
        hooks_dir: Optional override for the target hooks directory.
        hooks: Optional iterable restricting the hook names to install.
        dry_run: When ``True`` avoid filesystem mutations while reporting actions.

    Returns:
        InstallResult: Aggregated record of installed, skipped, and backed-up hooks.

    Raises:
        FileNotFoundError: Raised when the repository lacks required directories.
    """

    directories = _prepare_directories(root, hooks_dir)

    hook_names = normalise_hook_order(hooks)
    result = InstallResult(installed=[], skipped=[], backups=[])

    for name in hook_names:
        outcome = _install_single_hook(name=name, directories=directories, dry_run=dry_run)
        result.installed.extend(outcome.installed)
        result.skipped.extend(outcome.skipped)
        result.backups.extend(outcome.backups)

    if dry_run:
        ok(f"Dry run complete: would install {len(result.installed)} hooks", use_emoji=True)
    else:
        ok(f"Installed {len(result.installed)} hooks", use_emoji=True)
    return result


def _prepare_directories(root: Path, hooks_dir: Path | None) -> HookDirectories:
    """Return validated directories required for hook installation.

    Args:
        root: Repository root directory.
        hooks_dir: Optional target directory for installed hooks.

    Returns:
        HookDirectories: Validated directories referencing project, git, target, and templates.

    Raises:
        FileNotFoundError: Raised when required directories are missing.
    """

    project_root = root.resolve()
    git_dir = project_root / ".git"
    if not git_dir.exists():
        raise FileNotFoundError("Not a git repository (missing .git directory)")

    target_dir = hooks_dir or git_dir / "hooks"
    target_dir.mkdir(parents=True, exist_ok=True)

    template_dir = project_root / "py-qa" / "hooks"
    if not template_dir.exists():
        raise FileNotFoundError(f"Hook templates not found: {template_dir}")

    return HookDirectories(
        project_root=project_root,
        git_dir=git_dir,
        target_dir=target_dir,
        template_dir=template_dir,
    )


def _install_single_hook(
    *,
    name: str,
    directories: HookDirectories,
    dry_run: bool,
) -> HookOperationOutcome:
    """Install a single git hook based on the provided directories.

    Args:
        name: Hook name being installed.
        directories: Prepared directories used for template lookup and installation.
        dry_run: When ``True`` avoid performing filesystem mutations.

    Returns:
        HookOperationOutcome: Paths that were installed, skipped, or backed up.
    """

    template = directories.template_dir / name
    outcome = HookOperationOutcome(installed=[], skipped=[], backups=[])

    if not template.exists():
        warn(f"Template for {name} not found at {template}", use_emoji=True)
        outcome.skipped.append(template)
        return outcome

    destination = directories.target_dir / name
    backup_path: Path | None = None

    if destination.exists() and not destination.is_symlink():
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = destination.with_suffix(destination.suffix + f".backup.{timestamp}")
        info(f"Backing up existing {name} hook to {backup_path}", use_emoji=True)
        if not dry_run:
            destination.rename(backup_path)
        outcome.backups.append(backup_path)

    info(f"Installing {name} hook", use_emoji=True)
    if dry_run:
        outcome.installed.append(destination)
        return outcome

    if destination.exists() or destination.is_symlink():
        destination.unlink()

    destination.symlink_to(template)
    destination.chmod(0o755)
    outcome.installed.append(destination)
    return outcome


__all__ = ["install_hooks"]
