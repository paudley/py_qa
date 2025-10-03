# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Implementation of the `pyqa install` command."""

from __future__ import annotations

from typing import Annotated

import typer

from ..installs import InstallSummary, install_dev_environment
from ..logging import fail, info, ok
from ..process_utils import SubprocessExecutionError
from ._install_cli_models import InstallCLIOptions, build_install_options
from .shared import Depends


def install_command(
    options: Annotated[InstallCLIOptions, Depends(build_install_options)],
) -> None:
    """Install development dependencies and optional typing artefacts."""
    resolved_root = options.root
    install_options = options.install
    use_emoji = options.use_emoji

    info(
        f"Installing py-qa development dependencies in {resolved_root}",
        use_emoji=use_emoji,
    )

    try:
        summary: InstallSummary = install_dev_environment(
            resolved_root,
            include_optional=install_options.include_optional,
            generate_stubs=install_options.generate_stubs,
            on_optional_stub=(
                (lambda dep: info(f"Adding optional typing stub {dep}", use_emoji=use_emoji))
                if install_options.include_optional
                else None
            ),
            on_stub_generation=(
                (lambda module: info(f"Generating stubs for {module}", use_emoji=use_emoji))
                if install_options.generate_stubs
                else None
            ),
        )
    except FileNotFoundError as exc:
        fail(str(exc), use_emoji=use_emoji)
        raise typer.Exit(code=1) from exc
    except SubprocessExecutionError as exc:  # pragma: no cover - exercised via CLI tests
        fail(str(exc), use_emoji=use_emoji)
        raise typer.Exit(code=exc.returncode or 1) from exc

    if summary.optional_stub_packages and not install_options.include_optional:
        info(
            "Optional stub packages detected but not installed due to CLI flags.",
            use_emoji=use_emoji,
        )

    ok("Dependency installation complete.", use_emoji=use_emoji)
    raise typer.Exit(code=0)


__all__ = ["install_command"]
