# SPDX-License-Identifier: MIT
"""Helper services for configuration inspection commands."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast

import typer

from pyqa.config.types import ConfigValue
from pyqa.core.config.loader import (
    ConfigError,
    ConfigLoader,
    ConfigLoadResult,
    FieldUpdate,
    generate_config_schema,
)
from pyqa.core.serialization import JsonValue, SerializableValue, jsonify
from pyqa.platform.paths import strip_repo_root_from_text

from ....tools.settings import TOOL_SETTING_SCHEMA, SettingField, tool_setting_schema_as_dict
from ...core.shared import CLIError, CLILogger

SchemaFormatLiteral = Literal["json", "json-tools", "markdown", "md"]

JSON_FORMAT: Final[SchemaFormatLiteral] = "json"
JSON_TOOLS_FORMAT: Final[SchemaFormatLiteral] = "json-tools"
MARKDOWN_FORMATS: Final[frozenset[str]] = frozenset({"markdown", "md"})
ROOT_SECTION: Final[str] = "root"
FINAL_LAYER_KEY = "final"
TOOL_SETTINGS_KEY = "tool_settings"
TYPE_KEY = "type"
DEFAULT_KEY = "default"


def load_config_with_trace(
    root: Path,
    *,
    strict: bool,
    logger: CLILogger,
) -> ConfigLoadResult:
    """Perform configuration loading with provenance metadata.

    Args:
        root: Project root directory used to locate configuration files.
        strict: Whether configuration warnings should be treated as errors.
        logger: CLI logger used to report failures to the user.

    Returns:
        ConfigLoadResult: Loaded configuration alongside provenance metadata.

    Raises:
        CLIError: If configuration loading fails due to validation errors.
    """

    loader = ConfigLoader.for_root(root)
    try:
        return loader.load_with_trace(strict=strict)
    except ConfigError as exc:  # pragma: no cover - CLI path
        logger.fail(f"Configuration invalid: {exc}")
        raise CLIError(str(exc)) from exc


def validate_config(root: Path, *, strict: bool, logger: CLILogger) -> None:
    """Perform configuration validation, raising ``CLIError`` on failure.

    Args:
        root: Project root directory used to locate configuration files.
        strict: Whether configuration warnings should be treated as errors.
        logger: CLI logger used to report validation results.

    Raises:
        CLIError: If configuration loading fails due to validation errors.
    """

    loader = ConfigLoader.for_root(root)
    try:
        loader.load(strict=strict)
    except ConfigError as exc:  # pragma: no cover - CLI path
        logger.fail(f"Configuration invalid: {exc}")
        raise CLIError(str(exc)) from exc
    logger.ok("Configuration is valid.")


def render_config_mapping(result: ConfigLoadResult) -> Mapping[str, JsonValue]:
    """Convert a config load result into a JSON-serialisable mapping.

    Args:
        result: Configuration load result containing the modelled config.

    Returns:
        Mapping[str, JsonValue]: Serialisable mapping of configuration sections.
    """

    config = result.config
    return {
        "file_discovery": jsonify(cast(SerializableValue, config.file_discovery)),
        "output": jsonify(cast(SerializableValue, config.output)),
        "execution": jsonify(cast(SerializableValue, config.execution)),
        "dedupe": jsonify(cast(SerializableValue, config.dedupe)),
        "severity_rules": list(config.severity_rules),
        "tool_settings": jsonify(cast(SerializableValue, config.tool_settings)),
    }


def summarise_updates(updates: Sequence[FieldUpdate]) -> list[str]:
    """Return human readable descriptions of field updates.

    Args:
        updates: Sequence of configuration field updates.

    Returns:
        list[str]: Human-readable summaries describing configuration updates.
    """

    rendered: list[str] = []
    for update in updates:
        field_path = update.field if update.section == ROOT_SECTION else f"{update.section}.{update.field}"
        rendered_value = jsonify(cast(SerializableValue, update.value))
        formatted_value = summarise_value(field_path, rendered_value)
        rendered.append(f"- {field_path} <- {update.source} -> {formatted_value}")
    return rendered


def summarise_value(field_path: str, value: JsonValue) -> str:
    """Return a readable representation of ``value`` for updates.

    Args:
        field_path: Dot-delimited configuration field path.
        value: Value associated with the field update.

    Returns:
        str: Rendered representation suitable for CLI output.
    """

    if field_path.startswith(f"{TOOL_SETTINGS_KEY}.") and isinstance(value, Mapping):
        parts = field_path.split(".", 2)
        tool = parts[1]
        schema = TOOL_SETTING_SCHEMA.get(tool, {})
        sections = []
        for key, entry in value.items():
            field = schema.get(key)
            description = field.description if isinstance(field, SettingField) else None
            rendered = json.dumps(jsonify(cast(SerializableValue, entry)), sort_keys=True)
            if description:
                sections.append(f"{key}={rendered} ({description})")
            else:
                sections.append(f"{key}={rendered}")
        return "; ".join(sections) if sections else json.dumps({}, sort_keys=True)
    return json.dumps(jsonify(cast(SerializableValue, value)), sort_keys=True)


def render_schema(fmt: SchemaFormatLiteral) -> str:
    """Render the configuration schema in the requested format.

    Args:
        fmt: Requested schema format (``json``, ``json-tools``, or markdown).

    Returns:
        str: Schema representation in the requested format.

    Raises:
        typer.BadParameter: If ``fmt`` is not a recognised schema format.
    """

    fmt_lower = fmt.lower()
    if fmt_lower == JSON_FORMAT:
        schema = generate_config_schema()
        return json.dumps(schema, indent=2, sort_keys=True)
    if fmt_lower == JSON_TOOLS_FORMAT:
        return json.dumps(tool_setting_schema_as_dict(), indent=2, sort_keys=True)
    if fmt_lower in MARKDOWN_FORMATS:
        schema = generate_config_schema()
        return schema_to_markdown(schema)
    raise typer.BadParameter("Unknown schema format. Use 'json', 'json-tools', or 'markdown'.")


def schema_to_markdown(schema: Mapping[str, ConfigValue]) -> str:
    """Convert a schema mapping into markdown documentation.

    Args:
        schema: Schema mapping produced by :func:`generate_config_schema`.

    Returns:
        str: Markdown documentation describing schema sections and fields.
    """

    lines: list[str] = []
    for section, fields in schema.items():
        lines.append(f"## {section}")
        if isinstance(fields, Mapping):
            if TYPE_KEY in fields:
                lines.append("| Field | Type | Default |")
                lines.append("| --- | --- | --- |")
                default = json.dumps(fields.get(DEFAULT_KEY), sort_keys=True)
                lines.append(f"| {section} | {fields[TYPE_KEY]} | {default} |")
                lines.append("")
                continue
            lines.append("| Field | Type | Default | Description |")
            lines.append("| --- | --- | --- | --- |")
            for name, payload in fields.items():
                if isinstance(payload, Mapping):
                    kind = payload.get(TYPE_KEY, "-")
                    default = json.dumps(payload.get(DEFAULT_KEY), sort_keys=True)
                    description = payload.get("description", "-")
                    lines.append(f"| {name} | {kind} | {default} | {description} |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_output(content: str, *, out: Path | None, logger: CLILogger) -> None:
    """Print or write ``content`` to a file, ensuring newline termination.

    Args:
        content: Text content to emit.
        out: Optional path where content should be written.
        logger: CLI logger used to echo file paths or console output.
    """

    if out is None:
        logger.echo(content)
        return
    out_path = out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = content if content.endswith("\n") else f"{content}\n"
    text = strip_repo_root_from_text(text)
    out_path.write_text(text, encoding="utf-8")
    logger.echo(str(out_path))


def build_tool_schema_payload() -> dict[str, JsonValue]:
    """Return a JSON-serialisable payload describing tool settings.

    Returns:
        dict[str, JsonValue]: Schema payload including metadata and tool settings.
    """

    payload: dict[str, JsonValue] = {
        "_license": "SPDX-License-Identifier: MIT",
        "_copyright": "Copyright (c) 2025 Blackcat Informatics® Inc.",
    }
    schema_dict = tool_setting_schema_as_dict()
    payload.update(
        {key: jsonify(cast(SerializableValue, value)) for key, value in schema_dict.items()},
    )
    return payload


def collect_layer_snapshots(result: ConfigLoadResult) -> dict[str, JsonValue]:
    """Create configuration snapshots normalised to lower-case keys.

    Args:
        result: Configuration load result containing snapshot data.

    Returns:
        dict[str, JsonValue]: Mapping of snapshot names to serialisable values.
    """

    snapshots: dict[str, JsonValue] = {}
    for key, value in result.snapshots.items():
        snapshots[key.lower()] = jsonify(cast(SerializableValue, value))
    snapshots[FINAL_LAYER_KEY] = cast(JsonValue, dict(render_config_mapping(result)))
    return snapshots


def diff_snapshots(
    from_snapshot: Mapping[str, JsonValue],
    to_snapshot: Mapping[str, JsonValue],
    *,
    prefix: str = "",
) -> dict[str, JsonValue]:
    """Return a structural diff between two configuration snapshots.

    Args:
        from_snapshot: Baseline snapshot mapping.
        to_snapshot: Target snapshot mapping.
        prefix: Optional prefix appended to diff keys.

    Returns:
        dict[str, JsonValue]: Mapping describing differences between snapshots.
    """

    diff: dict[str, JsonValue] = {}
    keys = set(from_snapshot) | set(to_snapshot)
    for key in sorted(keys):
        left = from_snapshot.get(key)
        right = to_snapshot.get(key)
        if left == right:
            continue
        key_path = f"{prefix}.{key}" if prefix else key
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            nested = diff_snapshots(
                cast(Mapping[str, JsonValue], left),
                cast(Mapping[str, JsonValue], right),
                prefix=key_path,
            )
            diff.update(nested)
            continue
        if isinstance(left, Mapping) or isinstance(right, Mapping):
            nested = diff_snapshots(
                _mapping_or_empty(left),
                _mapping_or_empty(right),
                prefix=key_path,
            )
            if nested:
                diff.update(nested)
            diff[key_path] = cast(
                JsonValue,
                {
                    "from": jsonify(cast(SerializableValue, left)),
                    "to": jsonify(cast(SerializableValue, right)),
                },
            )
            continue
        diff[key_path] = cast(
            JsonValue,
            {
                "from": jsonify(cast(SerializableValue, left)),
                "to": jsonify(cast(SerializableValue, right)),
            },
        )
    return diff


def _mapping_or_empty(value: JsonValue | None) -> Mapping[str, JsonValue]:
    """Return ``value`` when it is a mapping, otherwise an empty mapping.

    Args:
        value: Candidate JSON value that may represent a mapping.

    Returns:
        Mapping[str, JsonValue]: Mapping derived from ``value`` or an empty mapping
        when ``value`` is not a mapping.
    """

    if isinstance(value, Mapping):
        return cast(Mapping[str, JsonValue], value)
    return {}


@dataclass(slots=True)
class ConfigDiffComputation:
    """Provide configuration diff metadata."""

    diff: dict[str, JsonValue]
    available_layers: list[str]


class UnknownConfigLayerError(ValueError):
    """Raised when a requested configuration layer does not exist."""

    def __init__(self, layer: str, *, available: list[str]) -> None:
        """Initialise the error with context about available layers.

        Args:
            layer: Name of the missing configuration layer requested by caller.
            available: Sorted list of layers present in the configuration
                snapshots.
        """

        super().__init__(layer)
        self.layer = layer
        self.available = available


def build_config_diff(
    result: ConfigLoadResult,
    *,
    from_layer: str,
    to_layer: str,
) -> ConfigDiffComputation:
    """Construct a diff payload between two configuration layers.

    Args:
        result: Configuration load result containing all layer snapshots.
        from_layer: Name of the baseline layer (case-insensitive).
        to_layer: Name of the comparison layer (case-insensitive).

    Returns:
        ConfigDiffComputation: Diff mapping and sorted list of available layers.

    Raises:
        UnknownConfigLayerError: If either ``from_layer`` or ``to_layer`` is not
            present in the snapshots.
        CLIError: If either configuration layer fails to provide a mapping
            payload that can be diffed.
    """

    snapshots = collect_layer_snapshots(result)
    available_layers = sorted(snapshots)
    from_key = from_layer.lower()
    to_key = to_layer.lower()

    if from_key not in snapshots:
        raise UnknownConfigLayerError(from_layer, available=available_layers)
    if to_key not in snapshots:
        raise UnknownConfigLayerError(to_layer, available=available_layers)

    from_snapshot = snapshots[from_key]
    to_snapshot = snapshots[to_key]
    if not isinstance(from_snapshot, Mapping) or not isinstance(to_snapshot, Mapping):
        raise CLIError("Configuration layers must be mapping objects to diff")
    typed_from = cast(Mapping[str, JsonValue], from_snapshot)
    typed_to = cast(Mapping[str, JsonValue], to_snapshot)
    diff_payload = diff_snapshots(typed_from, typed_to)
    return ConfigDiffComputation(diff=diff_payload, available_layers=available_layers)


__all__ = [
    "JSON_FORMAT",
    "JSON_TOOLS_FORMAT",
    "SchemaFormatLiteral",
    "FINAL_LAYER_KEY",
    "load_config_with_trace",
    "validate_config",
    "render_config_mapping",
    "render_schema",
    "summarise_updates",
    "summarise_value",
    "write_output",
    "build_tool_schema_payload",
    "collect_layer_snapshots",
    "diff_snapshots",
    "build_config_diff",
    "ConfigDiffComputation",
    "UnknownConfigLayerError",
]
