# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Python hygiene quality check implementation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .base import QualityCheckResult, QualityContext

PYTHON_HYGIENE_CATEGORY: Final[str] = "python-hygiene"
PYTHON_HYGIENE_BREAKPOINT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:debug-breakpoint"
PYTHON_HYGIENE_BARE_EXCEPT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:bare-except"
PYTHON_HYGIENE_MAIN_GUARD: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:module-main"
PYTHON_HYGIENE_BROAD_EXCEPTION: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:broad-exception"
PYTHON_HYGIENE_DEBUG_IMPORT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:debug-import"
PYTHON_HYGIENE_SYSTEM_EXIT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:system-exit"
PYTHON_HYGIENE_PRINT: Final[str] = f"{PYTHON_HYGIENE_CATEGORY}:print"
PYTHON_FILE_SUFFIXES: Final[tuple[str, ...]] = (".py", ".pyi")
TESTS_DIRECTORY_TOKEN: Final[str] = "tests"
CLI_COMPONENT_TOKENS: Final[tuple[str, ...]] = ("cli", "commands")
LOGGER_REFERENCE_TOKENS: Final[tuple[str, ...]] = ("logger", "logging.")
DEBUG_IMPORT_PREFIXES: Final[tuple[str, ...]] = ("import pdb", "import ipdb", "from pdb import")
SYSTEM_EXIT_TOKENS: Final[tuple[str, ...]] = ("raise systemexit", "systemexit(", "os._exit")
CONSOLE_RECEIVER_TOKENS: Final[tuple[str, ...]] = (
    "console",
    "self.console",
    "get_console_manager",
    "rich",
)
MAIN_GUARD_PATTERN: Final[re.Pattern[str]] = re.compile(r"if __name__ == ['\"]__main__['\"]\s*:")
BREAKPOINT_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!['\"])breakpoint\(")
TRACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!['\"])(?:pdb|ipdb)\.set_trace\(")
BARE_EXCEPT_PATTERN: Final[re.Pattern[str]] = re.compile(r"except\s*:\s*(?:#.*)?$")
BROAD_EXCEPTION_PATTERN: Final[re.Pattern[str]] = re.compile(r"except\s+Exception\b")
PRINT_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"print\s*\("),
    re.compile(r"pprint\s*\("),
)
MIN_JUSTIFICATION_WORDS: Final[int] = 3
COMMENT_DELIMITER: Final[str] = "#"
ESCAPE_CHAR: Final[str] = "\\"
SINGLE_QUOTE: Final[str] = "'"
DOUBLE_QUOTE: Final[str] = '"'
PRINT_METHOD_SENTINEL: Final[str] = ".print("
ATTRIBUTE_BOUNDARY_CHARS: Final[frozenset[str]] = frozenset({"_", "."})


@dataclass(slots=True)
class _HygieneScanState:
    """Track per-file state while scanning for hygiene violations."""

    found_main_guard: bool = False


@dataclass(frozen=True, slots=True)
class HygieneLineContext:
    """Describe metadata for a Python source line under analysis."""

    path: Path
    stripped: str
    line_number: int
    is_cli_module: bool


