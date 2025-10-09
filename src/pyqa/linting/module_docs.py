# SPDX-License-Identifier: MIT
"""Phase-9 linter ensuring package documentation files are present."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity

from .base import InternalLintReport, build_internal_report

_EXPECTED_SECTIONS: Final[tuple[str, ...]] = (
    "## Overview",
    "## Patterns",
    "## DI Seams",
    "## Extension Points",
)


def run_pyqa_module_doc_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool = True,
) -> InternalLintReport:
    """Validate presence and minimal content of module documentation files.

    Args:
        state: Prepared lint execution context describing the workspace.
        emit_to_logger: Historic compatibility switch (unused).

    Returns:
        ``InternalLintReport`` containing documentation violations.
    """

    _ = emit_to_logger
    root = state.options.target_options.root.resolve()
    package_root = root / "src" / "pyqa"
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    touched_files: set[Path] = set()

    for package in _iter_packages(package_root):
        doc_path = package.joinpath(_doc_filename(package_root, package))
        if not doc_path.exists():
            diagnostics.append(_build_diagnostic(root, doc_path, "Missing module documentation file."))
            stdout_lines.append(f"{doc_path}: missing module documentation file")
            touched_files.add(doc_path)
            continue
        content = doc_path.read_text(encoding="utf-8")
        for section in _EXPECTED_SECTIONS:
            if section not in content:
                diagnostics.append(_build_diagnostic(root, doc_path, f"Missing documentation section '{section}'"))
                stdout_lines.append(f"{doc_path}: missing documentation section {section}")
                touched_files.add(doc_path)

    return build_internal_report(
        tool="pyqa-module-docs",
        stdout=stdout_lines,
        diagnostics=diagnostics,
        files=sorted(touched_files),
    )


def _iter_packages(package_root: Path) -> list[Path]:
    """Return package directories beneath ``package_root``."""

    packages: list[Path] = []
    for init_file in package_root.rglob("__init__.py"):
        package_dir = init_file.parent
        if package_dir == package_root:
            continue
        packages.append(package_dir)
    return packages


def _doc_filename(package_root: Path, package: Path) -> str:
    """Return the expected documentation filename for ``package``."""

    relative = package.relative_to(package_root)
    parts = [part.upper() for part in relative.parts if part]
    return "_".join(parts) + ".md"


def _build_diagnostic(root: Path, doc_path: Path, message: str) -> Diagnostic:
    """Return a diagnostic anchored to ``doc_path`` with ``message``."""

    try:
        relative = doc_path.relative_to(root)
    except ValueError:
        relative = doc_path
    return Diagnostic(
        file=str(relative),
        line=1,
        column=None,
        severity=Severity.WARNING,
        message=message,
        tool="pyqa-module-docs",
        code="pyqa:module-docs",
    )


__all__ = ["run_pyqa_module_doc_linter"]
