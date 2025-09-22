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
        if not (config.changed_only or config.pre_commit or config.base_branch):
            return []
        candidates: set[Path] = set()
        diff_targets = list(self._diff_names(config, root))
        candidates.update(diff_targets)
        if config.include_untracked:
            candidates.update(self._untracked(root))
        return sorted({path.resolve() for path in candidates if path.exists()})

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
