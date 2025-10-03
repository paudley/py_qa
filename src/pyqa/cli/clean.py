# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for sparkling clean cleanup."""

from __future__ import annotations

from typing import Annotated

import typer

from ..clean import sparkly_clean
from ._clean_cli_models import CleanCLIOptions, build_clean_options
from ._clean_cli_services import (
    emit_dry_run_summary,
    emit_py_qa_warning,
    load_clean_config,
)
from .shared import CLIError, Depends, build_cli_logger, register_callback
from .typer_ext import create_typer

clean_app = create_typer(
    name="sparkly-clean",
    help="Remove temporary build/cache artefacts.",
    invoke_without_command=True,
)


@register_callback(clean_app, invoke_without_command=True)
def main(
    options: Annotated[CleanCLIOptions, Depends(build_clean_options)],
) -> None:
    """Execute the sparkly-clean command."""

    logger = build_cli_logger(emoji=options.emoji)
    try:
        config = load_clean_config(options.root, logger=logger)
    except CLIError as exc:
        raise typer.Exit(code=exc.exit_code) from exc

    result = sparkly_clean(
        options.root,
        config=config,
        extra_patterns=options.extra_patterns,
        extra_trees=options.extra_trees,
        dry_run=options.dry_run,
    )

    emit_py_qa_warning(result, options.root, logger=logger)
    if options.dry_run:
        emit_dry_run_summary(result, logger=logger)
    raise typer.Exit(code=0)


__all__ = ["clean_app"]
