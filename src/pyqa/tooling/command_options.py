# SPDX-License-Identifier: MIT
"""Command option mapping helpers used by tooling strategies."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_commands_python import (
    _discover_pylint_plugins,
    _python_target_version,
    _python_version_number,
    _python_version_tag,
    _pyupgrade_flag_from_version,
)
from ..tools.builtin_helpers import _as_bool, _resolve_path, _setting, _settings_list
from .catalog.types import JSONValue
from .loader import CatalogIntegrityError

__all__ = [
    "command_option_map",
    "compile_option_mappings",
    "OptionMapping",
    "require_str",
    "require_string_sequence",
]


class OptionKind(str, Enum):
    """Enumerate supported command-option mapping behaviours."""

    VALUE = "value"
    PATH = "path"
    ARGS = "args"
    FLAG = "flag"
    REPEAT_FLAG = "repeatFlag"


class TransformName(str, Enum):
    """Enumerate transforms available to option mappings."""

    PYTHON_VERSION_TAG = "python_version_tag"
    PYTHON_VERSION_NUMBER = "python_version_number"
    PYUPGRADE_FLAG = "pyupgrade_flag"
    STRICTNESS_IS_STRICT = "strictness_is_strict"
    STRICTNESS_IS_LENIENT = "strictness_is_lenient"
    BOOL_TO_YN = "bool_to_yn"
    BOOL_TO_STR = "bool_to_str"


class _OptionBehavior(Protocol):  # pylint: disable=too-few-public-methods
    """Behaviour contract responsible for appending CLI fragments."""

    def extend_command(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Mutate ``command`` to reflect ``value`` in the current context."""


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

        Returns:
            None: The command list is extended in place.

        """

        del ctx
        values = _settings_list(value)
        if not values:
            return
        if self.join_separator is not None:
            combined = self.join_separator.join(str(entry) for entry in values)
            _append_flagged(command, combined, self.flag)
            return
        for entry in values:
            _append_flagged(command, str(entry), self.flag)


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

        Returns:
            None: Paths are appended to ``command`` in place.

        """

        entries: Sequence[JSONValue]
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            entries = cast("Sequence[JSONValue]", value)
        else:
            entries = (value,)
        for entry in entries:
            if entry is None:
                continue
            if isinstance(entry, (str, Path)) and str(entry) in self.literal_values:
                resolved = str(entry)
            else:
                resolved = str(_resolve_path(ctx.root, entry))
            _append_flagged(command, resolved, self.flag)


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

        Returns:
            None: The command list is updated in place.

        """

        del ctx
        _append_flagged(command, str(value), self.flag)


@dataclass(slots=True, frozen=True)
class _FlagOptionBehavior:
    """Toggle boolean flag options based on configuration values."""

    flag: str | None
    negate_flag: str | None

    def extend_command(self, ctx: ToolContext, command: list[str], value: JSONValue) -> None:
        """Append positive or negated flags based on ``value``.

        Args:
            ctx: Tool execution context (unused for flag behaviour).
            command: Mutable command list.
            value: Raw option value controlling flag emission.

        Returns:
            None: Flags are appended directly to ``command``.

        """

        del ctx
        bool_value = _as_bool(value)
        if bool_value is None:
            bool_value = bool(value)
        if bool_value:
            if self.flag:
                command.append(self.flag)
            return
        if self.negate_flag:
            command.append(self.negate_flag)


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

        Returns:
            None: The command list is updated with repeated flags.

        """

        del ctx
        count = _coerce_repeat_count(value)
        if count == 0:
            if self.negate_flag:
                command.append(self.negate_flag)
            return
        command.extend([self.flag] * count)


@dataclass(slots=True, frozen=True)
class _ParsedOptionConfig:
    """Intermediate representation of option configuration values."""

    names: tuple[str, ...]
    kind: OptionKind
    flags: _OptionFlags
    defaults: _OptionDefaults


