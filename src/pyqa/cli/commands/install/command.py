# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Implementation of the `pyqa install` command."""

from __future__ import annotations

from typing import Annotated

import typer

from pyqa.runtime.installers import InstallSummary, install_dev_environment

from ....core.logging import fail, info, ok
from ....core.runtime.process import SubprocessExecutionError
from ...core.shared import Depends
from .models import InstallCLIOptions, build_install_options


def install_command(
    options: Annotated[InstallCLIOptions, Depends(build_install_options)],
) -> None:
    """Install development dependencies and optional typing artefacts.

    Args:
        options: Structured CLI options controlling installation behaviour.

    Raises:
        typer.Exit: Always raised to terminate Typer execution with the
            appropriate exit status.
    """
    resolved_root = options.root
    install_options = options.install
    use_emoji = options.use_emoji

    info(
        f"Installing pyqa-lint development dependencies in {resolved_root}",
        use_emoji=use_emoji,
    )

    try:
        summary: InstallSummary = install_dev_environment(
            resolved_root,
            include_optional=install_options.include_optional,
            generate_typing_modules=install_options.generate_typing_modules,
            on_optional_package=(
                (lambda dep: info(f"Adding optional typing package {dep}", use_emoji=use_emoji))
                if install_options.include_optional
                else None
            ),
            on_module_generation=(
                (lambda module: info(f"Generating typing scaffolds for {module}", use_emoji=use_emoji))
                if install_options.generate_typing_modules
                else None
            ),
        )
    except FileNotFoundError as exc:
        fail(str(exc), use_emoji=use_emoji)
        raise typer.Exit(code=1) from exc
    except SubprocessExecutionError as exc:  # pragma: no cover - exercised via CLI tests
        fail(str(exc), use_emoji=use_emoji)
        raise typer.Exit(code=exc.returncode or 1) from exc

    if summary.optional_typing_packages and not install_options.include_optional:
        info(
            "Optional typing packages detected but not installed due to CLI flags.",
            use_emoji=use_emoji,
        )

    ok("Dependency installation complete.", use_emoji=use_emoji)
    raise typer.Exit(code=0)


__all__ = ["install_command"]
