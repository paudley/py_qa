# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Option metadata models for tooling catalog entries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from .errors import CatalogIntegrityError
from .types import JSONValue
from .utils import expect_mapping, expect_string, optional_bool, optional_string, string_array

OptionType: TypeAlias = Literal[
    "string",
    "str",
    "boolean",
    "bool",
    "integer",
    "int",
    "number",
    "float",
    "array",
    "object",
    "mapping",
    "path",
    "list[str]",
]
_OPTION_TYPE_ALIASES: Final[dict[str, OptionType]] = {
    "string": "string",
    "str": "string",
    "boolean": "boolean",
    "bool": "boolean",
    "integer": "integer",
    "int": "integer",
    "number": "number",
    "float": "number",
    "array": "list[str]",
    "list[str]": "list[str]",
    "object": "mapping",
    "mapping": "mapping",
    "path": "path",
}


def normalize_option_type(value: JSONValue | None, *, context: str) -> OptionType:
    """Return the canonical option type string used by catalog metadata.

    Args:
        value: Raw type value sourced from catalog metadata.
        context: Human-readable context used in error messages.

    Returns:
        OptionType: Normalised option type recognised by the runtime.

    Raises:
        CatalogIntegrityError: If the provided value does not describe a known type.

    """

    raw = expect_string(value, key="type", context=context).lower()
    if raw not in _OPTION_TYPE_ALIASES:
        raise CatalogIntegrityError(f"{context}: unknown option type '{raw}'")
    return _OPTION_TYPE_ALIASES[raw]


@dataclass(frozen=True, slots=True)
class CliOptionMetadata:
    """CLI representation details for catalog options."""

    flag: str | None
    short_flag: str | None
    multiple: bool

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> CliOptionMetadata:
        """Create CLI metadata from JSON data.

        Args:
            data: Mapping describing CLI surface details.
            context: Human-readable context used in error messages.

        Returns:
            CliOptionMetadata: Materialised CLI metadata definition.

        Raises:
            CatalogIntegrityError: If the mapping contains invalid values.

        """

        flag_value = optional_string(data.get("flag"), key="flag", context=context)
        short_flag_value = optional_string(data.get("shortFlag"), key="shortFlag", context=context)
        multiple_value = optional_bool(
            data.get("multiple"),
            key="multiple",
            context=context,
            default=False,
        )
        return CliOptionMetadata(
            flag=flag_value,
            short_flag=short_flag_value,
            multiple=multiple_value,
        )


@dataclass(frozen=True, slots=True)
class OptionDefinition:
    """Declarative tool option exposed to configuration surfaces."""

    name: str
    option_type: OptionType
    description: str | None
    default: JSONValue
    cli: CliOptionMetadata | None
    choices: tuple[str, ...]
    aliases: tuple[str, ...]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> OptionDefinition:
        """Create an ``OptionDefinition`` from JSON data.

        Args:
            data: Mapping describing a single option definition.
            context: Human-readable context used in error messages.

        Returns:
            OptionDefinition: Frozen option definition instance.

        Raises:
            CatalogIntegrityError: If required option metadata is missing or invalid.

        """

        name_value = expect_string(data.get("name"), key="name", context=context)
        option_type_value = normalize_option_type(data.get("type"), context=context)
        description_value = optional_string(
            data.get("description"),
            key="description",
            context=context,
        )
        default_value = data.get("default")
        cli_data = data.get("cli")
        cli_value = (
            CliOptionMetadata.from_mapping(
                expect_mapping(cli_data, key="cli", context=context),
                context=f"{context}.cli",
            )
            if isinstance(cli_data, Mapping)
            else None
        )
        choices_value = string_array(data.get("choices"), key="choices", context=context)
        aliases_value = string_array(data.get("aliases"), key="aliases", context=context)
        return OptionDefinition(
            name=name_value,
            option_type=option_type_value,
            description=description_value,
            default=default_value,
            cli=cli_value,
            choices=choices_value,
            aliases=aliases_value,
        )


@dataclass(frozen=True, slots=True)
class OptionGroupDefinition:
    """Grouped options for documentation purposes."""

    title: str
    options: tuple[OptionDefinition, ...]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> OptionGroupDefinition:
        """Create an ``OptionGroupDefinition`` from JSON data.

        Args:
            data: Mapping describing a documentation group of options.
            context: Human-readable context used in error messages.

        Returns:
            OptionGroupDefinition: Frozen group definition.

        Raises:
            CatalogIntegrityError: If the mapping is malformed or missing required fields.

        """

        title_value = expect_string(data.get("title"), key="title", context=context)
        options_value = options_array(data.get("options"), key="options", context=context)
        return OptionGroupDefinition(title=title_value, options=options_value)


@dataclass(frozen=True, slots=True)
class OptionDocumentationBundle:
    """Documentation helpers for describing tool options."""

    groups: tuple[OptionGroupDefinition, ...]
    entries: tuple[OptionDefinition, ...]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> OptionDocumentationBundle:
        """Create an ``OptionDocumentationBundle`` from JSON data.

        Args:
            data: Mapping containing bundle metadata.
            context: Human-readable context used in error messages.

        Returns:
            OptionDocumentationBundle: Frozen documentation bundle.

        Raises:
            CatalogIntegrityError: If group or entry metadata is malformed.

        """

        groups_data = data.get("groups")
        groups_value: tuple[OptionGroupDefinition, ...] = ()
        if isinstance(groups_data, Sequence) and not isinstance(
            groups_data,
            (str, bytes, bytearray),
        ):
            group_items: list[OptionGroupDefinition] = []
            for index, element in enumerate(groups_data):
                element_mapping = expect_mapping(element, key=f"groups[{index}]", context=context)
                group_items.append(
                    OptionGroupDefinition.from_mapping(
                        element_mapping,
                        context=f"{context}.groups[{index}]",
                    ),
                )
            groups_value = tuple(group_items)
        entries_value = options_array(data.get("entries"), key="entries", context=context)
        return OptionDocumentationBundle(groups=groups_value, entries=entries_value)


def options_array(
    value: JSONValue | None,
    *,
    key: str,
    context: str,
) -> tuple[OptionDefinition, ...]:
    """Return a tuple of option definitions.

    Args:
        value: Raw JSON value that should describe a list of options.
        key: Name of the key currently being parsed.
        context: Human-readable context used in error messages.

    Returns:
        tuple[OptionDefinition, ...]: Immutable option definitions referenced by the caller.

    Raises:
        CatalogIntegrityError: If the value is not a valid sequence of option mappings.

    """

    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an array of option objects")
    options: list[OptionDefinition] = []
    for index, element in enumerate(value):
        element_mapping = expect_mapping(element, key=f"{key}[{index}]", context=context)
        options.append(
            OptionDefinition.from_mapping(
                element_mapping,
                context=f"{context}.{key}[{index}]",
            ),
        )
    return tuple(options)


__all__: Final[tuple[str, ...]] = (
    "CliOptionMetadata",
    "OptionDefinition",
    "OptionDocumentationBundle",
    "OptionGroupDefinition",
    "OptionType",
    "normalize_option_type",
    "options_array",
)