@dataclass(slots=True)
class PythonHygieneCheck:
    """Enforce Python hygiene rules by scanning source files."""

    name: str = "python"

    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Scan Python files for common hygiene violations.

        Args:
            ctx: Quality execution context describing files and configuration.
            result: Aggregated result used to record hygiene findings.
        """

        for path in self._target_files(ctx.files):
            content = self._load_content(path, result)
            if content is None:
                continue
            relative_parts = self._relative_parts(path, ctx.root)
            if self._should_skip_file(relative_parts):
                continue
            is_cli_module = self._is_cli_module(relative_parts)
            self._scan_lines(path, content, is_cli_module, result)

    def supports_fix(self) -> bool:
        """Report that hygiene issues require manual review.

        Returns:
            bool: Always ``False`` because fixes are not automated.
        """

        return False

    def _target_files(self, files: Sequence[Path]) -> list[Path]:
        """Return files eligible for hygiene scanning.

        Args:
            files: Candidate file list supplied by the orchestrator.

        Returns:
            list[Path]: Subset containing Python source files.
        """

        return [path for path in files if path.suffix in PYTHON_FILE_SUFFIXES]

    def _load_content(self, path: Path, result: QualityCheckResult) -> str | None:
        """Return decoded file content or ``None`` when reading fails.

        Args:
            path: File being read from disk.
            result: Result collector used to record read failures.

        Returns:
            str | None: Text content if available; otherwise ``None``.
        """

        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result.add_warning(
                f"Unable to read Python file: {exc}",
                path,
                check=PYTHON_HYGIENE_CATEGORY,
            )
            return None

    def _relative_parts(self, path: Path, root: Path) -> tuple[str, ...]:
        """Return path components relative to ``root`` when possible.

        Args:
            path: Candidate file path.
            root: Repository root for relative comparisons.

        Returns:
            tuple[str, ...]: Path components relative to ``root`` when derivable.
        """

        try:
            return path.relative_to(root).parts
        except ValueError:
            return path.parts

    def _should_skip_file(self, parts: tuple[str, ...]) -> bool:
        """Return ``True`` when the file should be excluded from checks.

        Args:
            parts: Path components describing the candidate file.

        Returns:
            bool: ``True`` when the file resides in excluded locations.
        """

        return TESTS_DIRECTORY_TOKEN in parts

    def _is_cli_module(self, parts: tuple[str, ...]) -> bool:
        """Return ``True`` when ``parts`` describe a CLI command module.

        Args:
            parts: Path components describing the candidate file.

        Returns:
            bool: ``True`` when the file should be treated as a CLI module.
        """

        return all(component in parts for component in CLI_COMPONENT_TOKENS)

    def _scan_lines(
        self,
        path: Path,
        content: str,
        is_cli_module: bool,
        result: QualityCheckResult,
    ) -> None:
        """Iterate file lines and record hygiene issues.

        Args:
            path: File path under analysis.
            content: File content split into lines.
            is_cli_module: Whether the file belongs to the CLI package.
            result: Result collector used to record hygiene issues.
        """

        state = _HygieneScanState()
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            context = HygieneLineContext(
                path=path,
                stripped=stripped,
                line_number=line_number,
                is_cli_module=is_cli_module,
            )
            self._analyse_line(
                context=context,
                state=state,
                result=result,
            )

    def _analyse_line(
        self,
        *,
        context: HygieneLineContext,
        state: _HygieneScanState,
        result: QualityCheckResult,
    ) -> None:
        """Analyse a single line of Python source for hygiene issues.

        Args:
            context: Metadata describing the line under analysis.
            state: Mutable scan state maintained across lines.
            result: Aggregated result used to record hygiene findings.
        """

        stripped = context.stripped
        lowered = stripped.lower()
        if not state.found_main_guard and MAIN_GUARD_PATTERN.match(stripped):
            state.found_main_guard = True
            result.add_warning(
                (
                    "Line "
                    f"{context.line_number}: Module defines a __main__ execution block; move the entry "
                    "point to a dedicated script."
                ),
                context.path,
                check=PYTHON_HYGIENE_MAIN_GUARD,
            )

        if BREAKPOINT_PATTERN.search(stripped) or TRACE_PATTERN.search(stripped):
            result.add_error(
                f"Line {context.line_number}: Debug breakpoint detected",
                context.path,
                check=PYTHON_HYGIENE_BREAKPOINT,
            )

        if BARE_EXCEPT_PATTERN.search(stripped):
            result.add_warning(
                f"Line {context.line_number}: Bare except detected",
                context.path,
                check=PYTHON_HYGIENE_BARE_EXCEPT,
            )

        if BROAD_EXCEPTION_PATTERN.search(stripped):
            self._handle_broad_exception(context.path, stripped, context.line_number, result)

        if any(stripped.startswith(prefix) for prefix in DEBUG_IMPORT_PREFIXES):
            result.add_warning(
                (
                    f"Line {context.line_number}: Debug import '{stripped.split()[1]}' should be removed "
                    "before committing."
                ),
                context.path,
                check=PYTHON_HYGIENE_DEBUG_IMPORT,
            )

        if not context.is_cli_module and _contains_system_exit(stripped):
            result.add_warning(
                (
                    "Line "
                    f"{context.line_number}: Direct process termination bypasses orchestrator safeguards; use "
                    "structured exit helpers."
                ),
                context.path,
                check=PYTHON_HYGIENE_SYSTEM_EXIT,
            )

        if not context.is_cli_module and _contains_print_call(stripped):
            if any(token in lowered for token in LOGGER_REFERENCE_TOKENS):
                return
            if _is_console_print(stripped):
                return
            result.add_warning(
                f"Line {context.line_number}: Replace print-style output with structured logging.",
                context.path,
                check=PYTHON_HYGIENE_PRINT,
            )

    def _handle_broad_exception(
        self,
        path: Path,
        stripped: str,
        line_number: int,
        result: QualityCheckResult,
    ) -> None:
        """Record a warning when a broad exception lacks justification.

        Args:
            path: File path under analysis.
            stripped: Original source line containing the broad except block.
            line_number: One-based line number associated with ``stripped``.
            result: Aggregated result used to record hygiene findings.
        """

        justification = ""
        if COMMENT_DELIMITER in stripped:
            justification = stripped.split(COMMENT_DELIMITER, 1)[1].strip()
        if len(justification.split()) >= MIN_JUSTIFICATION_WORDS:
            return
        result.add_warning(
            (
                "Line "
                f"{line_number}: Broad Exception catch requires an inline justification explaining why it is "
                "safe."
            ),
            path,
            check=PYTHON_HYGIENE_BROAD_EXCEPTION,
        )


def _contains_system_exit(line: str) -> bool:
    """Return ``True`` when ``line`` contains a system-exit invocation.

    Args:
        line: Source line inspected for exit calls.

    Returns:
        bool: ``True`` when a system-exit call appears outside string literals.
    """

    lowered = line.lower()
    for token in SYSTEM_EXIT_TOKENS:
        pattern = re.escape(token)
        for match in re.finditer(pattern, lowered):
            if not _is_within_quotes(line, match.start()):
                return True
    return False


def _is_within_quotes(line: str, start: int) -> bool:
    """Return ``True`` when the segment lies within quoted text.

    Args:
        line: Source line inspected for quoted segments.
        start: Index within ``line`` used to determine quoting state.

    Returns:
        bool: ``True`` when the segment is enclosed within single or double quotes.
    """

    in_single = False
    in_double = False
    escape = False
    for idx, char in enumerate(line):
        if idx >= start:
            break
        if escape:
            escape = False
            continue
        if char == ESCAPE_CHAR:
            escape = True
            continue
        if char == SINGLE_QUOTE and not in_double:
            in_single = not in_single
        elif char == DOUBLE_QUOTE and not in_single:
            in_double = not in_double
    return in_single or in_double


def _is_console_print(line: str) -> bool:
    """Return ``True`` when ``line`` represents an approved console print.

    Args:
        line: Source line inspected for console printing patterns.

    Returns:
        bool: ``True`` when the line invokes a sanctioned console print helper.
    """

    if PRINT_METHOD_SENTINEL not in line:
        return False
    prefix = line.split(PRINT_METHOD_SENTINEL, 1)[0]
    lowered = prefix.lower()
    return any(receiver in lowered for receiver in CONSOLE_RECEIVER_TOKENS)


def _contains_print_call(line: str) -> bool:
    """Return ``True`` when ``line`` performs a print-style call.

    Args:
        line: Source line inspected for print-style invocations.

    Returns:
        bool: ``True`` when a print-style call appears outside quoted text.
    """

    for pattern in PRINT_PATTERNS:
        for match in re.finditer(pattern, line):
            start = match.start()
            if start > 0 and (line[start - 1].isalnum() or line[start - 1] in ATTRIBUTE_BOUNDARY_CHARS):
                continue
            if not _is_within_quotes(line, start):
                return True
    return False


__all__ = [
    "PythonHygieneCheck",
    "PYTHON_HYGIENE_CATEGORY",
    "PYTHON_HYGIENE_BREAKPOINT",
    "PYTHON_HYGIENE_BARE_EXCEPT",
    "PYTHON_HYGIENE_MAIN_GUARD",
    "PYTHON_HYGIENE_BROAD_EXCEPTION",
    "PYTHON_HYGIENE_DEBUG_IMPORT",
    "PYTHON_HYGIENE_SYSTEM_EXIT",
    "PYTHON_HYGIENE_PRINT",
]

HYGIENE_EXPORTS: Final[tuple[str, ...]] = tuple(__all__)
