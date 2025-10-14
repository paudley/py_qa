# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces describing CLI command orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ParamSpec, Protocol, runtime_checkable

P = ParamSpec("P")


@runtime_checkable
class CliCommand(Protocol[P]):
    """Represent a Typer-compatible command callable."""

    @property
    def name(self) -> str:
        """Return the human-friendly name of the command."""
        raise NotImplementedError("CliCommand.name must be implemented")

    # suppression_valid: lint=internal-signatures CLI protocols expose Typer-compatible call signatures so implementations can accept arbitrary options without wrapper glue.
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> int | None:
        """Execute the command and optionally return an exit code."""
        raise NotImplementedError


@runtime_checkable
class CliCommandFactory(Protocol[P]):
    """Factory used to construct CLI commands with injected dependencies."""

    @property
    def command_name(self) -> str:
        """Return the name of the command constructed by the factory."""
        raise NotImplementedError("CliCommandFactory.command_name must be implemented")

    def create(self, argv: Sequence[str] | None = None) -> CliCommand[P]:
        """Return a CLI command configured for the provided arguments."""
        raise NotImplementedError
