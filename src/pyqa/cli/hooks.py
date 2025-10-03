# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for installing git hooks."""

from __future__ import annotations

from typing import Annotated

import typer

from ._hooks_cli_models import Depends, HookCLIOptions, build_hook_options
from ._hooks_cli_services import emit_hooks_summary, perform_installation
from .shared import CLIError, build_cli_logger, register_callback
from .typer_ext import create_typer

hooks_app = create_typer(
    name="install-hooks",
    help="Install py-qa git hooks (pre-commit, pre-push, commit-msg).",
    invoke_without_command=True,
)


@register_callback(hooks_app, invoke_without_command=True)
def main(
    options: Annotated[HookCLIOptions, Depends(build_hook_options)],
) -> None:
    """Install py-qa git hooks for the current repository.

    Args:
        options: Normalized CLI options containing installer directives.

    Returns:
        None. The function exits the Typer application with status information.
    """

    logger = build_cli_logger(emoji=options.emoji)
    try:
        result = perform_installation(options, logger=logger)
    except CLIError as exc:
        raise typer.Exit(code=exc.exit_code) from exc

    emit_hooks_summary(result, options, logger=logger)
    raise typer.Exit(code=0)


__all__ = ["hooks_app"]
