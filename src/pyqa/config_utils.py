# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared configuration helper functions."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .config import Config, ConfigError
from .serialization import jsonify
from .tools.settings import tool_setting_schema_as_dict

_KNOWN_SECTIONS: set[str] = {
    "file_discovery",
    "output",
    "execution",
    "dedupe",
    "severity_rules",
    "license",
    "quality",
    "clean",
    "update",
    "tools",
}

_ENV_VAR_PATTERN = re.compile(r"\$(\w+)|\$\{([^}]+)\}")


def _coerce_optional_int(value: Any, current: int, context: str) -> int:
    if value is None:
        return current
    if isinstance(value, bool):
        raise ConfigError(f"{context} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ConfigError(f"{context} must be an integer")


def _coerce_string_sequence(value: Any, context: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, str)):
        items = list(value)
    else:
        raise ConfigError(f"{context} must be a string or array of strings")
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ConfigError(f"{context} entries must be strings")
        trimmed = item.strip()
        if trimmed:
            result.append(trimmed)
    return result


def _normalize_tool_filters(raw: Any, existing: Mapping[str, list[str]]) -> dict[str, list[str]]:
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
    normalized = value.lower()
    if normalized not in {"concise", "pretty", "raw"}:
        raise ConfigError(f"invalid output mode '{value}'")
    return normalized


def _normalize_min_severity(value: str) -> str:
    normalized = value.lower()
    if normalized not in {"error", "warning", "notice", "note"}:
        raise ConfigError(f"invalid summary severity '{value}'")
    return normalized


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            result.append(resolved)
            seen.add(resolved)
    return result


def _existing_unique_paths(paths: Iterable[Path]) -> list[Path]:
    collected: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if not resolved.exists():
            continue
        if resolved in seen:
            continue
        collected.append(resolved)
        seen.add(resolved)
    return collected


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _coerce_iterable(value: Any, context: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ConfigError(f"{context} must be an array")
    return list(value)


def _normalise_pyproject_payload(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    tool_settings: dict[str, Any] = {}
    for key, value in data.items():
        if key == "tool_settings":
            key = "tools"
        if key in _KNOWN_SECTIONS - {"tools"}:
            result[key] = value
            continue
        if key == "tools":
            if not isinstance(value, Mapping):
                raise ConfigError("tools section must be a table")
            for tool, settings in value.items():
                if not isinstance(settings, Mapping):
                    raise ConfigError(f"tools.{tool} section must be a table")
                tool_settings[tool] = dict(settings)
            continue
        if isinstance(value, Mapping):
            tool_settings[key] = dict(value)
        else:
            result[key] = value
    if tool_settings:
        result["tools"] = tool_settings
    return result


def _normalise_fragment(fragment: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    tool_settings: dict[str, Any] = {}
    for key, value in fragment.items():
        if key == "tool_settings":
            key = "tools"
        if key in _KNOWN_SECTIONS - {"tools"}:
            result[key] = value
            continue
        if key == "tools":
            if not isinstance(value, Mapping):
                raise ConfigError("tools section must be a table")
            for tool, settings in value.items():
                if not isinstance(settings, Mapping):
                    raise ConfigError(f"tools.{tool} section must be a table")
                tool_settings[tool] = dict(settings)
            continue
        if isinstance(value, Mapping):
            tool_settings[key] = dict(value)
        else:
            result[key] = value
    if tool_settings:
        result["tools"] = tool_settings
    return result


def _expand_env(data: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    expanded: dict[str, Any] = {}
    for key, value in data.items():
        expanded[key] = _expand_env_value(value, env)
    return expanded


def _expand_env_value(value: Any, env: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _expand_env_string(value, env)
    if isinstance(value, Mapping):
        return {k: _expand_env_value(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_value(v, env) for v in value]
    return value


def _expand_env_string(value: str, env: Mapping[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1) or match.group(2)
        if key is None:
            return match.group(0)
        return env.get(key, match.group(0))

    return _ENV_VAR_PATTERN.sub(_replace, value)


def generate_config_schema() -> dict[str, Any]:
    """Return a JSON-serializable schema describing configuration sections."""
    defaults = Config()
    tool_defaults = dict(defaults.tool_settings)
    return {
        "file_discovery": _describe_model(defaults.file_discovery),
        "output": _describe_model(defaults.output),
        "execution": _describe_model(defaults.execution),
        "dedupe": _describe_model(defaults.dedupe),
        "duplicates": _describe_model(defaults.duplicates),
        "complexity": _describe_model(defaults.complexity),
        "strictness": _describe_model(defaults.strictness),
        "severity": _describe_model(defaults.severity),
        "severity_rules": {
            "type": "list[str]",
            "default": list(defaults.severity_rules),
        },
        "tool_settings": {
            "type": "dict[str, dict[str, object]]",
            "default": {tool: dict(settings) for tool, settings in tool_defaults.items()},
            "tools": tool_setting_schema_as_dict(),
        },
    }


def _describe_model(instance: BaseModel) -> dict[str, dict[str, Any]]:
    description: dict[str, dict[str, Any]] = {}
    fields = dict(instance.__class__.model_fields)
    for name in fields:
        field_info = fields[name]
        value = getattr(instance, name)
        annotation = getattr(field_info, "annotation", None) or type(value)
        description[name] = {
            "type": _render_field_type(annotation),
            "default": jsonify(value),
        }
    return description


def _render_field_type(annotation: Any) -> str:
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
