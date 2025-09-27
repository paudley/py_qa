# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Security scan CLI command."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import typer

from ..constants import PY_QA_DIR_NAME
from ..logging import emoji, warn
from ..security import SecurityScanner, SecurityScanResult, get_staged_files
from .utils import filter_py_qa_paths


def security_scan_command(
    files: list[Path] | None = typer.Argument(
        None,
        metavar="[FILES...]",
        help="Specific files to scan.",
    ),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    staged: bool = typer.Option(
        True,
        "--staged/--no-staged",
        help="Include staged files when no explicit files are provided.",
    ),
    no_bandit: bool = typer.Option(
        False,
        "--no-bandit",
        help="Skip running bandit static analysis.",
    ),
    no_emoji: bool = typer.Option(False, "--no-emoji", help="Disable emoji in output."),
) -> None:
    """Run security scans across the project."""
    root_path = root.resolve()
    target_candidates = list(_resolve_security_targets(files, root_path, staged))
    target_files, ignored_py_qa = filter_py_qa_paths(target_candidates, root_path)
    use_emoji = not no_emoji
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

    scanner = SecurityScanner(root=root_path, use_emoji=use_emoji, use_bandit=not no_bandit)
    result = scanner.run(list(target_files))
    exit_code = _report_security_findings(result, use_emoji=use_emoji)
    raise typer.Exit(code=exit_code)


def _resolve_security_targets(
    files: Sequence[Path] | None,
    root: Path,
    staged: bool,
) -> tuple[Path, ...]:
    if files:
        return tuple(path.resolve() for path in files)
    if staged:
        return tuple(get_staged_files(root))
    return ()


def _report_security_findings(result: SecurityScanResult, *, use_emoji: bool) -> int:
    emitted_header = _emit_secret_and_pii_findings(result, use_emoji=use_emoji)
    emitted_bandit = _emit_bandit_summary(result)
    if result.findings:
        if emitted_header or emitted_bandit:
            typer.echo("")
        typer.echo(
            f"{emoji('❌ ', use_emoji)}Security scan found {result.findings} potential issue(s)".strip(),
        )
        return 1
    typer.echo(f"{emoji('✅ ', use_emoji)}No security issues detected".strip())
    return 0


def _emit_secret_and_pii_findings(result: SecurityScanResult, *, use_emoji: bool) -> bool:
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
    for entry in lines:
        typer.echo(f"    {entry}")
