# SPDX-License-Identifier: MIT
"""Helper services for configuration inspection commands."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import typer

from ..config_loader import ConfigError, ConfigLoadResult, ConfigLoader, FieldUpdate
from ..serialization import jsonify
from ..tools.settings import TOOL_SETTING_SCHEMA, SettingField, tool_setting_schema_as_dict

JSON_FORMAT = "json"
JSON_TOOLS_FORMAT = "json-tools"
MARKDOWN_FORMATS = frozenset({"markdown", "md"})
FINAL_LAYER_KEY = "final"
TOOL_SETTINGS_KEY = "tool_settings"
TYPE_KEY = "type"
DEFAULT_KEY = "default"


def load_config_with_trace(root: Path, *, strict: bool) -> ConfigLoadResult:
    """Load configuration with provenance, exiting on failure."""

    loader = ConfigLoader.for_root(root)
    try:
        return loader.load_with_trace(strict=strict)
    except ConfigError as exc:  # pragma: no cover - CLI path
        typer.echo(f"Configuration invalid: {exc}")
        raise typer.Exit(code=1) from exc


def load_config(root: Path, *, strict: bool) -> None:
    """Validate configuration loading, exiting with status codes."""

    loader = ConfigLoader.for_root(root)
    try:
        loader.load(strict=strict)
    except ConfigError as exc:  # pragma: no cover - CLI path
        typer.echo(f"Configuration invalid: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo("Configuration is valid.")


def render_config_mapping(result: ConfigLoadResult) -> Mapping[str, object]:
    """Convert a config load result into a JSON-serialisable mapping."""

    config = result.config
    return {
        "file_discovery": jsonify(config.file_discovery),
        "output": jsonify(config.output),
        "execution": jsonify(config.execution),
        "dedupe": jsonify(config.dedupe),
        "severity_rules": list(config.severity_rules),
        "tool_settings": jsonify(config.tool_settings),
    }


def summarise_updates(updates: Sequence[FieldUpdate]) -> list[str]:
    """Return human readable descriptions of field updates."""

    rendered: list[str] = []
    for update in updates:
        field_path = (
            update.field if update.section == "root" else f"{update.section}.{update.field}"
        )
        rendered.append(
            f"- {field_path} <- {update.source} -> {summarise_value(field_path, update.value)}"
        )
    return rendered


def summarise_value(field_path: str, value: object) -> str:
    """Return a readable representation of ``value`` for updates."""

    if field_path.startswith(f"{TOOL_SETTINGS_KEY}.") and isinstance(value, Mapping):
        parts = field_path.split(".", 2)
        tool = parts[1]
        schema = TOOL_SETTING_SCHEMA.get(tool, {})
        sections = []
        for key, entry in value.items():
            field = schema.get(key)
            description = field.description if isinstance(field, SettingField) else None
            rendered = json.dumps(jsonify(entry), sort_keys=True)
            if description:
                sections.append(f"{key}={rendered} ({description})")
            else:
                sections.append(f"{key}={rendered}")
        return "; ".join(sections) if sections else json.dumps({}, sort_keys=True)
    return json.dumps(jsonify(value), sort_keys=True)


def render_schema(fmt: str) -> str:
    """Render the configuration schema in the requested format."""

    fmt_lower = fmt.lower()
    if fmt_lower == JSON_FORMAT:
        from ..config_loader import generate_config_schema  # local import to avoid cycles

        schema = generate_config_schema()
        return json.dumps(schema, indent=2, sort_keys=True)
    if fmt_lower == JSON_TOOLS_FORMAT:
        return json.dumps(tool_setting_schema_as_dict(), indent=2, sort_keys=True)
    if fmt_lower in MARKDOWN_FORMATS:
        from ..config_loader import generate_config_schema  # local import to avoid cycles

        schema = generate_config_schema()
        return schema_to_markdown(schema)
    raise typer.BadParameter("Unknown schema format. Use 'json', 'json-tools', or 'markdown'.")


def schema_to_markdown(schema: Mapping[str, object]) -> str:
    """Convert a schema mapping into markdown documentation."""

    lines: list[str] = []
    for section, fields in schema.items():
        lines.append(f"## {section}")
        if isinstance(fields, Mapping) and TYPE_KEY in fields:
            lines.append("| Field | Type | Default |")
            lines.append("| --- | --- | --- |")
            default = json.dumps(fields.get(DEFAULT_KEY), sort_keys=True)
            lines.append(f"| {section} | {fields[TYPE_KEY]} | {default} |")
            lines.append("")
            continue
        if isinstance(fields, Mapping):
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


def write_output(content: str, *, out: Path | None) -> None:
    """Print or write ``content`` to a file, ensuring newline termination."""

    if out is None:
        typer.echo(content)
        return
    out_path = out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = content if content.endswith("\n") else f"{content}\n"
    out_path.write_text(text, encoding="utf-8")
    typer.echo(str(out_path))


def collect_layer_snapshots(result: ConfigLoadResult) -> dict[str, Mapping[str, object]]:
    """Return snapshot mapping normalised to lower-case keys."""

    snapshots = {key.lower(): value for key, value in result.snapshots.items()}
    snapshots[FINAL_LAYER_KEY] = render_config_mapping(result)
    return snapshots


def diff_snapshots(
    from_snapshot: Mapping[str, Any],
    to_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a structural diff between two configuration snapshots."""

    diff: dict[str, Any] = {}
    keys = set(from_snapshot) | set(to_snapshot)
    for key in sorted(keys):
        left = from_snapshot.get(key)
        right = to_snapshot.get(key)
        if left == right:
            continue
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            nested = diff_snapshots(left, right)
            if nested:
                diff[key] = nested
        else:
            diff[key] = {"from": left, "to": right}
    return diff


__all__ = [
    "JSON_FORMAT",
    "JSON_TOOLS_FORMAT",
    "FINAL_LAYER_KEY",
    "load_config_with_trace",
    "load_config",
    "render_config_mapping",
    "render_schema",
    "summarise_updates",
    "summarise_value",
    "write_output",
    "collect_layer_snapshots",
    "diff_snapshots",
]
