# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Security scan CLI command."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Annotated

import typer

from ....compliance.security import SecurityScanner, SecurityScanResult, get_staged_files
from ....constants import PY_QA_DIR_NAME
from ....logging import emoji, warn
from ...core.shared import Depends
from ...core.utils import filter_py_qa_paths
from .models import SecurityCLIOptions, build_security_options


def security_scan_command(
    options: Annotated[SecurityCLIOptions, Depends(build_security_options)],
) -> None:
    """Run security scans across the project.

    Args:
        options: Structured CLI options controlling the security scan.

    Raises:
        typer.Exit: Always raised to terminate the command with an exit status.
    """
    root_path = options.root
    target_candidates = list(_resolve_security_targets(options.files, root_path, options.staged))
    target_files, ignored_py_qa = filter_py_qa_paths(target_candidates, root_path)
    use_emoji = options.use_emoji
    if ignored_py_qa:
        unique = ", ".join(dict.fromkeys(ignored_py_qa))
        warn(
            (
                f"Ignoring path(s) {unique}: '{PY_QA_DIR_NAME}' directories are skipped "
                "unless security-scan runs inside the py_qa workspace."
            ),
            use_emoji=use_emoji,
        )
    if not target_files:
        typer.echo("No files to scan.")
        raise typer.Exit(code=0)

    scanner = SecurityScanner(
        root=root_path,
        use_emoji=use_emoji,
        use_bandit=options.use_bandit,
    )
    result = scanner.run(list(target_files))
    exit_code = _report_security_findings(result, use_emoji=use_emoji)
    raise typer.Exit(code=exit_code)


def _resolve_security_targets(
    files: Sequence[Path] | None,
    root: Path,
    staged: bool,
) -> tuple[Path, ...]:
    """Return target files for the security scan.

    Args:
        files: Explicit file sequence supplied via CLI options.
        root: Repository root directory used to resolve staged files.
        staged: Whether to scan staged files instead of explicit paths.

    Returns:
        tuple[Path, ...]: Tuple of resolved target file paths.
    """

    if files:
        return tuple(path.resolve() for path in files)
    if staged:
        return tuple(get_staged_files(root))
    return ()


def _report_security_findings(result: SecurityScanResult, *, use_emoji: bool) -> int:
    """Emit security findings and return the exit status.

    Args:
        result: Security scan result produced by :class:`SecurityScanner`.
        use_emoji: Flag controlling emoji usage in CLI output.

    Returns:
        int: Exit status for the CLI command.
    """

    emitted_header = _emit_secret_and_pii_findings(result, use_emoji=use_emoji)
    emitted_bandit = _emit_bandit_summary(result)
    if result.findings:
        if emitted_header or emitted_bandit:
            typer.echo("")
        failure_message = (f"{emoji('❌ ', use_emoji)}Security scan found {result.findings} potential issue(s)").strip()
        typer.echo(failure_message)
        return 1
    success_message = f"{emoji('✅ ', use_emoji)}No security issues detected".strip()
    typer.echo(success_message)
    return 0


def _emit_secret_and_pii_findings(result: SecurityScanResult, *, use_emoji: bool) -> bool:
    """Emit detected secrets, PII findings, and temporary file warnings.

    Args:
        result: Security scan result produced by :class:`SecurityScanner`.
        use_emoji: Flag controlling emoji usage in CLI output.

    Returns:
        bool: ``True`` when any findings were emitted.
    """

    emitted = False
    for path, matches in result.secret_files.items():
        if not emitted:
            typer.echo("")
            emitted = True
        typer.echo(f"{emoji('❌ ', use_emoji)}{path}".strip())
        _emit_indented_lines(matches)
    for path, matches in result.pii_files.items():
        if not emitted:
            typer.echo("")
            emitted = True
        typer.echo(f"{emoji('⚠️ ', use_emoji)}Potential PII in {path}".strip())
        _emit_indented_lines(matches)
    for path in result.temp_files:
        if not emitted:
            typer.echo("")
            emitted = True
        typer.echo(f"{emoji('⚠️ ', use_emoji)}Temporary/backup file tracked: {path}".strip())
    return emitted


def _emit_bandit_summary(result: SecurityScanResult) -> bool:
    """Emit a summary of Bandit findings when available.

    Args:
        result: Security scan result produced by :class:`SecurityScanner`.

    Returns:
        bool: ``True`` when Bandit findings were emitted.
    """

    if not result.bandit_issues:
        return False
    typer.echo("")
    typer.echo("Bandit summary:")
    for level, count in sorted(result.bandit_issues.items()):
        label = level.split(".")[-1].title()
        typer.echo(f"  {label}: {count}")
    if result.bandit_samples:
        typer.echo("  Sample issues:")
        for sample in result.bandit_samples:
            typer.echo(f"    {sample}")
    return True


def _emit_indented_lines(lines: Iterable[str]) -> None:
    """Emit indented lines for CLI readability.

    Args:
        lines: Iterable of string lines to output.
    """

    for entry in lines:
        typer.echo(f"    {entry}")
