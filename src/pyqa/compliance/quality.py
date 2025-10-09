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
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict, Field

from pyqa.core.config.constants import ALWAYS_EXCLUDE_DIRS

from ..config import FileDiscoveryConfig, LicenseConfig, QualityConfigSection
from ..core.runtime.process import run_command
from ..discovery.filesystem import FilesystemDiscovery
from ..discovery.git import GitDiscovery, list_tracked_files
from ..filesystem.paths import normalize_path
from ..tools.settings import tool_setting_schema_as_dict
from .banned import BannedWordChecker
from .checks.license_fixer import LicenseFixError, LicenseHeaderFixer
from .checks.licenses import (
    LicensePolicy,
    load_license_policy,
    normalise_notice,
    verify_file_license,
)

# Thresholds for commit message validation.
MAX_COMMIT_SUBJECT_LENGTH: Final[int] = 72
MAX_COMMIT_LINE_LENGTH: Final[int] = 72
COMMIT_DESCRIPTION_SEPARATOR: Final[str] = ": "


class QualityIssueLevel(str, Enum):
    """Severity classification for issues discovered during quality checks."""

    ERROR = "error"
    WARNING = "warning"


LICENSE_HEADER_CATEGORY: Final[str] = "license-header"
COPYRIGHT_CATEGORY: Final[str] = "copyright"
PYTHON_HYGIENE_CATEGORY: Final[str] = "python-hygiene"
SCHEMA_SYNC_CATEGORY: Final[str] = "schema"
PYTHON_HYGIENE_BREAKPOINT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:debug-breakpoint"
PYTHON_HYGIENE_BARE_EXCEPT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:bare-except"
PYTHON_HYGIENE_MAIN_GUARD: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:module-main"
PYTHON_HYGIENE_BROAD_EXCEPTION: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:broad-exception"
PYTHON_HYGIENE_DEBUG_IMPORT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:debug-import"
PYTHON_HYGIENE_SYSTEM_EXIT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:system-exit"
PYTHON_HYGIENE_PRINT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:print"


class QualityIssue(BaseModel):
    """Concrete issue discovered by a quality check."""

    model_config = ConfigDict(frozen=True)

    level: QualityIssueLevel
    message: str
    path: Path | None = None
    check: str | None = None


class QualityCheckResult(BaseModel):
    """Aggregate quality issues collected during a run."""

    model_config = ConfigDict(validate_assignment=True)

    issues: list[QualityIssue] = Field(default_factory=list)

    def add_error(self, message: str, path: Path | None = None, *, check: str | None = None) -> None:
        """Record an error-level issue identified by a quality check.

        Args:
            message: Description of the issue.
            path: Optional file location associated with the issue.
            check: Optional identifier describing the originating check or
                sub-check.
        """

        issues = list(self.issues)
        issues.append(
            QualityIssue(
                level=QualityIssueLevel.ERROR,
                message=message,
                path=path,
                check=check,
            ),
        )
        self.issues = issues

    def add_warning(self, message: str, path: Path | None = None, *, check: str | None = None) -> None:
        """Record a warning-level issue identified by a quality check.

        Args:
            message: Description of the warning.
            path: Optional file location associated with the warning.
            check: Optional identifier describing the originating check or
                sub-check.
        """

        issues = list(self.issues)
        issues.append(
            QualityIssue(
                level=QualityIssueLevel.WARNING,
                message=message,
                path=path,
                check=check,
            ),
        )
        self.issues = issues

    @property
    def errors(self) -> list[QualityIssue]:
        """Return the subset of recorded issues that are classified as errors."""

        return [issue for issue in self.issues if issue.level is QualityIssueLevel.ERROR]

    @property
    def warnings(self) -> list[QualityIssue]:
        """Return the subset of recorded issues that are classified as warnings."""

        return [issue for issue in self.issues if issue.level is QualityIssueLevel.WARNING]

    def exit_code(self) -> int:
        """Return the process exit code implied by the collected issues."""

        return 1 if self.errors else 0


@dataclass(slots=True)
class QualityContext:
    """Shared context passed to individual quality checks."""

    root: Path
    files: Sequence[Path]
    quality: QualityConfigSection
    license_policy: LicensePolicy | None
    fix: bool = False