@dataclass(slots=True, frozen=True)
class _OptionFlags:
    """CLI flag metadata associated with an option."""

    flag: str | None
    join_with: str | None
    negate_flag: str | None
    literal_values: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class _OptionDefaults:
    """Default behaviour metadata for an option."""

    value: JSONValue | None
    reference: str | None
    transform: TransformName | None


@dataclass(slots=True)
class OptionMapping:
    """Declarative mapping between tool settings and CLI arguments."""

    settings: tuple[str, ...]
    behavior: _OptionBehavior
    defaults: _OptionDefaults

    def apply(self, ctx: ToolContext, command: list[str]) -> None:
        """Append CLI fragments derived from the configured option.

        Args:
            ctx: Execution context providing catalog settings and defaults.
            command: Mutable sequence representing the command under
                construction.

        Returns:
            None: The command list is mutated in place.

        """

        value = self._resolve_value(ctx)
        if value is None:
            return
        adjusted = self._apply_transform(value, ctx) if self.defaults.transform else value
        self.behavior.extend_command(ctx, command, adjusted)

    def _resolve_value(self, ctx: ToolContext) -> JSONValue | None:
        """Resolve the value backing this option, honouring defaults.

        Args:
            ctx: Execution context supplying tool settings from the catalog.

        Returns:
            JSONValue | None: Explicit configuration value, derived default, or
            ``None`` when nothing applies.

        """

        value: JSONValue | None = None
        for name in self.settings:
            candidate = cast("JSONValue | None", _setting(ctx.settings, name))
            if candidate is not None:
                value = candidate
                break
        if value is None and self.defaults.value is not None:
            value = self.defaults.value
        if value is None and self.defaults.reference is not None:
            value = _resolve_default_reference(self.defaults.reference, ctx)
        return value

    def _apply_transform(self, value: JSONValue, ctx: ToolContext) -> JSONValue:
        """Apply the configured transform to ``value`` in ``ctx``.

        Args:
            value: Raw option value resolved from settings.
            ctx: Execution context providing additional metadata for transforms.

        Returns:
            JSONValue: Transformed value ready for command emission.

        """

        assert self.defaults.transform is not None
        transformer = _TRANSFORM_HANDLERS[self.defaults.transform]
        return transformer(value, ctx)


