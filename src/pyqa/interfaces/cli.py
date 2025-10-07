# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces describing CLI command orchestration."""

# pylint: disable=too-few-public-methods -- Protocol definitions intentionally expose minimal method surfaces.

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CliCommand(Protocol):
    """Represent a Typer-compatible command callable."""

    def __call__(self, *args: Any, **kwargs: Any) -> int | None:
        """Execute the command and optionally return an exit code."""
        raise NotImplementedError


@runtime_checkable
class CliCommandFactory(Protocol):
    """Factory used to construct CLI commands with injected dependencies."""

    def create(self, argv: Sequence[str] | None = None) -> CliCommand:
        """Return a CLI command configured for the provided arguments."""
        raise NotImplementedError
