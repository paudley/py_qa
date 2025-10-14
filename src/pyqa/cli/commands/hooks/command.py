# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for installing git hooks."""

from __future__ import annotations

from typing import Annotated

import typer

from ...core.shared import CLIError, Depends, build_cli_logger, register_callback
from ...core.typer_ext import TyperAppConfig, create_typer
from .models import HookCLIOptions, build_hook_options
from .services import emit_hooks_summary, perform_installation

hooks_app = create_typer(
    config=TyperAppConfig(
        name="install-hooks",
        help_text="Install py-qa git hooks (pre-commit, pre-push, commit-msg).",
        invoke_without_command=True,
    ),
)


@register_callback(hooks_app, invoke_without_command=True)
def main(
    options: Annotated[HookCLIOptions, Depends(build_hook_options)],
) -> None:
    """Install py-qa git hooks for the current repository.

    Args:
        options: Normalized CLI options containing installer directives.

    Raises:
        typer.Exit: Always raised to terminate the command with an exit status.
    """

    logger = build_cli_logger(emoji=options.emoji)
    try:
        result = perform_installation(options, logger=logger)
    except CLIError as exc:
        raise typer.Exit(code=exc.exit_code) from exc

    emit_hooks_summary(result, options, logger=logger)
    raise typer.Exit(code=0)


__all__ = ["hooks_app"]
