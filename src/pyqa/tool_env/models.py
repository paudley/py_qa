# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Data models used by tool environment preparation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PreparedCommand(BaseModel):
    """Command ready for execution including environment metadata."""

    model_config = ConfigDict(validate_assignment=True)

    cmd: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    version: str | None
    source: Literal["system", "local", "project"]

    @classmethod
    def from_parts(
        cls,
        *,
        cmd: Sequence[str],
        env: Mapping[str, str] | None,
        version: str | None,
        source: Literal["system", "local", "project"],
    ) -> PreparedCommand:
        """Construct a :class:`PreparedCommand` from primitive components.

        Args:
            cmd: Command sequence ready for execution.
            env: Optional environment overrides.
            version: Detected tool version, if any.
            source: Origin of the command (system, local, or project).

        Returns:
            PreparedCommand: Normalised command data class.
        """

        return cls(
            cmd=list(cmd),
            env={str(k): str(v) for k, v in (env or {}).items()},
            version=version,
            source=source,
        )


__all__ = ["PreparedCommand"]
