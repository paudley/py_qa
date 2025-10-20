# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Repository quality checks and enforcement helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Final

from pyqa.core.config.constants import ALWAYS_EXCLUDE_DIRS

from ..config import FileDiscoveryConfig, LicenseConfig, QualityConfigSection
from ..config.types import ConfigFragment
from ..core.runtime.process import CommandOptions, run_command
from ..discovery.filesystem import FilesystemDiscovery
from ..discovery.git import GitDiscovery, list_tracked_files
from ..filesystem.paths import normalize_path
from ..tools.settings import tool_setting_schema_as_dict
from .banned import BannedWordChecker
from .checks.license_fixer import LicenseFixError, LicenseHeaderFixer
from .checks.licenses import LicensePolicy, load_license_policy, normalise_notice, verify_file_license
from .quality_components import QualityCheck, QualityCheckResult, QualityContext, QualityIssue, QualityIssueLevel
from .quality_components.hygiene import (
    PythonHygieneCheck,
)

COPYRIGHT_KEYWORDS: Final[tuple[str, ...]] = ("copyright", "notice")
MAX_COMMIT_SUBJECT_LENGTH: Final[int] = 72
MAX_COMMIT_LINE_LENGTH: Final[int] = 72
COMMIT_DESCRIPTION_SEPARATOR: Final[str] = ": "
LICENSE_HEADER_CATEGORY: Final[str] = "license-header"
COPYRIGHT_CATEGORY: Final[str] = "copyright"
SCHEMA_SYNC_CATEGORY: Final[str] = "schema"


@dataclass(slots=True)
class FileSizeCheck:
    """Enforce configured file size thresholds."""

    name: str = "file-size"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Validate file sizes against maximum and warning thresholds.

        Args:
            ctx: Quality context containing candidate files and configuration.
            result: Aggregated result used to record issues.
        """

        for path in ctx.files:
            try:
                size = path.stat().st_size
            except OSError as exc:
                result.add_warning(f"Could not stat file {path}: {exc}", path, check=self.name)
                continue
            if size > ctx.quality.max_file_size:
                result.add_error(
                    f"File exceeds maximum size ({size} bytes > {ctx.quality.max_file_size} bytes)",
                    path,
                    check=self.name,
                )
            elif size > ctx.quality.warn_file_size:
                result.add_warning(
                    f"File close to size limit ({size} bytes)",
                    path,
                    check=self.name,
                )

    def supports_fix(self) -> bool:
        """Report that this check cannot modify offending files.

        Returns:
            bool: Always ``False`` because the check only records findings.
        """

        return False


@dataclass(slots=True)
class LicenseCheck:
    """Validate and optionally repair license headers."""

    name: str = "license"

    @dataclass(slots=True)
    class EvaluationOptions:
        """Collect inputs required to evaluate a license header."""

        policy: LicensePolicy
        root: Path
        fixer: LicenseHeaderFixer | None
        current_year: int | None
        result: QualityCheckResult

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Verify license headers across candidate files.

        When ``ctx.fix`` is true, the check attempts to update headers using
        :class:`LicenseHeaderFixer` before revalidating the file.

        Args:
            ctx: Quality context describing files and settings.
            result: Result collector used to record findings.
        """

        policy = ctx.license_policy
        if not policy:
            return

        fixer = LicenseHeaderFixer(policy) if ctx.fix else None
        options = self.EvaluationOptions(
            policy=policy,
            root=ctx.root,
            fixer=fixer,
            current_year=fixer.current_year if fixer else None,
            result=result,
        )
        observed_notices: set[str] = set()

        for path in ctx.files:
            if not _is_textual_candidate(path):
                continue
            content = self._read_text(path, result)
            if content is None:
                continue

            issues, final_content = self._evaluate_license(path, content, options)
            for issue in issues:
                category = self._classify_issue(issue)
                result.add_error(issue, path, check=category)

            notice = policy.match_notice(final_content)
            if notice:
                observed_notices.add(normalise_notice(notice))

        if policy.canonical_notice and len(observed_notices) > 1:
            result.add_warning(
                "Multiple copyright notices detected across files; ensure headers use a consistent notice.",
                check=COPYRIGHT_CATEGORY,
            )

    def supports_fix(self) -> bool:
        """Report that license headers can be auto-corrected.

        Returns:
            bool: Always ``True`` because the check can rewrite headers.
        """

        return True

    def _read_text(self, path: Path, result: QualityCheckResult) -> str | None:
        """Read file contents or record an access warning.

        Args:
            path: File to read from disk.
            result: Result collector used to record warnings.

        Returns:
            str | None: File content when readable; otherwise ``None``.
        """

        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result.add_warning(
                f"Unable to read file for license check: {exc}",
                path,
                check=LICENSE_HEADER_CATEGORY,
            )
            return None

    def _evaluate_license(
        self,
        path: Path,
        content: str,
        options: EvaluationOptions,
    ) -> tuple[list[str], str]:
        """Evaluate license issues for ``path`` and return updated content.

        Args:
            path: File under evaluation.
            content: Original file content.
            options: Evaluation settings containing policy and fixer details.

        Returns:
            tuple[list[str], str]: Collected issues and the content used to extract notices.
        """

        issues = verify_file_license(
            path,
            content,
            options.policy,
            options.root,
            current_year=options.current_year,
        )
        if not issues or options.fixer is None:
            return issues, content

        updated_content = self._attempt_fix(path, content, options.fixer, options.result)
        if updated_content is None:
            return issues, content

        refreshed = verify_file_license(
            path,
            updated_content,
            options.policy,
            options.root,
            current_year=options.current_year,
        )
        return refreshed, updated_content

    def _attempt_fix(
        self,
        path: Path,
        content: str,
        fixer: LicenseHeaderFixer,
        result: QualityCheckResult,
    ) -> str | None:
        """Apply an automatic license fix returning the updated content.

        Args:
            path: File path to update.
            content: Original file content prior to fixes.
            fixer: License header fixer responsible for applying updates.
            result: Result collector used to record warnings or errors.

        Returns:
            str | None: Updated content when the fix succeeds; otherwise ``None``.
        """

        try:
            updated = fixer.apply(path, content)
        except LicenseFixError as exc:
            result.add_warning(
                f"Automatic license fix skipped: {exc}",
                path,
                check=LICENSE_HEADER_CATEGORY,
            )
            return None
        if not updated:
            return None
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            result.add_error(
                f"Failed to update license header: {exc}",
                path,
                check=LICENSE_HEADER_CATEGORY,
            )
            return None
        return updated

    def _classify_issue(self, issue: str) -> str:
        """Return the derived category for a license-related issue.

        Args:
            issue: Diagnostic message produced during license evaluation.

        Returns:
            str: Category identifier used when recording the issue.
        """

        lowered = issue.lower()
        if any(keyword in lowered for keyword in COPYRIGHT_KEYWORDS):
            return COPYRIGHT_CATEGORY
        return LICENSE_HEADER_CATEGORY


