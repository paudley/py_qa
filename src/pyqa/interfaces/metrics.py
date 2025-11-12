# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Protocols describing reusable metric payloads."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .core import JsonValue


@runtime_checkable
class FileMetricsProtocol(Protocol):
    """Expose the minimal interface required to persist per-file metrics."""

    line_count: int
    """Number of lines recorded for the file."""

    suppressions: Mapping[str, int]
    """Count of inline suppression markers keyed by tool."""

    @abstractmethod
    def to_payload(self) -> Mapping[str, JsonValue]:
        """Return the metrics encoded as a JSON-compatible mapping.

        Returns:
            Mapping[str, JsonValue]: Serialised metrics used by caches and reports.
        """

    @classmethod
    @abstractmethod
    def from_payload(cls, payload: Mapping[str, JsonValue] | None) -> FileMetricsProtocol:
        """Reconstruct metrics from the payload produced by :meth:`to_payload`.

        Args:
            payload: Serialised metrics mapping or ``None`` when unavailable.

        Returns:
            FileMetricsProtocol: Metrics instance populated from ``payload``.
        """


__all__ = ["FileMetricsProtocol"]