@dataclass(slots=True)
class _OptionCommandStrategy(CommandBuilder):
    """Command builder driven by declarative option mappings."""

    base: tuple[str, ...]
    append_files: bool
    options: tuple[OptionMapping, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return the fully rendered CLI command for the current context.

        Args:
            ctx: Tool execution context containing settings, files, and
                configuration defaults.

        Returns:
            Sequence[str]: Final immutable command arguments ready for
            execution.

        """

        command = list(self.base)
        for option in self.options:
            option.apply(ctx, command)
        if self.append_files and ctx.files:
            command.extend(str(path) for path in ctx.files)
        return tuple(command)


def command_option_map(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder that maps catalog options onto CLI arguments.

    Args:
        config: Catalog configuration describing ``base`` arguments, whether to
            ``appendFiles``, and an ``options`` array containing option
            definitions.

    Returns:
        CommandBuilder: Strategy that renders CLI arguments according to the
        catalog definition.

    Raises:
        CatalogIntegrityError: If required configuration keys are missing or
            contain invalid values.

    """

    base_args = require_string_sequence(config, "base", context="command_option_map")
    append_files = bool(config.get("appendFiles", True))
    options_config = cast("JSONValue | None", config.get("options"))
    mappings = compile_option_mappings(
        options_config,
        context="command_option_map.options",
    )
    return _OptionCommandStrategy(
        base=base_args,
        append_files=append_files,
        options=mappings,
    )


def compile_option_mappings(
    options_config: JSONValue | None,
    *,
    context: str,
) -> tuple[OptionMapping, ...]:
    """Translate a catalog ``options`` array into ``OptionMapping`` instances.

    Args:
        options_config: Raw JSON value extracted from catalog configuration.
        context: Human-friendly context string used when raising validation
            errors.

    Returns:
        tuple[OptionMapping, ...]: Sequence of compiled option mappings ready for
        command composition.

    Raises:
        CatalogIntegrityError: If ``options_config`` is not an array of mapping
            objects with the expected fields.

    """

    if options_config is None:
        return ()
    if not isinstance(options_config, Sequence) or isinstance(
        options_config,
        (str, bytes, bytearray),
    ):
        raise CatalogIntegrityError(f"{context}: 'options' must be an array of objects")

    compiled: list[OptionMapping] = []
    for index, raw_option in enumerate(options_config):
        option_context = f"{context}[{index}]"
        if not isinstance(raw_option, Mapping):
            raise CatalogIntegrityError(f"{option_context}: option must be an object")
        parsed = _collect_option_config(raw_option, option_context)
        behavior = _build_option_behavior(parsed, context=option_context)
        compiled.append(
            OptionMapping(
                settings=parsed.names,
                behavior=behavior,
                defaults=parsed.defaults,
            ),
        )
    return tuple(compiled)


def require_string_sequence(
    config: Mapping[str, JSONValue],
    key: str,
    *,
    context: str,
) -> tuple[str, ...]:
    """Return the required sequence of strings for ``key`` in ``config``."""

    value = config.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an array of arguments")
    result = tuple(str(item) for item in value)
    if not result:
        raise CatalogIntegrityError(f"{context}: '{key}' must contain at least one argument")
    return result


def require_str(config: Mapping[str, JSONValue], key: str, *, context: str) -> str:
    """Return the required string value for ``key`` in ``config``."""

    value = config.get(key)
    if not isinstance(value, str):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be a string")
    return value


def _collect_option_config(entry: Mapping[str, Any], context: str) -> _ParsedOptionConfig:
    """Parse option configuration mapping into a typed structure.

    Args:
        entry: Raw option configuration extracted from the catalog.
        context: Context string for error reporting.

    Returns:
        _ParsedOptionConfig: Structured representation of the option config.

    Raises:
        CatalogIntegrityError: If any required field is missing or invalid.

    """

    names = _parse_option_names(entry.get("setting"), context)
    kind = _parse_option_kind(entry.get("type", "value"), context)
    flag = _parse_optional_string(entry.get("flag"), "flag", context)
    join_with = _parse_optional_string(entry.get("joinWith"), "joinWith", context)
    negate_flag = _parse_optional_string(entry.get("negateFlag"), "negateFlag", context)
    literal_values = _parse_literal_values(entry.get("literalValues", ()), context)
    default_value = cast("JSONValue | None", entry.get("default"))
    default_from = _parse_optional_string(entry.get("defaultFrom"), "defaultFrom", context)
    transform = _parse_transform(entry.get("transform"), context)

    flags = _OptionFlags(
        flag=flag,
        join_with=join_with,
        negate_flag=negate_flag,
        literal_values=literal_values,
    )
    defaults = _OptionDefaults(
        value=default_value,
        reference=default_from,
        transform=transform,
    )

    return _ParsedOptionConfig(
        names=names,
        kind=kind,
        flags=flags,
        defaults=defaults,
    )


def _parse_option_names(raw: Any, context: str) -> tuple[str, ...]:
    """Normalise the ``setting`` field into a tuple of option names.

    Args:
        raw: Raw value supplied for the ``setting`` key.
        context: Context string for error messages.

    Returns:
        tuple[str, ...]: Non-empty tuple of setting names.

    Raises:
        CatalogIntegrityError: If ``raw`` is neither a string nor an array of
            strings.

    """

    if isinstance(raw, str):
        names = (raw,)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        names = tuple(str(name) for name in raw if name is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'setting' must be a string or array of strings")
    if not names:
        raise CatalogIntegrityError(f"{context}: 'setting' must provide at least one entry")
    return names


def _parse_option_kind(raw: Any, context: str) -> OptionKind:
    """Map ``type`` entries onto :class:`OptionKind` members.

    Args:
        raw: Raw value describing the option kind.
        context: Context string for error reporting.

    Returns:
        OptionKind: Enum value describing how the option behaves.

    Raises:
        CatalogIntegrityError: If ``raw`` is not a recognised kind.

    """

    if not isinstance(raw, str):
        raise CatalogIntegrityError(f"{context}: 'type' must be a string")
    normalized = raw.strip().lower()
    mapping: dict[str, OptionKind] = {
        "value": OptionKind.VALUE,
        "path": OptionKind.PATH,
        "args": OptionKind.ARGS,
        "flag": OptionKind.FLAG,
        "repeatflag": OptionKind.REPEAT_FLAG,
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise CatalogIntegrityError(f"{context}: unsupported option type '{raw}'") from exc


def _parse_optional_string(raw: Any, field_name: str, context: str) -> str | None:
    """Return a cleaned optional string value when provided.

    Args:
        raw: Raw value to validate.
        field_name: Name of the field being processed.
        context: Context string for error reporting.

    Returns:
        str | None: Cleaned string or ``None`` when absent.

    Raises:
        CatalogIntegrityError: If ``raw`` is not a string when provided.

    """

    if raw is None:
        return None
    if isinstance(raw, str):
        cleaned = raw.strip()
        return cleaned if cleaned else None
    raise CatalogIntegrityError(f"{context}: '{field_name}' must be a string when provided")


def _parse_literal_values(raw: Any, context: str) -> tuple[str, ...]:
    """Return literal values that bypass path resolution.

    Args:
        raw: Raw configuration entry for ``literalValues``.
        context: Context string for error reporting.

    Returns:
        tuple[str, ...]: Tuple of literal string values.

    Raises:
        CatalogIntegrityError: If ``raw`` is neither a string nor an array of
            strings.

    """

    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return tuple(str(item) for item in raw if item is not None)
    raise CatalogIntegrityError(f"{context}: 'literalValues' must be a string or array of strings")


def _parse_transform(raw: Any, context: str) -> TransformName | None:
    """Normalise optional transform names.

    Args:
        raw: Raw ``transform`` value from configuration.
        context: Context string for error reporting.

    Returns:
        TransformName | None: Transform enum member or ``None``.

    Raises:
        CatalogIntegrityError: If ``raw`` is not a recognised transform name.

    """

    if raw is None:
        return None
    if not isinstance(raw, str):
        raise CatalogIntegrityError(f"{context}: 'transform' must be a string when provided")
    normalized = raw.strip()
    try:
        return TransformName(normalized)
    except ValueError as exc:
        raise CatalogIntegrityError(f"{context}: unsupported transform '{raw}'") from exc


def _build_option_behavior(config: _ParsedOptionConfig, *, context: str) -> _OptionBehavior:
    """Instantiate behaviour strategy for a parsed option.

    Args:
        config: Parsed option configuration.
        context: Context string used when raising validation errors.

    Returns:
        _OptionBehavior: Behaviour responsible for emitting CLI fragments.

    Raises:
        CatalogIntegrityError: If the option kind is unsupported or missing
            required fields.

    """

    flags = config.flags
    if config.kind is OptionKind.ARGS:
        return _ArgsOptionBehavior(flag=flags.flag, join_separator=flags.join_with)
    if config.kind is OptionKind.PATH:
        return _PathOptionBehavior(flag=flags.flag, literal_values=flags.literal_values)
    if config.kind is OptionKind.VALUE:
        return _ValueOptionBehavior(flag=flags.flag)
    if config.kind is OptionKind.FLAG:
        return _FlagOptionBehavior(flag=flags.flag, negate_flag=flags.negate_flag)
    if config.kind is OptionKind.REPEAT_FLAG:
        if flags.flag is None:
            raise CatalogIntegrityError(f"{context}: repeatFlag requires a 'flag' entry")
        return _RepeatFlagBehavior(flag=flags.flag, negate_flag=flags.negate_flag)
    raise CatalogIntegrityError(f"{context}: unsupported option kind '{config.kind.value}'")


def _transform_python_version_tag(value: JSONValue, ctx: ToolContext) -> JSONValue:
    """Return Python version tag derived from ``value`` or context.

    Args:
        value: Raw version value configured for the option.
        ctx: Tool execution context providing fallback version information.

    Returns:
        JSONValue: Version tag string representing the target version.

    """
    return _python_version_tag(_coerce_version_string(value, ctx))


def _transform_python_version_number(value: JSONValue, ctx: ToolContext) -> JSONValue:
    """Return Python version number derived from ``value`` or context.

    Args:
        value: Raw version value configured for the option.
        ctx: Tool execution context providing fallback version information.

    Returns:
        JSONValue: Version number string or tuple accepted by downstream tools.

    """
    return _python_version_number(_coerce_version_string(value, ctx))


def _transform_pyupgrade_flag(value: JSONValue, ctx: ToolContext) -> JSONValue:
    """Return ``pyupgrade`` flag corresponding to the configured version.

    Args:
        value: Raw version value configured for the option.
        ctx: Tool execution context providing fallback version information.

    Returns:
        JSONValue: `pyupgrade` flag string.

    """
    return _pyupgrade_flag_from_version(_coerce_version_string(value, ctx))


def _transform_strictness_is_strict(value: JSONValue, ctx: ToolContext) -> JSONValue:
    """Return ``True`` when strictness represents a strict profile.

    Args:
        value: Raw strictness value from configuration.
        ctx: Tool execution context (unused).

    Returns:
        JSONValue: Boolean indicating whether the strict profile is active.

    """
    del ctx
    if isinstance(value, str):
        return value.strip().lower() == "strict"
    if isinstance(value, bool):
        return value
    return bool(value)


def _transform_strictness_is_lenient(value: JSONValue, ctx: ToolContext) -> JSONValue:
    """Return ``True`` when strictness represents a lenient profile.

    Args:
        value: Raw strictness value from configuration.
        ctx: Tool execution context (unused).

    Returns:
        JSONValue: Boolean indicating whether the lenient profile is active.

    """
    del ctx
    if isinstance(value, str):
        return value.strip().lower() == "lenient"
    return False


def _transform_bool_to_yn(value: JSONValue, ctx: ToolContext) -> JSONValue:
    """Transform booleans into ``y``/``n`` strings.

    Args:
        value: Raw boolean-like value from configuration.
        ctx: Tool execution context (unused).

    Returns:
        JSONValue: ``"y"`` when truthy, otherwise ``"n"``.

    """
    del ctx
    bool_value = _as_bool(value)
    if bool_value is None:
        bool_value = bool(value)
    return "y" if bool_value else "n"


def _transform_bool_to_str(value: JSONValue, ctx: ToolContext) -> JSONValue:
    """Transform booleans into ``true``/``false`` strings.

    Args:
        value: Raw boolean-like value from configuration.
        ctx: Tool execution context (unused).

    Returns:
        JSONValue: Literal string ``"true"`` or ``"false"``.

    """
    del ctx
    bool_value = _as_bool(value)
    if bool_value is None:
        bool_value = bool(value)
    return "true" if bool_value else "false"


def _append_flagged(command: list[str], value: str, flag: str | None) -> None:
    """Append ``value`` to ``command`` accounting for an optional ``flag``.

    Args:
        command: Mutable command list to extend.
        value: Argument value to append.
        flag: Optional flag to prefix before ``value``.

    Returns:
        None: The command list is mutated in place.

    """
    if flag is None:
        command.append(value)
        return
    if flag.endswith("="):
        command.append(f"{flag}{value}")
    else:
        command.extend([flag, value])


def _coerce_repeat_count(value: JSONValue) -> int:
    """Coerce arbitrary values into a non-negative repeat count.

    Args:
        value: Raw configuration value specifying repetitions.

    Returns:
        int: Non-negative repeat count derived from ``value``.

    """
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return max(int(value), 0)
    try:
        return max(int(str(value)), 0)
    except (TypeError, ValueError):
        return 0


def _coerce_version_string(value: JSONValue, ctx: ToolContext) -> str:
    """Return version string derived from ``value`` or context defaults.

    Args:
        value: Raw version input from the catalog.
        ctx: Tool execution context used to infer defaults.

    Returns:
        str: Resolved version string.

    """
    if value is None:
        return _python_target_version(ctx)
    return str(value)


def _resolve_default_reference(token: str, ctx: ToolContext) -> JSONValue | None:
    """Resolve default reference token against the execution context.

    Args:
        token: Reference key describing which default to resolve.
        ctx: Tool execution context providing configuration defaults.

    Returns:
        JSONValue | None: Resolved default or ``None`` when unavailable.

    """
    if token in _DEFAULT_REFERENCE_LOOKUP:
        return _DEFAULT_REFERENCE_LOOKUP[token](ctx)
    if token in _DYNAMIC_REFERENCE_LOOKUP:
        return _DYNAMIC_REFERENCE_LOOKUP[token](ctx)
    if token.startswith("tool_setting."):
        setting_name = token.split(".", 1)[1]
        return cast("JSONValue | None", _setting(ctx.settings, setting_name))
    return None


_TransformFunc = Callable[[JSONValue, ToolContext], JSONValue]
_TRANSFORM_HANDLERS: Mapping[TransformName, _TransformFunc] = {
    TransformName.PYTHON_VERSION_TAG: _transform_python_version_tag,
    TransformName.PYTHON_VERSION_NUMBER: _transform_python_version_number,
    TransformName.PYUPGRADE_FLAG: _transform_pyupgrade_flag,
    TransformName.STRICTNESS_IS_STRICT: _transform_strictness_is_strict,
    TransformName.STRICTNESS_IS_LENIENT: _transform_strictness_is_lenient,
    TransformName.BOOL_TO_YN: _transform_bool_to_yn,
    TransformName.BOOL_TO_STR: _transform_bool_to_str,
}


_DEFAULT_REFERENCE_LOOKUP: Mapping[str, Callable[[ToolContext], JSONValue | None]] = {
    "execution.line_length": lambda ctx: ctx.cfg.execution.line_length,
    "complexity.max_complexity": lambda ctx: ctx.cfg.complexity.max_complexity,
    "complexity.max_arguments": lambda ctx: ctx.cfg.complexity.max_arguments,
    "severity.bandit_level": lambda ctx: getattr(ctx.cfg.severity.bandit_level, "value", ctx.cfg.severity.bandit_level),
    "severity.bandit_confidence": lambda ctx: getattr(
        ctx.cfg.severity.bandit_confidence,
        "value",
        ctx.cfg.severity.bandit_confidence,
    ),
    "severity.pylint_fail_under": lambda ctx: ctx.cfg.severity.pylint_fail_under,
    "severity.max_warnings": lambda ctx: ctx.cfg.severity.max_warnings,
    "strictness.type_checking": lambda ctx: ctx.cfg.strictness.type_checking,
    "execution.sql_dialect": lambda ctx: getattr(ctx.cfg.execution, "sql_dialect", None),
    "tool.root": lambda ctx: str(ctx.root),
}


_DYNAMIC_REFERENCE_LOOKUP: Mapping[str, Callable[[ToolContext], JSONValue | None]] = {
    "python.target_version_tag": lambda ctx: _python_version_tag(_python_target_version(ctx)),
    "python.target_version": _python_target_version,
    "python.target_version_number": lambda ctx: _python_version_number(_python_target_version(ctx)),
    "python.discover_pylint_plugins": lambda ctx: tuple(_discover_pylint_plugins(ctx.root)),
}