class QualityCheck(Protocol):
    """Contract for individual quality checks."""

    name: str

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Execute the check and append findings to *result*."""
        raise NotImplementedError

    def supports_fix(self) -> bool:
        """Return ``True`` when the check can perform in-place fixes."""
        raise NotImplementedError


@dataclass(slots=True)
class FileSizeCheck:
    """Quality check that enforces configured file size thresholds."""

    name: str = "file-size"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Validate file sizes against maximum and warning thresholds."""

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
        """Return ``False`` because this check cannot modify offending files."""

        return False


@dataclass(slots=True)
class LicenseCheck:
    """Validate and optionally repair license headers."""

    name: str = "license"

    @dataclass(slots=True)
    class EvaluationOptions:
        """Aggregated inputs required to evaluate a license header."""

        policy: LicensePolicy
        root: Path
        fixer: LicenseHeaderFixer | None
        current_year: int | None
        result: QualityCheckResult

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Verify license headers across candidate files.

        When ``ctx.fix`` is true, the check attempts to update headers using
        :class:`LicenseHeaderFixer` before revalidating the file.
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
        """Return ``True`` because license headers can be auto-corrected."""

        return True

    def _read_text(self, path: Path, result: QualityCheckResult) -> str | None:
        """Return file contents or record an access warning."""

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
        """Return issues for ``path`` and the content used for notice extraction."""

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
        """Apply an automatic license fix returning the updated content."""

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
        """Return the derived category for a license-related issue."""

        lowered = issue.lower()
        if "copyright" in lowered or "notice" in lowered:
            return COPYRIGHT_CATEGORY
        return LICENSE_HEADER_CATEGORY


@dataclass(slots=True)
class PythonHygieneCheck:
    """Ensure Python sources do not contain debugging leftovers or bare excepts."""

    name: str = "python"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Scan Python files for common hygiene violations."""

        python_files = [path for path in ctx.files if path.suffix in {".py", ".pyi"}]
        for path in python_files:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                result.add_warning(
                    f"Unable to read Python file: {exc}",
                    path,
                    check=PYTHON_HYGIENE_CATEGORY,
                )
                continue
            try:
                relative_parts = path.relative_to(ctx.root).parts
            except ValueError:
                relative_parts = path.parts
            if "tests" in relative_parts:
                continue

            is_cli_module = "cli" in relative_parts and "commands" in relative_parts
            found_main_guard = False

            for line_number, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                lower_stripped = stripped.lower()

                if not found_main_guard and re.match(r"if __name__ == ['\"]__main__['\"]\s*:", stripped):
                    found_main_guard = True
                    result.add_warning(
                        f"Line {line_number}: Module defines a __main__ execution block; move the entry point to a dedicated script.",
                        path,
                        check=PYTHON_HYGIENE_MAIN_GUARD,
                    )

                if re.search(r"(?<!['\"])breakpoint\(", stripped) or re.search(
                    r"(?<!['\"])(?:pdb|ipdb)\.set_trace\(",
                    stripped,
                ):
                    result.add_error(
                        f"Line {line_number}: Debug breakpoint detected",
                        path,
                        check=PYTHON_HYGIENE_BREAKPOINT,
                    )

                if re.search(r"except\s*:\s*(?:#.*)?$", stripped):
                    result.add_warning(
                        f"Line {line_number}: Bare except detected",
                        path,
                        check=PYTHON_HYGIENE_BARE_EXCEPT,
                    )

                if re.search(r"except\s+Exception\b", stripped):
                    justification = ""
                    if "#" in stripped:
                        justification = stripped.split("#", 1)[1].strip()
                    if len(justification.split()) < 3:
                        result.add_warning(
                            f"Line {line_number}: 'except Exception' requires an inline justification explaining why a broad catch is safe.",
                            path,
                            check=PYTHON_HYGIENE_BROAD_EXCEPTION,
                        )

                if (
                    stripped.startswith("import pdb")
                    or stripped.startswith("import ipdb")
                    or stripped.startswith("from pdb import")
                ):
                    result.add_warning(
                        f"Line {line_number}: Debug import '{stripped.split()[1]}' should be removed before committing.",
                        path,
                        check=PYTHON_HYGIENE_DEBUG_IMPORT,
                    )

                if not is_cli_module and _contains_system_exit(stripped):
                    result.add_warning(
                        f"Line {line_number}: Direct process termination bypasses orchestrator safeguards; use structured exit helpers.",
                        path,
                        check=PYTHON_HYGIENE_SYSTEM_EXIT,
                    )

                if not is_cli_module and _contains_print_call(stripped):
                    if "logger" in lower_stripped or "logging." in lower_stripped:
                        continue
                    if _is_console_print(stripped):
                        continue
                    result.add_warning(
                        f"Line {line_number}: Replace print-style output with structured logging.",
                        path,
                        check=PYTHON_HYGIENE_PRINT,
                    )

    def supports_fix(self) -> bool:
        """Return ``False`` because hygiene issues require manual review."""

        return False


def _contains_system_exit(line: str) -> bool:
    lowered = line.lower()
    for token in ("raise systemexit", "systemexit(", "os._exit"):
        start = lowered.find(token)
        while start != -1:
            if not _is_within_quotes(line, start, start + len(token)):
                return True
            start = lowered.find(token, start + len(token))
    return False


def _is_within_quotes(line: str, start: int, end: int) -> bool:
    in_single = False
    in_double = False
    escape = False
    for idx, char in enumerate(line):
        if idx >= start:
            break
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
    return in_single or in_double


def _is_console_print(line: str) -> bool:
    if ".print(" not in line:
        return False
    prefix = line.split(".print(", 1)[0]
    lowered = prefix.lower()
    allowed_receivers = (
        "console",
        "self.console",
        "get_console_manager",
        "rich",
    )
    return any(receiver in lowered for receiver in allowed_receivers)


def _contains_print_call(line: str) -> bool:
    for pattern in (r"print\s*\(", r"pprint\s*\("):
        for match in re.finditer(pattern, line):
            start, end = match.span()
            if start > 0 and (line[start - 1].isalnum() or line[start - 1] in {"_", "."}):
                continue
            if not _is_within_quotes(line, start, end):
                return True
    return False


@dataclass(slots=True)
class SchemaCheck:
    """Validate that exported schema documentation matches tool metadata."""

    name: str = "schema"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Compare generated schema artefacts with the current tool schema."""

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
        """Return ``False`` because regeneration requires an external command."""

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
        """Resolve ``path`` relative to :attr:`root` when necessary."""

        return path if path.is_absolute() else (self.root / path).resolve()


