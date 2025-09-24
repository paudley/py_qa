# SPDX-License-Identifier: MIT
"""Data models used by tool environment preparation."""

from __future__ import annotations

from typing import Literal, Mapping, Sequence

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
    ) -> "PreparedCommand":
        return cls(
            cmd=list(cmd),
            env={str(k): str(v) for k, v in (env or {}).items()},
            version=version,
            source=source,
        )


__all__ = ["PreparedCommand"]
