# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Repository quality checks and enforcement helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .banned import BannedWordChecker
from .checks.licenses import (
    LicensePolicy,
    load_license_policy,
    normalise_notice,
    verify_file_license,
)
from .config import FileDiscoveryConfig, LicenseConfig, QualityConfigSection
from .constants import ALWAYS_EXCLUDE_DIRS
from .discovery.filesystem import FilesystemDiscovery
from .discovery.git import GitDiscovery, list_tracked_files
from .process_utils import run_command
from .tools.settings import TOOL_SETTING_SCHEMA


class QualityIssueLevel(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class QualityIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: QualityIssueLevel
    message: str
    path: Path | None = None


class QualityCheckResult(BaseModel):
    """Aggregate quality issues collected during a run."""

    model_config = ConfigDict(validate_assignment=True)

    issues: list[QualityIssue] = Field(default_factory=list)

    def add_error(self, message: str, path: Path | None = None) -> None:
        issues = list(self.issues)
        issues.append(QualityIssue(level=QualityIssueLevel.ERROR, message=message, path=path))
        self.issues = issues

    def add_warning(self, message: str, path: Path | None = None) -> None:
        issues = list(self.issues)
        issues.append(QualityIssue(level=QualityIssueLevel.WARNING, message=message, path=path))
        self.issues = issues

    @property
    def errors(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.level is QualityIssueLevel.ERROR]

    @property
    def warnings(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.level is QualityIssueLevel.WARNING]

    def exit_code(self) -> int:
        return 1 if self.errors else 0


@dataclass(slots=True)
class QualityContext:
    """Shared context passed to individual quality checks."""

    root: Path
    files: Sequence[Path]
    quality: QualityConfigSection
    license_policy: LicensePolicy | None


class QualityCheck(Protocol):
    """Contract for individual quality checks."""

    name: str

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Execute the check and append findings to *result*."""


@dataclass
class FileSizeCheck:
    name: str = "file-size"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        for path in ctx.files:
            try:
                size = path.stat().st_size
            except OSError as exc:
                result.add_warning(f"Could not stat file {path}: {exc}", path)
                continue
            if size > ctx.quality.max_file_size:
                result.add_error(
                    f"File exceeds maximum size ({size} bytes > {ctx.quality.max_file_size} bytes)",
                    path,
                )
            elif size > ctx.quality.warn_file_size:
                result.add_warning(
                    f"File close to size limit ({size} bytes)",
                    path,
                )


@dataclass
class LicenseCheck:
    name: str = "license"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        policy = ctx.license_policy
        if not policy:
            return

        observed_notices: set[str] = set()
        for path in ctx.files:
            if not _is_textual_candidate(path):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                result.add_warning(f"Unable to read file for license check: {exc}", path)
                continue

            issues = verify_file_license(path, content, policy, ctx.root)
            for issue in issues:
                result.add_error(issue, path)

            observed = policy.match_notice(content)
            if observed:
                observed_notices.add(normalise_notice(observed))

        if policy.canonical_notice and len(observed_notices) > 1:
            result.add_warning(
                "Multiple copyright notices detected across files; ensure headers use a consistent notice.",
            )


@dataclass
class PythonHygieneCheck:
    name: str = "python"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        python_files = [path for path in ctx.files if path.suffix in {".py", ".pyi"}]
        for path in python_files:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                result.add_warning(f"Unable to read Python file: {exc}", path)
                continue
            if re.search(r"(?<!['\"])pdb\.set_trace\(", content) or re.search(
                r"(?<!['\"])breakpoint\(",
                content,
            ):
                result.add_error("Debug breakpoint detected", path)
            if re.search(r"except\s*:\s*(?:#.*)?$", content, re.MULTILINE):
                result.add_warning("Bare except detected", path)


@dataclass
class SchemaCheck:
    name: str = "schema"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        if not ctx.quality.schema_targets:
            return
        expected = json.dumps(TOOL_SETTING_SCHEMA, indent=2, sort_keys=True) + "\n"
        for target in ctx.quality.schema_targets:
            target_path = target if target.is_absolute() else (ctx.root / target).resolve()
            if not target_path.exists():
                result.add_error(
                    "Schema documentation missing. Run 'pyqa config export-tools' to regenerate.",
                    target_path,
                )
                continue
            actual = target_path.read_text(encoding="utf-8")
            if actual == expected:
                continue
            try:
                parsed_actual = json.loads(actual)
            except json.JSONDecodeError:
                relative = _relative_to_root(target_path, ctx.root)
                result.add_error(
                    f"Schema documentation out of date. Run 'pyqa config export-tools {relative}' to refresh.",
                    target_path,
                )
                continue
            parsed_expected = json.loads(expected)
            parsed_actual.pop("_license", None)
            parsed_actual.pop("_copyright", None)
            if parsed_actual != parsed_expected:
                relative = _relative_to_root(target_path, ctx.root)
                result.add_error(
                    f"Schema documentation out of date. Run 'pyqa config export-tools {relative}' to refresh.",
                    target_path,
                )


@dataclass(slots=True)
class QualityFileCollector:
    """Gather files for quality checks using existing discovery strategies."""

    root: Path

    def collect(self, files: Sequence[Path] | None, *, staged: bool) -> list[Path]:
        if files:
            return [self._resolve(path) for path in files if self._resolve(path).exists()]

        if staged:
            git_discovery = GitDiscovery()
            config = FileDiscoveryConfig(pre_commit=True, include_untracked=True, changed_only=True)
            return [
                path.resolve()
                for path in git_discovery.discover(config, self.root)
                if path.exists()
            ]

        tracked = list_tracked_files(self.root)
        if tracked:
            return [path for path in tracked if path.exists()]

        filesystem_discovery = FilesystemDiscovery()
        config = FileDiscoveryConfig()
        return [
            path.resolve()
            for path in filesystem_discovery.discover(config, self.root)
            if path.exists()
        ]

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.root / path).resolve()


class QualityChecker:
    """Run quality enforcement checks across a project workspace."""

    def __init__(
        self,
        root: Path,
        *,
        quality: QualityConfigSection,
        license_policy: LicensePolicy | None = None,
        license_overrides: LicenseConfig | Mapping[str, object] | None = None,
        files: Sequence[Path] | None = None,
        checks: Iterable[str] | None = None,
        staged: bool = False,
        collector: QualityFileCollector | None = None,
    ) -> None:
        self.root = root.resolve()
        self.quality = quality
        self._staged = staged
        self._explicit_files = [self._resolve_path(path) for path in files] if files else None
        self._collector = collector or QualityFileCollector(self.root)
        self._selected_checks = set(checks) if checks else set(quality.checks)
        self.license_policy = license_policy or load_license_policy(self.root, license_overrides)
        self._available_checks: dict[str, QualityCheck] = {
            "file-size": FileSizeCheck(),
            "license": LicenseCheck(),
            "python": PythonHygieneCheck(),
            "schema": SchemaCheck(),
        }

    def run(self) -> QualityCheckResult:
        result = QualityCheckResult()
        raw_files = self._collector.collect(self._explicit_files, staged=self._staged)
        files = self._filter_files(raw_files)
        context = QualityContext(
            root=self.root,
            files=files,
            quality=self.quality,
            license_policy=self.license_policy,
        )
        for name, check in self._available_checks.items():
            if name not in self._selected_checks:
                continue
            check.run(context, result)
        return result

    # ------------------------------------------------------------------
    def _filter_files(self, files: Sequence[Path]) -> list[Path]:
        filtered: list[Path] = []
        seen: set[Path] = set()
        for path in files:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if self._is_excluded(resolved):
                continue
            filtered.append(resolved)
        return filtered

    def _is_excluded(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            relative = Path(path.name)
        if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
            return True
        relative_str = str(relative)
        return any(fnmatch(relative_str, pattern) for pattern in self.quality.skip_globs)

    def _resolve_path(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.root / path).resolve()


CONVENTIONAL_SUBJECT = re.compile(
    r"^(build|chore|ci|deps|docs|feat|fix|perf|refactor|revert|style|test)(?:\([^)]+\))?(?:!)?: \S.+$",
)


def check_commit_message(root: Path, message_file: Path) -> QualityCheckResult:
    """Validate commit message formatting and banned word usage."""
    root = root.resolve()
    message_path = message_file.resolve()
    result = QualityCheckResult()

    if not message_path.exists():
        result.add_error("Commit message file does not exist", message_path)
        return result

    content = message_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines:
        result.add_error("Commit message is empty", message_path)
        return result

    subject = lines[0]
    if len(subject) > 72:
        result.add_error("Commit subject exceeds 72 characters", message_path)
    if not CONVENTIONAL_SUBJECT.match(subject):
        result.add_error(
            "Commit subject must follow Conventional Commits (type(scope): description)",
            message_path,
        )
    elif ": " in subject:
        description = subject.split(": ", 1)[1]
        if description and description[0].isalpha() and not description[0].islower():
            result.add_warning(
                "Commit subject description should start with lowercase letter",
                message_path,
            )

    for idx, line in enumerate(lines[1:], start=2):
        if len(line) > 72:
            result.add_warning(f"Line {idx} exceeds 72 characters", message_path)

    checker = BannedWordChecker(root=root)
    banned_matches = checker.scan(lines)
    if banned_matches:
        formatted = ", ".join(sorted(set(banned_matches)))
        result.add_error(f"Commit message contains banned terms: {formatted}", message_path)

    return result


def ensure_branch_protection(root: Path, quality: QualityConfigSection) -> QualityCheckResult:
    """Fail when attempting to operate on a protected branch."""
    result = QualityCheckResult()
    branch = _current_branch(root)
    if branch and branch in set(quality.protected_branches):
        result.add_error(f"Branch '{branch}' is protected. Create a feature branch before pushing.")
    return result


def _current_branch(root: Path) -> str | None:
    completed = run_command(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    branch = completed.stdout.strip()
    return branch or None


def _relative_to_root(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _is_textual_candidate(path: Path) -> bool:
    return path.suffix.lower() in {
        ".py",
        ".pyi",
        ".toml",
        ".md",
        ".rst",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".sh",
        ".bash",
        ".ps1",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".js",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".cs",
    }
