# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Utilities for installing py-qa git hooks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .logging import info, ok, warn

HOOK_NAMES = ("pre-commit", "pre-push", "commit-msg")


@dataclass
class InstallResult:
    installed: list[Path]
    skipped: list[Path]
    backups: list[Path]


def install_hooks(
    root: Path,
    *,
    hooks_dir: Path | None = None,
    dry_run: bool = False,
) -> InstallResult:
    """Install git hooks by symlinking py-qa templates into ``.git/hooks``."""

    project_root = root.resolve()
    git_dir = project_root / ".git"
    if not git_dir.exists():
        raise FileNotFoundError("Not a git repository (missing .git directory)")

    target_dir = hooks_dir or git_dir / "hooks"
    target_dir.mkdir(parents=True, exist_ok=True)

    template_dir = project_root / "py-qa" / "hooks"
    if not template_dir.exists():
        raise FileNotFoundError(f"Hook templates not found: {template_dir}")

    installed: list[Path] = []
    skipped: list[Path] = []
    backups: list[Path] = []

    for name in HOOK_NAMES:
        template = template_dir / name
        if not template.exists():
            warn(f"Template for {name} not found at {template}", use_emoji=True)
            skipped.append(template)
            continue

        destination = target_dir / name
        backup_path: Path | None = None

        if destination.exists() and not destination.is_symlink():
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_path = destination.with_suffix(destination.suffix + f".backup.{timestamp}")
            info(f"Backing up existing {name} hook to {backup_path}", use_emoji=True)
            if not dry_run:
                destination.rename(backup_path)
            backups.append(backup_path)

        info(f"Installing {name} hook", use_emoji=True)
        if dry_run:
            installed.append(destination)
            continue

        if destination.exists() or destination.is_symlink():
            destination.unlink()

        destination.symlink_to(template)
        destination.chmod(0o755)
        installed.append(destination)

    if dry_run:
        ok(f"Dry run complete: would install {len(installed)} hooks", use_emoji=True)
    else:
        ok(f"Installed {len(installed)} hooks", use_emoji=True)
    return InstallResult(installed=installed, skipped=skipped, backups=backups)


__all__ = ["install_hooks", "InstallResult", "HOOK_NAMES"]
