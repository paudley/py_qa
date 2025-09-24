# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Git-based discovery strategy."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

from ..config import FileDiscoveryConfig
from ..execution.worker import run_command
from .base import DiscoveryStrategy

GitRunner = Callable[[Sequence[str], Path], list[str]]


class GitDiscovery(DiscoveryStrategy):
    """Collect files reported as changed by Git."""

    def __init__(
        self, *, runner: Callable[[Sequence[str], Path], list[str]] | None = None
    ) -> None:
        self._runner = runner or self._default_runner

    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        limits = self._normalise_limits(config, root)
        if not (config.changed_only or config.pre_commit or config.base_branch):
            return []
        candidates: set[Path] = set()
        diff_targets = list(self._diff_names(config, root))
        candidates.update(diff_targets)
        if config.include_untracked:
            candidates.update(self._untracked(root))
        bounded = {
            path.resolve()
            for path in candidates
            if path.exists() and self._within_limits(path, limits)
        }
        return sorted(bounded)

    def _diff_names(self, config: FileDiscoveryConfig, root: Path) -> Iterator[Path]:
        if config.pre_commit:
            cmd = ["git", "diff", "--name-only", "--cached"]
        else:
            diff_ref = self._resolve_diff_ref(config, root)
            cmd = (
                ["git", "diff", "--name-only", diff_ref, "--"]
                if diff_ref
                else ["git", "status", "--short"]
            )
            if not diff_ref:
                for line in self._runner(cmd, root):
                    line = line.strip()
                    if not line:
                        continue
                    yield (root / line.split(maxsplit=1)[-1]).resolve()
                return
        for line in self._runner(cmd, root):
            line = line.strip()
            if not line:
                continue
            yield (root / line).resolve()

    def _untracked(self, root: Path) -> Iterator[Path]:
        cmd = ["git", "ls-files", "--others", "--exclude-standard"]
        for line in self._runner(cmd, root):
            line = line.strip()
            if not line:
                continue
            yield (root / line).resolve()

    def _resolve_diff_ref(self, config: FileDiscoveryConfig, root: Path) -> str | None:
        if config.base_branch:
            merge_base_cmd = ["git", "merge-base", "HEAD", config.base_branch]
            output = self._runner(merge_base_cmd, root)
            if output:
                return output[0].strip()
            return config.base_branch
        if config.diff_ref:
            return config.diff_ref
        return None

    @staticmethod
    def _default_runner(cmd: Sequence[str], root: Path) -> list[str]:
        cp = run_command(cmd, cwd=root)
        if cp.returncode != 0:
            return []
        return cp.stdout.splitlines()

    @staticmethod
    def _normalise_limits(config: FileDiscoveryConfig, root: Path) -> list[Path]:
        limits: list[Path] = []
        for entry in config.limit_to:
            candidate = entry if entry.is_absolute() else root / entry
            resolved = candidate.resolve()
            if resolved not in limits:
                limits.append(resolved)
        return limits

    @staticmethod
    def _within_limits(candidate: Path, limits: list[Path]) -> bool:
        if not limits:
            return True
        for limit in limits:
            try:
                candidate.relative_to(limit)
                return True
            except ValueError:
                continue
        return False


def list_tracked_files(root: Path) -> list[Path]:
    """Return all tracked files for the repository rooted at *root*."""

    cp = run_command(["git", "ls-files"], cwd=root)
    if cp.returncode != 0:
        return []
    files: list[Path] = []
    for line in cp.stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        files.append((root / candidate).resolve())
    return files
