# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Security scanning utilities for secret detection and lint integration."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CompletedProcess
from typing import Final

from ..core.logging import fail, info, ok, warn
from ..core.runtime.process import CommandOptions, run_command

# Patterns for secret detection (compiled lazily)
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"api[_-]?key.*=.*['\"][a-zA-Z0-9]{20,}['\"]",
        r"api[_-]?secret.*=.*['\"][a-zA-Z0-9]{20,}['\"]",
        r"access[_-]?token.*=.*['\"][a-zA-Z0-9]{20,}['\"]",
        r"auth[_-]?token.*=.*['\"][a-zA-Z0-9]{20,}['\"]",
        r"bearer.*['\"][a-zA-Z0-9]{20,}['\"]",
        r"AKIA[0-9A-Z]{16}",
        r"aws[_-]?access[_-]?key[_-]?id.*=.*['\"][A-Z0-9]{20}['\"]",
        r"aws[_-]?secret[_-]?access[_-]?key.*=.*['\"][a-zA-Z0-9/+=]{40}['\"]",
        r"AIza[0-9A-Za-z\-_]{35}",
        r"service[_-]?account.*\.json",
        r"gh[opsu]_[a-zA-Z0-9]{36}",
        r"github[_-]?token.*=.*['\"][a-zA-Z0-9]{40}['\"]",
        r"password.*=.*['\"][^'\"]{8,}['\"]",
        r"passwd.*=.*['\"][^'\"]{8,}['\"]",
        r"pwd.*=.*['\"][^'\"]{8,}['\"]",
        r"secret.*=.*['\"][^'\"]{8,}['\"]",
        r"-----BEGIN RSA PRIVATE KEY-----",
        r"-----BEGIN OPENSSH PRIVATE KEY-----",
        r"-----BEGIN DSA PRIVATE KEY-----",
        r"-----BEGIN EC PRIVATE KEY-----",
        r"-----BEGIN PGP PRIVATE KEY BLOCK-----",
        r"postgres://[^:]+:[^@]+@",
        r"mysql://[^:]+:[^@]+@",
        r"mongodb://[^:]+:[^@]+@",
        r"redis://[^:]+:[^@]+@",
        r"xox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}",
        r"secret.*=.*['\"][A-Za-z0-9+/]{20,}={0,2}['\"]",
        r"eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]*",
    )
]

_ENTROPY_PATTERN = re.compile(r"['\"][A-Za-z0-9+/]{32,}['\"]")

_PII_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[0-9]{3}-[0-9]{2}-[0-9]{4}"),
    re.compile(r"[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}"),
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
]

_DOC_ENV_PATTERNS = re.compile(
    r"os\.environ|process\.env|ENV\[|getenv\(|-e [A-Z_]+=|export [A-Z_]+=|\$\{?[A-Z_]+\}?",
)

_MARKDOWN_SUFFIX: Final[str] = ".md"

_SKIP_PII_FILES = (
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
)

_SKIP_PII_PATH_FRAGMENTS = (
    ".github/workflows/",
    "scripts/hooks/",
)

_TMP_FILE_SUFFIXES = (
    ".bak",
    ".backup",
    ".tmp",
    ".temp",
    ".swp",
    "~",
    ".env",
)

_BANDIT_SUCCESS_CODES: Final[set[int]] = {0, 1}
_BANDIT_REPORT_SUFFIX: Final[str] = ".json"
_BINARY_SNIFF_BYTES: Final[int] = 4096
_NULL_BYTE: Final[bytes] = b"\x00"
BANDIT_HIGH_TOKEN: Final[str] = "HIGH"
BANDIT_HIGH_SYMBOL: Final[str] = "❌"
BANDIT_WARNING_SYMBOL: Final[str] = "⚠️"
BANDIT_GUIDANCE: Final[str] = "Run 'bandit -r src/ --format screen' for full details."


