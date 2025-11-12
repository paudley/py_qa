# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Security scan CLI command."""

from __future__ import annotations

from pyqa.cli.protocols import TyperLike

from ...core.shared import register_command
from .command import security_scan_command

__all__ = ["register"]


def register(app: TyperLike) -> None:
    """Register the security scan command with ``app``.

    Args:
        app: Typer-compatible application receiving the security command registration.
    """

    register_command(app, security_scan_command, name="security-scan")
