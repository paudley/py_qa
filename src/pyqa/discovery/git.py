# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Git-based discovery strategy."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path

from ..core.runtime.process import CommandOptions, run_command
from ..interfaces.discovery import FileDiscoveryConfig
from .base import DiscoveryStrategy, is_within_limits, resolve_limit_paths

GitRunner = Callable[[Sequence[str], Path], list[str]]


class GitDiscovery(DiscoveryStrategy):
    """Collect files reported as changed by Git."""

    def __init__(self, *, runner: GitRunner | None = None) -> None:
        """Create a Git discovery strategy.

        Args:
            runner: Optional command runner used to execute git commands. A
                sensible default based on :func:`run_command` is used when
                omitted.
        """

        self._runner = runner or self._default_runner

    @property
    def identifier(self) -> str:
        """Return the identifier for the git discovery strategy.

        Returns:
            str: Human-readable identifier associated with git discovery.
        """

        return "git"

    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Return files discovered via git status/diff output.

        Args:
            config: Discovery configuration controlling git flags.
            root: Repository root directory.

        Returns:
            Iterable[Path]: Sorted sequence of resolved candidate paths.
        """

        limits = tuple(resolve_limit_paths(config.limit_to, root))
        if not (config.changed_only or config.pre_commit or config.base_branch):
            return []
        candidates: set[Path] = set()
        diff_targets = list(self._diff_names(config, root))
        candidates.update(diff_targets)
        if config.include_untracked:
            candidates.update(self._untracked(root))
        bounded: set[Path] = set()
        for candidate in candidates:
            if not candidate.exists():
                continue
            resolved = candidate.resolve()
            if is_within_limits(resolved, limits):
                bounded.add(resolved)
        return sorted(bounded)

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Delegate to :meth:`discover` to support callable semantics.

        Args:
            config: Discovery configuration supplied by the caller.
            root: Repository root used to resolve relative paths.

        Returns:
            Iterable[Path]: Candidate paths returned by :meth:`discover`.
        """

        return self.discover(config, root)

    def _diff_names(self, config: FileDiscoveryConfig, root: Path) -> Iterator[Path]:
        """Yield files referenced by git diff or status output.

        Args:
            config: Discovery configuration controlling diff behaviour.
            root: Repository root directory.

        Returns:
            Iterator[Path]: Iterator yielding resolved diff candidates.

        Yields:
            Path: Resolved candidate files reported by git.
        """

        if config.pre_commit:
            cmd = ["git", "diff", "--name-only", "--cached"]
        else:
            diff_ref = self._resolve_diff_ref(config, root)
            cmd = ["git", "diff", "--name-only", diff_ref, "--"] if diff_ref else ["git", "status", "--short"]
            if not diff_ref:
                for raw in self._runner(cmd, root):
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    path_fragment = stripped.split(maxsplit=1)[-1]
                    yield (root / path_fragment).resolve()
                return
        for raw in self._runner(cmd, root):
            stripped = raw.strip()
            if not stripped:
                continue
            yield (root / stripped).resolve()

    def _untracked(self, root: Path) -> Iterator[Path]:
        """Yield untracked files from git ls-files output.

        Args:
            root: Repository root directory.

        Returns:
            Iterator[Path]: Iterator yielding resolved untracked file paths.

        Yields:
            Path: Resolved untracked file paths.
        """

        cmd = ["git", "ls-files", "--others", "--exclude-standard"]
        for raw in self._runner(cmd, root):
            stripped = raw.strip()
            if not stripped:
                continue
            yield (root / stripped).resolve()

    def _resolve_diff_ref(self, config: FileDiscoveryConfig, root: Path) -> str | None:
        """Return the git reference to diff against based on ``config``.

        Args:
            config: Discovery configuration specifying diff behaviour.
            root: Repository root directory.

        Returns:
            str | None: Git reference to diff against, or ``None`` when status
                output should be used.
        """

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
        """Execute ``cmd`` returning stdout lines while swallowing failures.

        Args:
            cmd: Git command to execute.
            root: Repository root directory.

        Returns:
            list[str]: Raw stdout lines produced by subprocess execution.
        """

        cp = run_command(cmd, options=CommandOptions(cwd=root, capture_output=True, text=True, check=False))
        if cp.returncode != 0:
            return []
        return (cp.stdout or "").splitlines()


def list_tracked_files(root: Path) -> list[Path]:
    """Return tracked files for the git repository rooted at ``root``.

    Args:
        root: Repository root directory.

    Returns:
        list[Path]: Resolved, tracked file paths.
    """
    cp = run_command(["git", "ls-files"], options=CommandOptions(cwd=root, capture_output=True, text=True, check=False))
    if cp.returncode != 0:
        return []
    files: list[Path] = []
    for line in cp.stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        files.append((root / candidate).resolve())
    return files