@dataclass
class SecurityScanResult:
    """Aggregated results from the security scan."""

    findings: int = 0
    secret_files: dict[Path, list[str]] = field(default_factory=dict)
    pii_files: dict[Path, list[str]] = field(default_factory=dict)
    temp_files: list[Path] = field(default_factory=list)
    bandit_issues: dict[str, int] | None = None
    bandit_samples: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def register_secret(self, path: Path, message: str) -> None:
        """Record a potential secret finding for ``path``."""

        self.secret_files.setdefault(path, []).append(message)
        self.findings += 1

    def register_pii(self, path: Path, message: str) -> None:
        """Record potential personally identifiable information for ``path``."""

        self.pii_files.setdefault(path, []).append(message)
        self.findings += 1

    def register_temp(self, path: Path) -> None:
        """Record a temporary or backup file that should not be committed."""

        self.temp_files.append(path)
        self.findings += 1

    def register_bandit(self, metrics: dict[str, int], samples: list[str]) -> None:
        """Record results from a Bandit security scan."""

        self.bandit_issues = metrics
        self.bandit_samples = samples
        self.findings += max(sum(metrics.values()), 1)


@dataclass
class SecurityScanner:
    """Perform static secret and vulnerability scanning for a project."""

    root: Path
    use_emoji: bool = True
    use_bandit: bool = True
    excludes_file: Path | None = None

    def run(self, files: Sequence[Path]) -> SecurityScanResult:
        """Run configured security checks against ``files``."""

        result = SecurityScanResult()
        resolved_files = self._resolve_files(files)

        info("🔍 Scanning files for secrets and credentials...", use_emoji=self.use_emoji)
        for path in resolved_files:
            self._scan_file(path, result)

        if self.use_bandit:
            self._run_bandit(result)

        return result

    # ------------------------------------------------------------------
    def _resolve_files(self, files: Sequence[Path]) -> list[Path]:
        """Resolve ``files`` relative to :attr:`root` and drop missing entries."""

        resolved: list[Path] = []
        for file in files:
            candidate = (self.root / file).resolve() if not file.is_absolute() else file
            if candidate.exists():
                resolved.append(candidate)
        return resolved

    def _should_exclude(self, path: Path) -> bool:
        """Return whether ``path`` matches the exclude configuration."""

        excludes_path = self.excludes_file or (self.root / ".security-check-excludes")
        if not excludes_path.exists():
            return False
        relative = path.relative_to(self.root)
        patterns = [line.strip() for line in excludes_path.read_text().splitlines()]
        for pattern in patterns:
            if not pattern or pattern.startswith("#"):
                continue
            if relative.match(pattern) or relative.name == pattern:
                return True
        return False

    def _is_binary(self, path: Path) -> bool:
        """Return ``True`` when ``path`` appears to contain binary data."""

        try:
            handle = path.open("rb")
        except OSError:
            return False
        with handle:
            chunk = handle.read(_BINARY_SNIFF_BYTES)
        return _NULL_BYTE in chunk

    def _read_text(self, path: Path) -> str:
        """Return the textual contents of ``path`` or an empty string on failure."""

        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _scan_file(self, path: Path, result: SecurityScanResult) -> None:
        """Scan ``path`` for secrets, PII, temp files, and aggregate findings."""

        if not self._is_scan_candidate(path):
            return

        text = self._read_text(path)
        if not text:
            return

        relative_path = path.relative_to(self.root)
        lines = text.splitlines()

        secrets = self._scan_secret_patterns(path, relative_path, lines, result)
        entropy = self._scan_entropy(relative_path, lines, result)
        temp_flag = self._scan_temp_files(relative_path, result)
        pii_flag = self._scan_pii(path, relative_path, lines, result)

        if secrets or entropy:
            fail(f"Potential secrets found in {relative_path}", use_emoji=self.use_emoji)
        if temp_flag:
            warn(
                f"Temporary/backup file should not be committed: {relative_path}",
                use_emoji=self.use_emoji,
            )
        if pii_flag:
            warn(f"Potential PII found in {relative_path}", use_emoji=self.use_emoji)

    def _is_scan_candidate(self, path: Path) -> bool:
        """Return ``True`` when ``path`` is eligible for scanning."""

        if not path.is_file() or self._should_exclude(path):
            return False
        if path.suffix in {".lock", ".json"} and path.name.endswith("lock.json"):
            return False
        if self._is_binary(path):
            return False
        return True

    def _scan_secret_patterns(
        self,
        path: Path,
        relative_path: Path,
        lines: Sequence[str],
        result: SecurityScanResult,
    ) -> bool:
        """Scan ``lines`` for secret patterns and record findings."""

        found = False
        for pattern in _SECRET_PATTERNS:
            matches = _match_pattern(pattern, lines)
            if not matches or _should_skip_markdown(pattern, path, matches):
                continue
            for line_no, snippet in matches[:3]:
                result.register_secret(relative_path, f"line {line_no}: {snippet.strip()}")
            found = True
        return found

    def _scan_entropy(
        self,
        relative_path: Path,
        lines: Sequence[str],
        result: SecurityScanResult,
    ) -> bool:
        """Scan ``lines`` for high-entropy strings indicative of secrets."""

        matches = _match_pattern(_ENTROPY_PATTERN, lines)
        filtered = _filter_entropy(matches)
        if not filtered:
            return False
        for line_no, snippet in filtered[:3]:
            result.register_secret(
                relative_path,
                f"high entropy string at line {line_no}: {snippet.strip()}",
            )
        return True

    def _scan_temp_files(self, relative_path: Path, result: SecurityScanResult) -> bool:
        """Identify temporary or backup files that should not be committed."""

        if relative_path.suffix in _TMP_FILE_SUFFIXES or relative_path.name.endswith("~"):
            result.register_temp(relative_path)
            return True
        return False

    def _scan_pii(
        self,
        path: Path,
        relative_path: Path,
        lines: Sequence[str],
        result: SecurityScanResult,
    ) -> bool:
        """Scan ``lines`` for PII matches and record potential findings."""

        if _should_skip_pii(path):
            return False
        found = False
        for pattern in _PII_PATTERNS:
            matches = _match_pattern(pattern, lines, case_sensitive=True)
            matches = _filter_comments(matches)
            if not matches:
                continue
            for line_no, snippet in matches[:3]:
                result.register_pii(relative_path, f"line {line_no}: {snippet.strip()}")
            found = True
        return found

    # ------------------------------------------------------------------
    def _run_bandit(self, result: SecurityScanResult) -> None:
        src_dir = self.root / "src"
        if not src_dir.is_dir():
            info(
                "No src/ directory found, skipping bandit scan",
                use_emoji=self.use_emoji,
            )
            return

        if not shutil.which("bandit"):
            warn(
                "Bandit is not installed. Install via 'uv sync --group dev' to enable python security scanning.",
                use_emoji=self.use_emoji,
            )
            return

        info("Running bandit security analysis...", use_emoji=self.use_emoji)
        with _temporary_report_path(_BANDIT_REPORT_SUFFIX) as report_path:
            completed = self._invoke_bandit(src_dir, report_path)
            if completed.returncode == 0:
                ok(
                    "Bandit scan completed - no security issues found",
                    use_emoji=self.use_emoji,
                )
                return
            if completed.returncode not in _BANDIT_SUCCESS_CODES:
                self._log_bandit_failure(completed)
                return

            metrics, samples = self._summarise_bandit_report(report_path)
            self._report_bandit_findings(metrics, samples, result)

    def _invoke_bandit(self, src_dir: Path, report_path: Path) -> CompletedProcess[str]:
        """Run Bandit against ``src_dir`` capturing the JSON report at ``report_path``."""

        options = CommandOptions(capture_output=True, check=False)
        return run_command(
            [
                "bandit",
                "-r",
                str(src_dir),
                "-f",
                "json",
                "-o",
                str(report_path),
                "--quiet",
            ],
            options=options,
        )

    def _log_bandit_failure(self, completed: CompletedProcess[str]) -> None:
        """Emit log messages when Bandit exits with an unexpected error."""

        warn(
            f"Bandit scan encountered an error (exit code {completed.returncode}).",
            use_emoji=self.use_emoji,
        )
        stderr = completed.stderr.strip()
        if stderr:
            warn(stderr, use_emoji=self.use_emoji)

    def _summarise_bandit_report(self, report_path: Path) -> tuple[dict[str, int], list[str]]:
        """Return metrics and representative samples from the Bandit report."""

        data = json.loads(report_path.read_text(encoding="utf-8"))
        totals = data.get("metrics", {}).get("_totals", {})
        metrics = {
            "SEVERITY.HIGH": int(totals.get("SEVERITY.HIGH", 0)),
            "SEVERITY.MEDIUM": int(totals.get("SEVERITY.MEDIUM", 0)),
            "SEVERITY.LOW": int(totals.get("SEVERITY.LOW", 0)),
        }
        samples = [
            f"{item.get('filename')}:{item.get('line_number')} - {item.get('issue_text')}"
            for item in data.get("results", [])[:3]
        ]
        return metrics, samples

    def _report_bandit_findings(
        self,
        metrics: dict[str, int],
        samples: list[str],
        result: SecurityScanResult,
    ) -> None:
        """Record Bandit findings and emit a textual summary."""

        result.register_bandit(metrics, samples)
        fail("Bandit found security vulnerabilities", use_emoji=self.use_emoji)
        for level, count in metrics.items():
            symbol = BANDIT_HIGH_SYMBOL if BANDIT_HIGH_TOKEN in level else BANDIT_WARNING_SYMBOL
            suffix = level.rsplit(".", maxsplit=1)[-1].title()
            info(f"  {symbol} {suffix} severity: {count}", use_emoji=self.use_emoji)
        if samples:
            info("\n  Sample issues:", use_emoji=self.use_emoji)
            for sample in samples:
                info(f"    {sample}", use_emoji=self.use_emoji)
        info(f"\n  {BANDIT_GUIDANCE}", use_emoji=self.use_emoji)


