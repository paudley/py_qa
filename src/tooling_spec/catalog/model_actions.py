# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Action metadata models for tooling catalog entries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .errors import CatalogIntegrityError
from .model_references import CommandDefinition, ParserDefinition
from .types import JSONValue
from .utils import (
    expect_mapping,
    optional_bool,
    optional_number,
    optional_string,
    string_array,
    string_mapping,
)


@dataclass(frozen=True, slots=True)
class ActionExecution:
    """Capture execution behaviour for a tool action."""

    append_files: bool
    is_fix: bool
    ignore_exit: bool
    timeout_seconds: float | None
    env: Mapping[str, str]
    filters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Represent an executable catalog action backed by strategies."""

    name: str
    description: str | None
    execution: ActionExecution
    command: CommandDefinition
    parser: ParserDefinition | None

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> ActionDefinition:
        """Create an ``ActionDefinition`` from JSON data.

        Args:
            data: Mapping containing action configuration.
            context: Human-readable context used in error messages.

        Returns:
            ActionDefinition: Frozen action definition.

        Raises:
            CatalogIntegrityError: If required action fields are missing or invalid.

        """

        name_value = optional_string(data.get("name"), key="name", context=context)
        if name_value is None:
            raise CatalogIntegrityError(f"{context}: action requires a 'name'")
        description_value = optional_string(
            data.get("description"),
            key="description",
            context=context,
        )
        append_files_value = optional_bool(
            data.get("appendFiles"),
            key="appendFiles",
            context=context,
            default=True,
        )
        is_fix_value = optional_bool(data.get("isFix"), key="isFix", context=context, default=False)
        ignore_exit_value = optional_bool(
            data.get("ignoreExit"),
            key="ignoreExit",
            context=context,
            default=False,
        )
        timeout_value = optional_number(
            data.get("timeoutSeconds"),
            key="timeoutSeconds",
            context=context,
        )
        env_value = string_mapping(data.get("env"), key="env", context=context)
        filters_value = string_array(data.get("filters"), key="filters", context=context)
        command_data = expect_mapping(data.get("command"), key="command", context=context)
        command_value = CommandDefinition.from_mapping(command_data, context=f"{context}.command")
        parser_data = data.get("parser")
        parser_value = (
            ParserDefinition.from_mapping(
                expect_mapping(parser_data, key="parser", context=context),
                context=f"{context}.parser",
            )
            if isinstance(parser_data, Mapping)
            else None
        )
        execution = ActionExecution(
            append_files=append_files_value,
            is_fix=is_fix_value,
            ignore_exit=ignore_exit_value,
            timeout_seconds=timeout_value,
            env=env_value,
            filters=filters_value,
        )
        return ActionDefinition(
            name=name_value,
            description=description_value,
            execution=execution,
            command=command_value,
            parser=parser_value,
        )

    @property
    def append_files(self) -> bool:
        """Return whether file arguments should be appended to the command.

        Returns:
            bool: ``True`` when file arguments should be appended to the command.
        """
        return self.execution.append_files

    @property
    def is_fix(self) -> bool:
        """Return whether the action is expected to modify files in-place.

        Returns:
            bool: ``True`` when the action modifies files.
        """
        return self.execution.is_fix

    @property
    def ignore_exit(self) -> bool:
        """Return whether non-zero exit codes should be ignored.

        Returns:
            bool: ``True`` when non-zero exit codes should be ignored.
        """
        return self.execution.ignore_exit

    @property
    def timeout_seconds(self) -> float | None:
        """Return the maximum execution time allowed for the action.

        Returns:
            float | None: Timeout in seconds, or ``None`` when unset.
        """
        return self.execution.timeout_seconds

    @property
    def env(self) -> Mapping[str, str]:
        """Provide environment variables injected when invoking the action.

        Returns:
            Mapping[str, str]: Environment variables applied to the action.
        """
        return self.execution.env

    @property
    def filters(self) -> tuple[str, ...]:
        """Provide glob-style filters limiting files passed to the action.

        Returns:
            tuple[str, ...]: Glob patterns restricting the file list.
        """
        return self.execution.filters


def actions_array(
    value: JSONValue | None,
    *,
    key: str,
    context: str,
) -> tuple[ActionDefinition, ...]:
    """Return a tuple of action definitions.

    Args:
        value: JSON value that should describe a sequence of action mappings.
        key: Name of the key currently being parsed.
        context: Human-readable context used in error messages.

    Returns:
        tuple[ActionDefinition, ...]: Immutable action definitions referenced by the caller.

    Raises:
        CatalogIntegrityError: If the value is not a valid sequence of action mappings.

    """

    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an array of action objects")
    actions: list[ActionDefinition] = []
    for index, element in enumerate(value):
        element_mapping = expect_mapping(element, key=f"{key}[{index}]", context=context)
        actions.append(
            ActionDefinition.from_mapping(
                element_mapping,
                context=f"{context}.{key}[{index}]",
            ),
        )
    if not actions:
        raise CatalogIntegrityError(f"{context}: '{key}' must contain at least one action")
    return tuple(actions)


__all__ = [
    "ActionDefinition",
    "ActionExecution",
    "actions_array",
]
