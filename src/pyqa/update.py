# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Workspace dependency updater orchestrations."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .constants import ALWAYS_EXCLUDE_DIRS
from .logging import fail, info, ok, warn


class WorkspaceKind(str, Enum):
    PYTHON = "python"
    PNPM = "pnpm"
    YARN = "yarn"
    NPM = "npm"
    GO = "go"
    RUST = "rust"


CommandRunner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class Workspace:
    """A discovered workspace and its package manager metadata."""

    directory: Path
    kind: WorkspaceKind
    manifest: Path


@dataclass(slots=True)
class UpdateResult:
    """Summary of update execution."""

    successes: list[Workspace] = field(default_factory=list)
    failures: list[tuple[Workspace, str]] = field(default_factory=list)
    skipped: list[Workspace] = field(default_factory=list)

    def record_success(self, workspace: Workspace) -> None:
        self.successes.append(workspace)

    def record_failure(self, workspace: Workspace, message: str) -> None:
        self.failures.append((workspace, message))

    def record_skip(self, workspace: Workspace) -> None:
        self.skipped.append(workspace)

    def exit_code(self) -> int:
        return 1 if self.failures else 0


class WorkspaceDiscovery:
    """Discover workspaces for supported package managers."""

    _NODE_LOCKS = {
        WorkspaceKind.PNPM: "pnpm-lock.yaml",
        WorkspaceKind.YARN: "yarn.lock",
        WorkspaceKind.NPM: "package-lock.json",
    }

    def __init__(self, *, skip_patterns: Iterable[str] | None = None) -> None:
        default_patterns = {"pyreadstat", ".git/modules"}
        if skip_patterns:
            default_patterns.update(skip_patterns)
        self._skip_substrings = default_patterns

    def discover(self, root: Path) -> list[Workspace]:
        root = root.resolve()
        workspaces: list[Workspace] = []
        for dirpath, dirnames, filenames in os.walk(root):
            directory = Path(dirpath)
            if self._should_skip(directory, root):
                dirnames[:] = []
                continue
            manifests = self._manifests_for(directory, filenames)
            workspaces.extend(manifests)
        return sorted(workspaces, key=lambda ws: (ws.directory, ws.kind.value))

    def _should_skip(self, directory: Path, root: Path) -> bool:
        try:
            relative = directory.relative_to(root)
        except ValueError:
            relative = directory
        if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
            return True
        path_str = str(relative)
        return any(pattern in path_str for pattern in self._skip_substrings)

    def _manifests_for(self, directory: Path, filenames: list[str]) -> list[Workspace]:
        workspaces: list[Workspace] = []
        files = set(filenames)

        # Python workspace via pyproject.toml
        if "pyproject.toml" in files:
            workspaces.append(
                Workspace(directory=directory, kind=WorkspaceKind.PYTHON, manifest=directory / "pyproject.toml")
            )

        # Node workspaces with priority: pnpm -> yarn -> npm
        for kind, lock_name in self._NODE_LOCKS.items():
            if lock_name in files:
                manifest = directory / lock_name
                workspaces.append(Workspace(directory=directory, kind=kind, manifest=manifest))
                break
        else:
            if "package.json" in files:
                workspaces.append(
                    Workspace(directory=directory, kind=WorkspaceKind.NPM, manifest=directory / "package.json")
                )

        if "go.mod" in files:
            workspaces.append(
                Workspace(directory=directory, kind=WorkspaceKind.GO, manifest=directory / "go.mod")
            )

        if "Cargo.toml" in files:
            workspaces.append(
                Workspace(directory=directory, kind=WorkspaceKind.RUST, manifest=directory / "Cargo.toml")
            )

        return workspaces