@dataclass(frozen=True, slots=True)
class QualityCheckerOptions:
    """Optional parameters used to configure :class:`QualityChecker`."""

    license_policy: LicensePolicy | None = None
    license_overrides: LicenseConfig | Mapping[str, object] | None = None
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
        """Execute configured quality checks and return their aggregated result."""

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
        """Return a mapping of available check names to their implementations."""

        return dict(self._available_checks)

    # ------------------------------------------------------------------
    def _filter_files(self, files: Sequence[Path]) -> list[Path]:
        """Return ``files`` with duplicates and excluded paths removed."""

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
        """Return whether ``path`` should be excluded from quality checks."""

        try:
            relative = path.relative_to(self.root)
        except ValueError:
            relative = Path(path.name)
        if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
            return True
        relative_str = str(relative)
        return any(fnmatch(relative_str, pattern) for pattern in self.quality.skip_globs)

    def _resolve_path(self, path: Path) -> Path:
        """Resolve user-provided ``path`` relative to the project root."""

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
        """Return resolved explicit files specified via options."""

        if not self._options.files:
            return None
        return [self._resolve_path(path) for path in self._options.files]


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
    """Fail when attempting to operate on a protected branch."""

    result = QualityCheckResult()
    branch = _current_branch(root)
    if branch and branch in set(quality.protected_branches):
        result.add_error(f"Branch '{branch}' is protected. Create a feature branch before pushing.")
    return result


def _current_branch(root: Path) -> str | None:
    """Return the current git branch for *root* or ``None`` on failure."""

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
    """Return ``path`` relative to ``root`` when possible."""

    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _is_textual_candidate(path: Path) -> bool:
    """Return ``True`` when ``path`` likely contains textual contents."""

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
