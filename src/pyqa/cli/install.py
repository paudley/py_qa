# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Implementation of the `pyqa install` command."""

from __future__ import annotations

from pathlib import Path

import typer

from ..installs import InstallSummary, install_dev_environment
from ..logging import fail, info, ok
from ..process_utils import SubprocessExecutionError
from .options import InstallOptions


def install_command(
    root: Path = typer.Option(
        Path.cwd(),
        "--root",
        "-r",
        help="Project root to bootstrap.",
    ),
    include_optional: bool = typer.Option(
        True,
        "--include-optional/--no-include-optional",
        help="Install optional typing stubs when their runtime packages are present.",
    ),
    generate_stubs: bool = typer.Option(
        True,
        "--generate-stubs/--no-generate-stubs",
        help="Generate stub skeletons for installed runtime packages.",
    ),
    emoji: bool = typer.Option(
        True,
        "--emoji/--no-emoji",
        help="Toggle emoji in CLI output.",
    ),
) -> None:
    """Install development dependencies and optional typing artefacts."""
    resolved_root = root.resolve()
    options = InstallOptions(include_optional=include_optional, generate_stubs=generate_stubs)

    info(
        f"Installing py-qa development dependencies in {resolved_root}",
        use_emoji=emoji,
    )

    try:
        summary: InstallSummary = install_dev_environment(
            resolved_root,
            include_optional=options.include_optional,
            generate_stubs=options.generate_stubs,
            on_optional_stub=(
                (lambda dep: info(f"Adding optional typing stub {dep}", use_emoji=emoji))
                if options.include_optional
                else None
            ),
            on_stub_generation=(
                (lambda module: info(f"Generating stubs for {module}", use_emoji=emoji))
                if options.generate_stubs
                else None
            ),
        )
    except FileNotFoundError as exc:
        fail(str(exc), use_emoji=emoji)
        raise typer.Exit(code=1) from exc
    except SubprocessExecutionError as exc:  # pragma: no cover - exercised via CLI tests
        fail(str(exc), use_emoji=emoji)
        raise typer.Exit(code=exc.returncode or 1) from exc

    if summary.optional_stub_packages and not options.include_optional:
        info(
            "Optional stub packages detected but not installed due to CLI flags.",
            use_emoji=emoji,
        )

    ok("Dependency installation complete.", use_emoji=emoji)
    raise typer.Exit(code=0)


__all__ = ["install_command"]