def _match_pattern(
    pattern: re.Pattern[str],
    lines: Sequence[str],
    *,
    case_sensitive: bool = False,
) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    compiled = pattern if case_sensitive else re.compile(pattern.pattern, re.IGNORECASE)
    for idx, line in enumerate(lines, start=1):
        if compiled.search(line):
            matches.append((idx, line))
    return matches


def _should_skip_pii(path: Path) -> bool:
    """Return ``True`` when PII scanning should skip ``path``."""

    if path.name in _SKIP_PII_FILES:
        return True
    return any(fragment in path.as_posix() for fragment in _SKIP_PII_PATH_FRAGMENTS)


def _should_skip_markdown(
    _pattern: re.Pattern[str],
    path: Path,
    matches: list[tuple[int, str]],
) -> bool:
    """Return ``True`` when Markdown matches likely reference docs rather than secrets."""

    if path.suffix.lower() != _MARKDOWN_SUFFIX:
        return False
    return all(_DOC_ENV_PATTERNS.search(line) for _, line in matches)


def _filter_entropy(matches: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Filter entropy matches to remove obvious non-secret content."""

    filtered: list[tuple[int, str]] = []
    for idx, line in matches:
        if re.search(r"sha256|md5|hash|digest|test|example|sample|hexsha", line, re.IGNORECASE):
            continue
        if line.strip().startswith("#") or line.strip().startswith("//"):
            continue
        filtered.append((idx, line))
    return filtered


def _filter_comments(matches: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Return matches excluding comments to reduce false positives."""

    return [
        (idx, line) for idx, line in matches if not line.lstrip().startswith("#") and not line.lstrip().startswith("//")
    ]


@contextmanager
def _temporary_report_path(suffix: str) -> Iterator[Path]:
    """Yield a temporary file path that is cleaned up afterwards."""

    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    path = Path(handle.name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def get_staged_files(root: Path) -> list[Path]:
    """Return files with staged changes in git."""
    try:
        options = CommandOptions(capture_output=True, check=False, cwd=root)
        completed = run_command(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            options=options,
        )
    except FileNotFoundError:  # git not installed
        return []
    if completed.returncode != 0:
        return []
    return [root / line.strip() for line in completed.stdout.splitlines() if line.strip()]
