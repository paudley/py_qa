# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared configuration helper functions."""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, cast

from pydantic import BaseModel

from ..core.serialization import jsonify
from ..filesystem.paths import normalize_path
from ..tools.settings import tool_setting_schema_as_dict
from .models import Config, ConfigError
from .types import ConfigFragment, ConfigValue

_KNOWN_SECTIONS: set[str] = {
    "file_discovery",
    "output",
    "execution",
    "dedupe",
    "severity_rules",
    "license",
    "quality",
    "generic_value_types",
    "clean",
    "update",
    "tools",
}

_TOOL_SECTION: Final[str] = "tools"
_TOOL_SETTINGS_SECTION: Final[str] = "tool_settings"
_CONFIG_SECTION_KEYS: Final[set[str]] = _KNOWN_SECTIONS - {_TOOL_SECTION}

_ENV_VAR_PATTERN = re.compile(r"\$(\w+)|\$\{([^}]+)\}")


def _coerce_optional_int(value: ConfigValue, current: int, context: str) -> int:
    """Return a sanitised integer configuration value.

    Args:
        value: Raw configuration payload supplied by the caller.
        current: Baseline integer to use when ``value`` is ``None``.
        context: Dot-delimited configuration key for error reporting.

    Returns:
        Integer value guaranteed to be valid for the configuration model.

    Raises:
        ConfigError: If ``value`` cannot be interpreted as an integer.
    """

    if value is None:
        return current
    if isinstance(value, bool):
        raise ConfigError(f"{context} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ConfigError(f"{context} must be an integer")


def _coerce_string_sequence(value: ConfigValue, context: str) -> list[str]:
    """Return a normalised list of non-empty strings.

    Args:
        value: Raw configuration payload that should represent a sequence.
        context: Dot-delimited configuration key for error reporting.

    Returns:
        List of trimmed string values.

    Raises:
        ConfigError: If ``value`` cannot be converted into a sequence of strings.
    """

    if value is None:
        return []
    items: list[str]
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, str)):
        items = []
        for entry in value:
            if not isinstance(entry, str):
                raise ConfigError(f"{context} entries must be strings")
            items.append(entry)
    else:
        raise ConfigError(f"{context} must be a string or array of strings")
    result: list[str] = []
    for item in items:
        trimmed = item.strip()
        if trimmed:
            result.append(trimmed)
    return result


def _normalize_tool_filters(
    raw: ConfigFragment | ConfigValue,
    existing: Mapping[str, list[str]],
) -> dict[str, list[str]]:
    """Return merged tool filters combining existing and raw configuration.

    Args:
        raw: Mapping of tool identifiers to configured file globs.
        existing: Previously defined tool filter mapping.

    Returns:
        Mapping of tool identifiers to deduplicated glob patterns.

    Raises:
        ConfigError: If ``raw`` contains non-mapping values or non-string patterns.
    """

    if not isinstance(raw, Mapping):
        raise ConfigError("output.tool_filters must be a table")

    result: dict[str, list[str]] = {tool: patterns.copy() for tool, patterns in existing.items()}
    for tool, patterns in raw.items():
        patterns_iterable = _coerce_iterable(patterns, f"output.tool_filters.{tool}")
        bucket = result.setdefault(tool, [])
        for pattern in patterns_iterable:
            if not isinstance(pattern, str):
                raise ConfigError("tool filter patterns must be strings")
            if pattern not in bucket:
                bucket.append(pattern)
    return result


def _normalize_output_mode(value: str) -> str:
    """Return a canonical output mode identifier.

    Args:
        value: Raw output mode supplied by the user.

    Returns:
        Lowercase output mode string accepted by the reporter.

    Raises:
        ConfigError: If ``value`` does not represent a supported mode.
    """

    normalized = value.lower()
    if normalized not in {"concise", "pretty", "raw"}:
        raise ConfigError(f"invalid output mode '{value}'")
    return normalized


def _normalize_min_severity(value: str) -> str:
    """Return a canonical summary severity identifier.

    Args:
        value: Raw severity token supplied by the user.

    Returns:
        Lowercase severity string accepted by reporters.

    Raises:
        ConfigError: If ``value`` is not a recognised severity.
    """

    normalized = value.lower()
    if normalized not in {"error", "warning", "notice", "note"}:
        raise ConfigError(f"invalid summary severity '{value}'")
    return normalized


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    """Return unique resolved paths preserving order.

    Args:
        paths: Iterable of path-like objects to normalise.

    Returns:
        Ordered list of unique resolved paths.
    """

    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = _resolve_path(path)
        if resolved not in seen:
            result.append(resolved)
            seen.add(resolved)
    return result


