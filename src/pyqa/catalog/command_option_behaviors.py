# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Behaviour implementations powering catalog command option mappings."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

from pyqa.tools.base import ToolContext
from pyqa.tools.builtin_helpers import _as_bool, _resolve_path, _settings_list

from .types import JSONValue


class _OptionBehavior(Protocol):
    """Define behaviour contracts responsible for appending CLI fragments."""

    def extend_command(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Extend ``command`` to reflect ``value`` within the current context.

        Args:
            ctx: Tool execution context providing settings and metadata.
            command: Mutable command list that will be emitted downstream.
            value: Raw configuration value that should influence the command.
        """

    def __call__(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Apply the behaviour using callable syntax.

        Args:
            ctx: Tool execution context forwarded to ``extend_command``.
            command: Mutable command list forwarded to the behaviour.
            value: Option value forwarded unchanged.
        """


@dataclass(slots=True, frozen=True)
class _ArgsOptionBehavior:
    """Render list-like option values into CLI arguments."""

    flag: str | None
    join_separator: str | None

    def extend_command(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Append CLI arguments emitted by list-style configuration values.

        Args:
            ctx: Tool execution context (unused for args behaviour).
            command: Mutable command list to mutate.
            value: Raw configuration value assigned to the option.
        """

        del ctx
        values = _settings_list(value)
        if not values:
            return
        append_value = partial(_append_flagged, command, flag=self.flag)
        if self.join_separator is not None:
            combined = self.join_separator.join(str(entry) for entry in values)
            append_value(combined)
            return
        for entry in values:
            append_value(str(entry))

    def __call__(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Apply ``extend_command`` to handle callable usage.

        Args:
            ctx: Tool execution context forwarded to ``extend_command``.
            command: Mutable command list forwarded to the behaviour.
            value: Option value forwarded unchanged.
        """

        self.extend_command(ctx, command, value)


@dataclass(slots=True, frozen=True)
class _PathOptionBehavior:
    """Resolve path-like option values relative to the project root."""

    flag: str | None
    literal_values: tuple[str, ...]

    def extend_command(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Append resolved filesystem paths for ``value``.

        Args:
            ctx: Tool execution context providing filesystem roots.
            command: Mutable command list.
            value: Raw option value containing path(s).
        """

        entries: tuple[JSONValue, ...] = (
            tuple(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else (value,)
        )
        append_value = partial(_append_flagged, command, flag=self.flag)
        for entry in entries:
            if entry is None:
                continue
            entry_text = str(entry)
            resolved = (
                entry_text
                if isinstance(entry, (str, Path)) and entry_text in self.literal_values
                else str(_resolve_path(ctx.root, entry))
            )
            append_value(resolved)

    def __call__(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Apply ``extend_command`` to handle callable usage.

        Args:
            ctx: Tool execution context forwarded to ``extend_command``.
            command: Mutable command list forwarded to the behaviour.
            value: Option value forwarded unchanged.
        """

        self.extend_command(ctx, command, value)


@dataclass(slots=True, frozen=True)
class _ValueOptionBehavior:
    """Render scalar option values as CLI segments."""

    flag: str | None

    def extend_command(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Append scalar option values to ``command``.

        Args:
            ctx: Tool execution context (unused for scalar values).
            command: Mutable command list to mutate.
            value: Raw option value to append.
        """

        del ctx
        append_value = partial(_append_flagged, command, flag=self.flag)
        append_value(str(value))

    def __call__(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Apply ``extend_command`` to handle callable usage.

        Args:
            ctx: Tool execution context forwarded to ``extend_command``.
            command: Mutable command list forwarded to the behaviour.
            value: Option value forwarded unchanged.
        """

        self.extend_command(ctx, command, value)


@dataclass(slots=True, frozen=True)
class _FlagOptionBehavior:
    """Manage boolean flag options based on configuration values."""

    flag: str | None
    negate_flag: str | None

    def extend_command(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Append positive or negated flags based on ``value``.

        Args:
            ctx: Tool execution context (unused for flag behaviour).
            command: Mutable command list.
            value: Raw option value controlling flag emission.
        """

        del ctx
        coerced_value = _as_bool(value)
        should_enable = bool(value) if coerced_value is None else coerced_value
        selected_flag = self.flag if should_enable else self.negate_flag
        if selected_flag:
            command.append(selected_flag)

    def __call__(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Apply ``extend_command`` to handle callable usage.

        Args:
            ctx: Tool execution context forwarded to ``extend_command``.
            command: Mutable command list forwarded to the behaviour.
            value: Option value forwarded unchanged.
        """

        self.extend_command(ctx, command, value)


@dataclass(slots=True, frozen=True)
class _RepeatFlagBehavior:
    """Repeat a flag N times based on an integral configuration value."""

    flag: str
    negate_flag: str | None

    def extend_command(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Repeat the configured flag according to ``value``.

        Args:
            ctx: Tool execution context (unused for repeat flag behaviour).
            command: Mutable command list.
            value: Raw option value defining the repeat count.
        """

        del ctx
        count = _coerce_repeat_count(value)
        if count > 0:
            command.extend([self.flag] * count)
            return
        if self.negate_flag:
            command.append(self.negate_flag)

    def __call__(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Apply :meth:`extend_command` via callable syntax.

        Args:
            ctx: Tool execution context forwarded to ``extend_command``.
            command: Mutable command list forwarded to the behaviour.
            value: Option value forwarded unchanged.
        """

        self.extend_command(ctx, command, value)


def _append_flagged(command: list[str], value: str, *, flag: str | None) -> None:
    """Append ``value`` to ``command`` and prepend ``flag`` when provided.

    Args:
        command: Command list receiving the appended values.
        value: CLI argument emitted for the option value.
        flag: Optional flag to prepend before ``value``.
    """

    if flag:
        command.append(flag)
    command.append(value)


def _coerce_repeat_count(value: JSONValue) -> int:
    """Return a numeric repeat count derived from ``value``.

    Args:
        value: Raw catalog configuration value describing the repetition count.

    Returns:
        int: Non-negative repetition count resolved from ``value``.
    """

    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0


__all__ = [
    "_OptionBehavior",
    "_ArgsOptionBehavior",
    "_PathOptionBehavior",
    "_ValueOptionBehavior",
    "_FlagOptionBehavior",
    "_RepeatFlagBehavior",
]