def _default_runner(args: Sequence[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
    )


class WorkspaceUpdater:
    """Apply package manager updates across discovered workspaces."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        dry_run: bool = False,
        use_emoji: bool = True,
    ) -> None:
        self._runner = runner or _default_runner
        self._dry_run = dry_run
        self._use_emoji = use_emoji

    def update(
        self,
        root: Path,
        *,
        managers: set[WorkspaceKind] | None = None,
        workspaces: Iterable[Workspace],
    ) -> UpdateResult:
        result = UpdateResult()
        for workspace in workspaces:
            if managers and workspace.kind not in managers:
                continue
            rel_path = _format_relative(workspace.directory, root)
            info(
                f"Updating {workspace.kind.value} workspace at {rel_path}",
                use_emoji=self._use_emoji,
            )
            commands = self._commands_for(workspace)
            if not commands:
                warn("No update strategy available", use_emoji=self._use_emoji)
                result.record_skip(workspace)
                continue
            failed = False
            for command in commands:
                if self._dry_run:
                    info(
                        f"DRY RUN: {' '.join(command)}",
                        use_emoji=self._use_emoji,
                    )
                    continue
                cp = self._runner(command, workspace.directory)
                if cp.returncode != 0:
                    message = (
                        f"Command '{' '.join(command)}' failed with exit code {cp.returncode}"
                    )
                    fail(message, use_emoji=self._use_emoji)
                    result.record_failure(workspace, f"{rel_path}: {message}")
                    failed = True
                    break
            if not failed:
                if self._dry_run:
                    result.record_skip(workspace)
                else:
                    ok("Workspace updated", use_emoji=self._use_emoji)
                    result.record_success(workspace)
        return result

    def _commands_for(self, workspace: Workspace) -> list[list[str]]:
        if workspace.kind is WorkspaceKind.PYTHON:
            return self._python_commands(workspace)
        if workspace.kind is WorkspaceKind.PNPM:
            return self._pnpm_commands(workspace)
        if workspace.kind is WorkspaceKind.YARN:
            return self._yarn_commands(workspace)
        if workspace.kind is WorkspaceKind.NPM:
            return self._npm_commands(workspace)
        if workspace.kind is WorkspaceKind.GO:
            return self._go_commands(workspace)
        if workspace.kind is WorkspaceKind.RUST:
            return self._rust_commands(workspace)
        return []

    def _python_commands(self, workspace: Workspace) -> list[list[str]]:
        commands: list[list[str]] = []
        venv = workspace.directory / ".venv"
        if not venv.exists():
            commands.append(["uv", "venv"])
        commands.append(
            [
                "uv",
                "sync",
                "-U",
                "--all-extras",
                "--all-groups",
                "--managed-python",
                "--link-mode=hardlink",
                "--compile-bytecode",
            ]
        )
        return commands

    def _pnpm_commands(self, workspace: Workspace) -> list[list[str]]:
        if not shutil.which("pnpm"):
            warn("pnpm not found in PATH; skipping", use_emoji=self._use_emoji)
            return []
        return [["pnpm", "up", "--latest"]]

    def _yarn_commands(self, workspace: Workspace) -> list[list[str]]:
        if not shutil.which("yarn"):
            warn("yarn not found in PATH; skipping", use_emoji=self._use_emoji)
            return []
        return [["yarn", "upgrade", "--latest"]]

    def _npm_commands(self, workspace: Workspace) -> list[list[str]]:
        if not shutil.which("npm"):
            warn("npm not found in PATH; skipping", use_emoji=self._use_emoji)
            return []
        return [["npm", "update"]]

    def _go_commands(self, workspace: Workspace) -> list[list[str]]:
        if not shutil.which("go"):
            warn("go not found in PATH; skipping", use_emoji=self._use_emoji)
            return []
        return [["go", "get", "-u", "./..."], ["go", "mod", "tidy"]]

    def _rust_commands(self, workspace: Workspace) -> list[list[str]]:
        if not shutil.which("cargo"):
            warn("cargo not found in PATH; skipping", use_emoji=self._use_emoji)
            return []
        return [["cargo", "update"]]


def ensure_lint_install(root: Path, runner: CommandRunner, *, dry_run: bool) -> None:
    lint_shim = root / "py-qa" / "lint"
    if not lint_shim.exists():
        return
    command = [str(lint_shim), "install"]
    info("Ensuring py-qa lint dependencies are installed", use_emoji=True)
    if dry_run:
        info(f"DRY RUN: {' '.join(command)}", use_emoji=True)
        return
    cp = runner(command, root)
    if cp.returncode != 0:
        warn(
            f"py-qa lint install failed with exit code {cp.returncode}",
            use_emoji=True,
        )


def _format_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)) or "."
    except ValueError:
        return str(path)


__all__ = [
    "Workspace",
    "WorkspaceKind",
    "WorkspaceDiscovery",
    "WorkspaceUpdater",
    "UpdateResult",
    "ensure_lint_install",
]