def _existing_unique_paths(paths: Iterable[Path]) -> list[Path]:
    """Return unique resolved paths that exist on disk.

    Args:
        paths: Iterable of path-like objects to validate.

    Returns:
        Ordered list of unique resolved paths that exist on disk.
    """

    collected: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = _resolve_path(path)
        if not resolved.exists() or resolved in seen:
            continue
        collected.append(resolved)
        seen.add(resolved)
    return collected


def _resolve_path(candidate: Path) -> Path:
    """Resolve ``candidate`` using :func:`normalize_path` where possible.

    Args:
        candidate: Path instance to resolve relative to the working directory.

    Returns:
        Absolute path corresponding to ``candidate``.
    """

    try:
        normalised = normalize_path(candidate)
    except (ValueError, OSError):
        return candidate.resolve()
    if normalised.is_absolute():
        return normalised
    try:
        return (Path.cwd() / normalised).resolve()
    except OSError:
        return (Path.cwd() / normalised).absolute()


def _deep_merge(
    base: Mapping[str, ConfigValue],
    override: Mapping[str, ConfigValue],
) -> dict[str, ConfigValue]:
    """Return a deep merge of two configuration mappings.

    Args:
        base: Original configuration mapping.
        override: Mapping containing override values.

    Returns:
        dictionary representing ``base`` with ``override`` values applied.
    """

    result: dict[str, ConfigValue] = dict(base)
    for key, value in override.items():
        base_value = result.get(key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(base_value, value)
        else:
            result[key] = value
    return result


def _coerce_iterable(value: ConfigValue, context: str) -> list[ConfigValue]:
    """Return a list populated from ``value``.

    Args:
        value: Raw configuration payload expected to be iterable.
        context: Dot-delimited configuration key for error reporting.

    Returns:
        List containing the iterable contents of ``value``.

    Raises:
        ConfigError: If ``value`` is not a non-string iterable.
    """

    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ConfigError(f"{context} must be an array")
    return list(value)


def _normalise_pyproject_payload(data: ConfigFragment) -> dict[str, ConfigValue]:
    """Normalize ``pyproject`` payloads by splitting tool sections.

    Args:
        data: Raw configuration mapping extracted from ``pyproject.toml``.

    Returns:
        Mapping where tool-specific settings are placed under ``tools``.
    """

    result, tool_settings = _partition_sections(data.items())
    if tool_settings:
        result[_TOOL_SECTION] = tool_settings
    return result


def _normalise_fragment(fragment: ConfigFragment) -> dict[str, ConfigValue]:
    """Canonicalize configuration fragments for catalog loaders.

    Args:
        fragment: Configuration mapping returned by loader plug-ins.

    Returns:
        Mapping where tool-specific settings are placed under ``tools``.
    """

    result, tool_settings = _partition_sections(fragment.items())
    if tool_settings:
        result[_TOOL_SECTION] = tool_settings
    return result


def _partition_sections(
    items: Iterable[tuple[str, ConfigValue]],
) -> tuple[dict[str, ConfigValue], dict[str, ConfigValue]]:
    """Return partitioned configuration sections and tool-specific entries.

    Args:
        items: Iterable of key/value pairs from configuration payloads.

    Returns:
        Tuple of recognised configuration sections and tool-specific settings.
    """

    result: dict[str, ConfigValue] = {}
    tool_settings: dict[str, ConfigValue] = {}
    for section_key, value in items:
        canonical_key = _canonical_section(section_key)
        if canonical_key in _CONFIG_SECTION_KEYS:
            result[canonical_key] = value
            continue
        if canonical_key == _TOOL_SECTION:
            tool_settings.update(_validate_tool_section(value))
            continue
        if isinstance(value, Mapping):
            tool_settings[canonical_key] = dict(value)
        else:
            result[canonical_key] = value
    return result, tool_settings


def _canonical_section(key: str) -> str:
    """Return canonical section name for ``key``.

    Args:
        key: Raw section name sourced from configuration payloads.

    Returns:
        Canonical section identifier recognised by the loader.
    """

    return _TOOL_SECTION if key == _TOOL_SETTINGS_SECTION else key


def _validate_tool_section(value: ConfigValue) -> dict[str, ConfigValue]:
    """Return a normalized representation of the ``tools`` configuration table.

    Args:
        value: Raw configuration payload associated with the ``tools`` section.

    Returns:
        Mapping of tool identifiers to their nested configuration values.

    Raises:
        ConfigError: If ``value`` does not represent a mapping of tool settings.
    """

    if not isinstance(value, Mapping):
        raise ConfigError("tools section must be a table")
    tools: dict[str, ConfigValue] = {}
    for tool_name, settings in value.items():
        if not isinstance(settings, Mapping):
            raise ConfigError(f"tools.{tool_name} section must be a table")
        tools[tool_name] = dict(settings)
    return tools


def _expand_env(data: Mapping[str, ConfigValue], env: Mapping[str, str]) -> dict[str, ConfigValue]:
    """Produce configuration data with environment variables expanded.

    Args:
        data: Configuration mapping containing string values to expand.
        env: Mapping of environment variables available to the loader.

    Returns:
        Configuration mapping where environment references have been expanded.
    """

    expanded: dict[str, ConfigValue] = {}
    for key, value in data.items():
        expanded[key] = _expand_env_value(value, env)
    return expanded


def _expand_env_value(value: ConfigValue, env: Mapping[str, str]) -> ConfigValue:
    """Return values with embedded environment variables expanded.

    Args:
        value: Configuration value that might contain environment references.
        env: Mapping of environment variables available to the loader.

    Returns:
        Configuration value with any embedded environment references expanded.
    """

    if isinstance(value, str):
        return _expand_env_string(value, env)
    if isinstance(value, Mapping):
        return {k: _expand_env_value(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_value(v, env) for v in value]
    return value


def _expand_env_string(value: str, env: Mapping[str, str]) -> str:
    """Expand shell-style environment variables contained within ``value``.

    Args:
        value: String value containing optional ``$VARNAME`` tokens.
        env: Mapping of environment variables available to the loader.

    Returns:
        String with the recognised environment tokens expanded.
    """

    def _replace(match: re.Match[str]) -> str:
        """Return replacement text for a single environment variable match.

        Args:
            match: Regex match containing the captured environment variable.

        Returns:
            str: Replacement text for the matched token.

        """
        key = match.group(1) or match.group(2)
        if key is None:
            return match.group(0)
        return env.get(key, match.group(0))

    return _ENV_VAR_PATTERN.sub(_replace, value)


def generate_config_schema() -> dict[str, ConfigValue]:
    """Return a JSON-serialisable schema describing configuration sections.

    Returns:
        Mapping that documents configuration sections and default values.
    """

    defaults = Config()
    tool_defaults = dict(defaults.tool_settings)
    schema: OrderedDict[str, ConfigValue] = OrderedDict()
    schema["file_discovery"] = cast(ConfigValue, _describe_model(defaults.file_discovery))
    schema["output"] = cast(ConfigValue, _describe_model(defaults.output))
    schema["execution"] = cast(ConfigValue, _describe_model(defaults.execution))
    schema["dedupe"] = cast(ConfigValue, _describe_model(defaults.dedupe))
    schema["complexity"] = cast(ConfigValue, _describe_model(defaults.complexity))
    schema["strictness"] = cast(ConfigValue, _describe_model(defaults.strictness))
    schema["severity"] = cast(ConfigValue, _describe_model(defaults.severity))
    schema["severity_rules"] = cast(
        ConfigValue,
        {
            "type": "list[str]",
            "default": list(defaults.severity_rules),
        },
    )
    schema["tool_settings"] = cast(
        ConfigValue,
        {
            "type": "dict[str, dict[str, ConfigValue]]",
            "default": {tool: dict(settings) for tool, settings in tool_defaults.items()},
            "tools": tool_setting_schema_as_dict(),
        },
    )
    return dict(schema)


def _describe_model(instance: BaseModel) -> dict[str, ConfigValue]:
    """Return a schema description for a Pydantic model instance.

    Args:
        instance: Pydantic model exposing the configuration fields.

    Returns:
        Mapping describing field names, types, and default values.
    """

    description: OrderedDict[str, ConfigValue] = OrderedDict()
    fields = dict(instance.__class__.model_fields)
    for name in fields:
        field_info = fields[name]
        value = getattr(instance, name)
        annotation = getattr(field_info, "annotation", None) or type(value)
        description[name] = cast(
            ConfigValue,
            {
                "type": _render_field_type(annotation),
                "default": jsonify(value),
            },
        )
    return dict(description)


def _render_field_type(annotation: type | str | None) -> str:
    """Return a string representation for a model field annotation.

    Args:
        annotation: Annotation object associated with a Pydantic field.

    Returns:
        Human-readable representation of ``annotation``.
    """

    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin is None:
        return getattr(annotation, "__name__", str(annotation))
    rendered_args = ", ".join(_render_field_type(arg) for arg in args)
    return f"{getattr(origin, '__name__', str(origin))}[{rendered_args}]"


__all__ = [
    "_KNOWN_SECTIONS",
    "_coerce_iterable",
    "_coerce_optional_int",
    "_coerce_string_sequence",
    "_deep_merge",
    "_existing_unique_paths",
    "_expand_env",
    "_normalise_fragment",
    "_normalise_pyproject_payload",
    "_normalize_min_severity",
    "_normalize_output_mode",
    "_normalize_tool_filters",
    "_unique_paths",
    "generate_config_schema",
]