class SchemaCheck:
    """Validate that exported schema documentation matches tool metadata."""

    name: str = "schema"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Compare generated schema artefacts with the current tool schema.

        Args:
            ctx: Quality context describing the filesystem and configuration.
            result: Aggregated result used to record schema mismatches.
        """

        if not ctx.quality.schema_targets:
            return
        expected_raw = json.dumps(tool_setting_schema_as_dict(), indent=2, sort_keys=True) + "\n"
        expected = json.loads(expected_raw)
        for target in ctx.quality.schema_targets:
            target_path = target if target.is_absolute() else (ctx.root / target).resolve()
            if not target_path.exists():
                result.add_error(
                    "Schema documentation missing. Run 'pyqa config export-tools' to regenerate.",
                    target_path,
                    check=SCHEMA_SYNC_CATEGORY,
                )
                continue
            actual_text = target_path.read_text(encoding="utf-8")
            if actual_text == expected_raw:
                continue
            try:
                parsed_actual = json.loads(actual_text)
            except json.JSONDecodeError:
                relative = _relative_to_root(target_path, ctx.root)
                result.add_error(
                    f"Schema documentation out of date. Run 'pyqa config export-tools {relative}' to refresh.",
                    target_path,
                    check=SCHEMA_SYNC_CATEGORY,
                )
                continue
            parsed_actual.pop("_license", None)
            parsed_actual.pop("_copyright", None)
            if parsed_actual != expected:
                relative = _relative_to_root(target_path, ctx.root)
                result.add_error(
                    f"Schema documentation out of date. Run 'pyqa config export-tools {relative}' to refresh.",
                    target_path,
                    check=SCHEMA_SYNC_CATEGORY,
                )

    def supports_fix(self) -> bool:
        """Report that regeneration requires an external command.

        Returns:
            bool: Always ``False`` because fixes must be performed externally.
        """

        return False


@dataclass(slots=True)
class QualityFileCollector:
    """Gather files for quality checks using existing discovery strategies."""

    root: Path

    def collect(self, files: Sequence[Path] | None, *, staged: bool) -> list[Path]:
        """Return files selected for quality checks.

        Args:
            files: Optional explicit file list supplied by the caller.
            staged: When true, consider only staged files via git discovery.

        Returns:
            list[Path]: Deduplicated list of files to analyse.
        """

        if files:
            return [self._resolve(path) for path in files if self._resolve(path).exists()]

        if staged:
            git_discovery = GitDiscovery()
            config = FileDiscoveryConfig(pre_commit=True, include_untracked=True, changed_only=True)
            return [path.resolve() for path in git_discovery.discover(config, self.root) if path.exists()]

        tracked = list_tracked_files(self.root)
        if tracked:
            return [path for path in tracked if path.exists()]

        filesystem_discovery = FilesystemDiscovery()
        config = FileDiscoveryConfig()
        return [path.resolve() for path in filesystem_discovery.discover(config, self.root) if path.exists()]

    def _resolve(self, path: Path) -> Path:
        """Resolve ``path`` relative to :attr:`root` when necessary.

        Args:
            path: Path supplied by the caller.

        Returns:
            Path: Absolute path anchored to :attr:`root` when ``path`` is relative.
        """

        return path if path.is_absolute() else (self.root / path).resolve()


@dataclass(frozen=True, slots=True)
class QualityCheckerOptions:
    """Optional parameters used to configure :class:`QualityChecker`."""

    license_policy: LicensePolicy | None = None
    license_overrides: LicenseConfig | ConfigFragment | None = None
    files: Sequence[Path] | None = None
    checks: Iterable[str] | None = None
    staged: bool = False
    collector: QualityFileCollector | None = None


class QualityChecker:
    """Run quality enforcement checks across a project workspace."""

    def __init__(
        self,
        root: Path,
        *,
        quality: QualityConfigSection,
        options: QualityCheckerOptions | None = None,
    ) -> None:
        """Initialise the quality checker with configuration and options.

        Args:
            root: Repository root where quality checks operate.
            quality: Quality configuration section defining thresholds and toggles.
            options: Optional advanced options controlling check selection and inputs.
        """

        self.root = root.resolve()
        self.quality = quality
        self._options = options or QualityCheckerOptions()
        self._collector = self._options.collector or QualityFileCollector(self.root)
        self.license_policy = self._options.license_policy or load_license_policy(
            self.root, self._options.license_overrides
        )
        self._selected_checks = set(self._options.checks) if self._options.checks else set(quality.checks)
        self._available_checks: dict[str, QualityCheck] = {
            "file-size": FileSizeCheck(),
            "license": LicenseCheck(),
            "python": PythonHygieneCheck(),
            "schema": SchemaCheck(),
        }

    def run(self, *, fix: bool = False) -> QualityCheckResult:
        """Execute configured quality checks and return their aggregated result.

        Args:
            fix: When ``True``, enable fix-capable checks to update files in-place.

        Returns:
            QualityCheckResult: Aggregated outcome of all executed checks.
        """

        result = QualityCheckResult()
        explicit_files = self._normalized_explicit_files()
        raw_files = self._collector.collect(explicit_files, staged=self._options.staged)
        files = self._filter_files(raw_files)
        context = QualityContext(
            root=self.root,
            files=files,
            quality=self.quality,
            license_policy=self.license_policy,
            fix=fix,
        )
        for name, check in self._available_checks.items():
            if name not in self._selected_checks:
                continue
            check.run(context, result)
        return result

    def available_checks(self) -> Mapping[str, QualityCheck]:
        """Return a mapping of available check names to their implementations.

        Returns:
            Mapping[str, QualityCheck]: Copy of registered check implementations keyed by name.
        """

        return dict(self._available_checks)

    # ------------------------------------------------------------------
    def _filter_files(self, files: Sequence[Path]) -> list[Path]:
        """Return ``files`` with duplicates and excluded paths removed.

        Args:
            files: Candidate file sequence discovered from the workspace.

        Returns:
            list[Path]: Deduplicated and filtered file list ready for analysis.
        """

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
        """Return whether ``path`` should be excluded from quality checks.

        Args:
            path: Candidate file resolved to an absolute path.

        Returns:
            bool: ``True`` when the path should be skipped.
        """

        try:
            relative = path.relative_to(self.root)
        except ValueError:
            relative = Path(path.name)
        if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
            return True
        relative_str = str(relative)
        return any(fnmatch(relative_str, pattern) for pattern in self.quality.skip_globs)

    def _resolve_path(self, path: Path) -> Path:
        """Resolve user-provided ``path`` relative to the project root.

        Args:
            path: Path supplied via CLI or configuration.

        Returns:
            Path: Absolute, normalised path anchored to :attr:`root`.
        """

        try:
            normalised = normalize_path(path, base_dir=self.root)
        except (ValueError, OSError):
            return path if path.is_absolute() else (self.root / path).resolve()
        if normalised.is_absolute():
            return normalised
        try:
            return (self.root / normalised).resolve()
        except OSError:
            return (self.root / normalised).absolute()

    def _normalized_explicit_files(self) -> list[Path] | None:
        """Return resolved explicit files specified via options.

        Returns:
            list[Path] | None: Resolved file list when explicitly provided.
        """

        if not self._options.files:
            return None
        return [self._resolve_path(path) for path in self._options.files]


CONVENTIONAL_SUBJECT = re.compile(
    r"^(build|chore|ci|deps|docs|feat|fix|perf|refactor|revert|style|test)(?:\([^)]+\))?(?:!)?: \S.+$",
)


def check_commit_message(root: Path, message_file: Path) -> QualityCheckResult:
    """Validate commit message formatting and banned word usage.

    Args:
        root: Repository root used to resolve auxiliary resources.
        message_file: Path to the commit message file to inspect.

    Returns:
        QualityCheckResult: Aggregated findings describing message violations.
    """
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
    if len(subject) > MAX_COMMIT_SUBJECT_LENGTH:
        result.add_error(
            f"Commit subject exceeds {MAX_COMMIT_SUBJECT_LENGTH} characters",
            message_path,
        )
    if not CONVENTIONAL_SUBJECT.match(subject):
        result.add_error(
            "Commit subject must follow Conventional Commits (type(scope): description)",
            message_path,
        )
    elif COMMIT_DESCRIPTION_SEPARATOR in subject:
        description = subject.split(COMMIT_DESCRIPTION_SEPARATOR, 1)[1]
        if description and description[0].isalpha() and not description[0].islower():
            result.add_warning(
                "Commit subject description should start with lowercase letter",
                message_path,
            )

    for idx, line in enumerate(lines[1:], start=2):
        if len(line) > MAX_COMMIT_LINE_LENGTH:
            result.add_warning(
                f"Line {idx} exceeds {MAX_COMMIT_LINE_LENGTH} characters",
                message_path,
            )

    checker = BannedWordChecker(root=root)
    banned_matches = checker.scan(lines)
    if banned_matches:
        formatted = ", ".join(sorted(set(banned_matches)))
        result.add_error(f"Commit message contains banned terms: {formatted}", message_path)

    return result


def ensure_branch_protection(root: Path, quality: QualityConfigSection) -> QualityCheckResult:
    """Fail when attempting to operate on a protected branch.

    Args:
        root: Repository root whose git metadata should be inspected.
        quality: Quality configuration containing protected branch names.

    Returns:
        QualityCheckResult: Result capturing protection violations.
    """

    result = QualityCheckResult()
    branch = _current_branch(root)
    if branch and branch in set(quality.protected_branches):
        result.add_error(f"Branch '{branch}' is protected. Create a feature branch before pushing.")
    return result


def _current_branch(root: Path) -> str | None:
    """Return the current git branch for *root* or ``None`` on failure.

    Args:
        root: Repository root whose branch should be detected.

    Returns:
        str | None: Current branch name when available.
    """

    options = CommandOptions(check=False, capture_output=True)
    completed = run_command(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        options=options,
    )
    if completed.returncode != 0:
        return None
    branch = completed.stdout.strip()
    return branch or None


def _relative_to_root(path: Path, root: Path) -> Path:
    """Return ``path`` relative to ``root`` when possible.

    Args:
        path: Candidate path under consideration.
        root: Repository root used as the base for relative paths.

    Returns:
        Path: Relative path when possible, otherwise the original ``path``.
    """

    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _is_textual_candidate(path: Path) -> bool:
    """Return ``True`` when ``path`` likely contains textual contents.

    Args:
        path: Candidate file path.

    Returns:
        bool: ``True`` when the file is treated as textual for license scanning.
    """

    return path.suffix.lower() in {
        ".py",
        ".pyi",
        ".toml",
        ".md",
        ".rst",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".sh",
        ".bash",
        ".ps1",
        ".jsonc",
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


__all__ = [
    "FileSizeCheck",
    "LicenseCheck",
    "QualityCheck",
    "QualityCheckResult",
    "QualityChecker",
    "QualityCheckerOptions",
    "QualityContext",
    "QualityFileCollector",
    "QualityIssue",
    "QualityIssueLevel",
    "SchemaCheck",
    "check_commit_message",
    "ensure_branch_protection",
]
