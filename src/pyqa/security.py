# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Security scanning utilities for secret detection and lint integration."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .logging import fail, info, ok, warn

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

_DOC_ENV_PATTERNS = re.compile(r"os\.environ|process\.env|ENV\[|getenv\(|-e [A-Z_]+=|export [A-Z_]+=|\$\{?[A-Z_]+\}?")

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
        self.secret_files.setdefault(path, []).append(message)
        self.findings += 1

    def register_pii(self, path: Path, message: str) -> None:
        self.pii_files.setdefault(path, []).append(message)
        self.findings += 1

    def register_temp(self, path: Path) -> None:
        self.temp_files.append(path)
        self.findings += 1

    def register_bandit(self, metrics: dict[str, int], samples: list[str]) -> None:
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
        resolved: list[Path] = []
        for file in files:
            candidate = (self.root / file).resolve() if not file.is_absolute() else file
            if candidate.exists():
                resolved.append(candidate)
        return resolved

    def _should_exclude(self, path: Path) -> bool:
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
        try:
            chunk = path.read_bytes()
        except OSError:
            return False
        return b"\x00" in chunk

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _scan_file(self, path: Path, result: SecurityScanResult) -> None:
        if not path.is_file() or self._should_exclude(path):
            return
        if path.suffix in {".lock", ".json"} and path.name.endswith("lock.json"):
            return
        if self._is_binary(path):
            return

        text = self._read_text(path)
        if not text:
            return

        relative_path = path.relative_to(self.root)
        lines = text.splitlines()

        # Secret patterns
        for pattern in _SECRET_PATTERNS:
            matches = _match_pattern(pattern, lines)
            if matches and not _should_skip_markdown(pattern, path, matches):
                for line_no, snippet in matches[:3]:
                    result.register_secret(relative_path, f"line {line_no}: {snippet.strip()}")
                fail(
                    f"Potential secrets found in {relative_path}",
                    use_emoji=self.use_emoji,
                )

        # High entropy strings
        matches = _match_pattern(_ENTROPY_PATTERN, lines)
        matches = _filter_entropy(matches)
        if matches:
            for line_no, snippet in matches[:3]:
                result.register_secret(
                    relative_path,
                    f"high entropy string at line {line_no}: {snippet.strip()}",
                )
            fail(
                f"High entropy strings found in {relative_path}",
                use_emoji=self.use_emoji,
            )

        # Temp/backup files
        if relative_path.suffix in _TMP_FILE_SUFFIXES or relative_path.name.endswith("~"):
            result.register_temp(relative_path)
            warn(
                f"Temporary/backup file should not be committed: {relative_path}",
                use_emoji=self.use_emoji,
            )

        # PII patterns
        if not _should_skip_pii(path):
            for pattern in _PII_PATTERNS:
                pii_matches = _match_pattern(pattern, lines, case_sensitive=True)
                pii_matches = _filter_comments(pii_matches)
                if pii_matches:
                    for line_no, snippet in pii_matches[:3]:
                        result.register_pii(relative_path, f"line {line_no}: {snippet.strip()}")
                    warn(
                        f"Potential PII found in {relative_path}",
                        use_emoji=self.use_emoji,
                    )

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
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
            report_path = Path(handle.name)
        try:
            completed = subprocess.run(
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
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                ok(
                    "Bandit scan completed - no security issues found",
                    use_emoji=self.use_emoji,
                )
                return
            if completed.returncode not in {0, 1}:
                warn(
                    f"Bandit scan encountered an error (exit code {completed.returncode}).",
                    use_emoji=self.use_emoji,
                )
                warn(completed.stderr.strip(), use_emoji=self.use_emoji)
                return

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
            result.register_bandit(metrics, samples)
            fail("Bandit found security vulnerabilities", use_emoji=self.use_emoji)
            for level, count in metrics.items():
                symbol = "❌" if "HIGH" in level else "⚠️"
                print(f"  {symbol} {level.split('.')[-1].title()} severity: {count}")
            if samples:
                print("\n  Sample issues:")
                for sample in samples:
                    print(f"    {sample}")
            print("\n  Run 'bandit -r src/ --format screen' for full details.")
        finally:
            report_path.unlink(missing_ok=True)


def _match_pattern(
    pattern: re.Pattern[str], lines: Sequence[str], *, case_sensitive: bool = False
) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    compiled = pattern if case_sensitive else re.compile(pattern.pattern, re.IGNORECASE)
    for idx, line in enumerate(lines, start=1):
        if compiled.search(line):
            matches.append((idx, line))
    return matches


def _should_skip_pii(path: Path) -> bool:
    if path.name in _SKIP_PII_FILES:
        return True
    return any(fragment in path.as_posix() for fragment in _SKIP_PII_PATH_FRAGMENTS)


def _should_skip_markdown(pattern: re.Pattern[str], path: Path, matches: list[tuple[int, str]]) -> bool:
    if path.suffix.lower() != ".md":
        return False
    return all(_DOC_ENV_PATTERNS.search(line) for _, line in matches)


def _filter_entropy(matches: list[tuple[int, str]]) -> list[tuple[int, str]]:
    filtered: list[tuple[int, str]] = []
    for idx, line in matches:
        if re.search(r"sha256|md5|hash|digest|test|example|sample|hexsha", line, re.IGNORECASE):
            continue
        if line.strip().startswith("#") or line.strip().startswith("//"):
            continue
        filtered.append((idx, line))
    return filtered


def _filter_comments(matches: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [
        (idx, line) for idx, line in matches if not line.lstrip().startswith("#") and not line.lstrip().startswith("//")
    ]


def get_staged_files(root: Path) -> list[Path]:
    """Return files with staged changes in git."""

    try:
        completed = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            cwd=root,
            check=False,
        )
        if completed.returncode != 0:
            return []
        return [root / line.strip() for line in completed.stdout.splitlines() if line.strip()]
    except FileNotFoundError:  # git not installed
        return []
