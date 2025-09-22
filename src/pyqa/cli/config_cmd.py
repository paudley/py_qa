# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Configuration inspection commands."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

import typer

from ..config import ConfigError
from ..config_loader import (
    ConfigLoader,
    ConfigLoadResult,
    FieldUpdate,
    generate_config_schema,
)
from ..tools.settings import TOOL_SETTING_SCHEMA

config_app = typer.Typer(help="Inspect, validate, and document configuration layers.")


@config_app.command("show")
def config_show(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    trace: bool = typer.Option(True, help="Show which source last set each field."),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        case_sensitive=False,
        help="Output format (currently only 'json').",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat configuration warnings as errors.",
    ),
) -> None:
    """Print the effective configuration for the project."""

    loader = ConfigLoader.for_root(root)
    try:
        result = loader.load_with_trace(strict=strict)
    except ConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    if format.lower() != "json":
        raise typer.BadParameter("Only JSON output is supported at the moment")

    typer.echo(json.dumps(_config_to_mapping(result), indent=2, sort_keys=True))
    if trace and result.updates:
        typer.echo("\n# Overrides")
        for update in _summarise_updates(result.updates):
            typer.echo(update)
    if result.warnings:
        typer.echo("\n# Warnings")
        for warning in result.warnings:
            typer.echo(f"- {warning}")


@config_app.command("validate")
def config_validate(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    strict: bool = typer.Option(False, "--strict", help="Treat configuration warnings as errors."),
) -> None:
    """Ensure the configuration loads successfully."""

    loader = ConfigLoader.for_root(root)
    try:
        loader.load(strict=strict)
    except ConfigError as exc:  # pragma: no cover - exercised in tests
        typer.echo(f"Configuration invalid: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo("Configuration is valid.")


@config_app.command("schema")
def config_schema(
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        case_sensitive=False,
        help="Output format: json (default), json-tools, or markdown.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Write schema output to the provided file path.",
    ),
) -> None:
    """Emit a machine-readable description of configuration fields."""

    schema = generate_config_schema()
    fmt = format.lower()
    if fmt == "json":
        content = json.dumps(schema, indent=2, sort_keys=True)
    elif fmt == "json-tools":
        content = json.dumps(TOOL_SETTING_SCHEMA, indent=2, sort_keys=True)
    elif fmt in {"md", "markdown"}:
        content = _schema_to_markdown(schema)
    else:  # pragma: no cover - defensive branch
        raise typer.BadParameter("Unknown schema format. Use 'json', 'json-tools', or 'markdown'.")

    if out:
        out_path = out.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        text = content if content.endswith("\n") else content + "\n"
        out_path.write_text(text, encoding="utf-8")
        typer.echo(str(out_path))
    else:
        typer.echo(content)


@config_app.command("diff")
def config_diff(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    from_layer: str = typer.Option("defaults", "--from", help="Baseline layer."),
    to_layer: str = typer.Option("final", "--to", help="Comparison layer."),
    out: Path | None = typer.Option(None, "--out", help="Write diff output to the provided path."),
) -> None:
    """Show the difference between two configuration layers."""

    loader = ConfigLoader.for_root(root)
    result = loader.load_with_trace()
    snapshots = result.snapshots
    from_key = from_layer.lower()
    to_key = to_layer.lower()
    available = {key.lower(): key for key in snapshots}
    available["final"] = "final"
    if from_key not in available:
        raise typer.BadParameter(f"Unknown layer '{from_layer}'. Available: {', '.join(sorted(available))}")
    if to_key not in available:
        raise typer.BadParameter(f"Unknown layer '{to_layer}'. Available: {', '.join(sorted(available))}")
    from_snapshot = snapshots.get(available[from_key])
    if from_snapshot is None and from_key == "final":
        from_snapshot = _config_to_mapping(result)
    to_snapshot = snapshots.get(available[to_key])
    if to_snapshot is None and to_key == "final":
        to_snapshot = _config_to_mapping(result)
    if from_snapshot is None or to_snapshot is None:
        raise typer.BadParameter("Selected layers are not available in this project")
    diff = _diff_snapshots(from_snapshot, to_snapshot)
    content = json.dumps(diff, indent=2, sort_keys=True)
    if out:
        out_path = out.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content + "\n", encoding="utf-8")
        typer.echo(str(out_path))
    else:
        typer.echo(content)


@config_app.command("export-tools")
def config_export_tools(
    out: Path = typer.Argument(
        Path("tool-schema.json"),
        metavar="PATH",
        help="Destination file for the tool schema JSON.",
    ),
) -> None:
    """Write the tool settings schema to disk."""

    out_path = out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(TOOL_SETTING_SCHEMA, indent=2, sort_keys=True) + "\n"
    out_path.write_text(text, encoding="utf-8")
    typer.echo(str(out_path))


def _config_to_mapping(result: ConfigLoadResult) -> Mapping[str, Any]:
    config = result.config
    return {
        "file_discovery": _jsonify(config.file_discovery),
        "output": _jsonify(config.output),
        "execution": _jsonify(config.execution),
        "dedupe": _jsonify(config.dedupe),
        "severity_rules": list(config.severity_rules),
        "tool_settings": _jsonify(config.tool_settings),
    }


def _jsonify(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonify(asdict(value))
    if hasattr(value, "to_dict"):
        return _jsonify(value.to_dict())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    return value


def _summarise_updates(updates: list[FieldUpdate]) -> list[str]:
    rendered: list[str] = []
    for update in updates:
        field_path = update.field if update.section == "root" else f"{update.section}.{update.field}"
        info = _summarise_value(field_path, update.value)
        rendered.append(f"- {field_path} <- {update.source} -> {info}")
    return rendered


def _summarise_value(field_path: str, value: Any) -> str:
    if field_path.startswith("tool_settings.") and isinstance(value, Mapping):
        parts = field_path.split(".", 2)
        tool = parts[1]
        schema = TOOL_SETTING_SCHEMA.get(tool, {})
        sections = []
        for key, entry in value.items():
            description = schema.get(key, {}).get("description")
            rendered = json.dumps(_jsonify(entry), sort_keys=True)
            if description:
                sections.append(f"{key}={rendered} ({description})")
            else:
                sections.append(f"{key}={rendered}")
        return "; ".join(sections) if sections else json.dumps({}, sort_keys=True)
    return json.dumps(_jsonify(value), sort_keys=True)


def _schema_to_markdown(schema: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for section, fields in schema.items():
        lines.append(f"## {section}")
        if isinstance(fields, Mapping) and "type" in fields:
            lines.append("| Field | Type | Default |")
            lines.append("| --- | --- | --- |")
            lines.append(f"| {section} | {fields['type']} | {json.dumps(fields['default'])} |")
            if section == "tool_settings":
                _append_tool_schema(lines, fields.get("tools", {}))
            lines.append("")
            continue
        lines.append("| Field | Type | Default |")
        lines.append("| --- | --- | --- |")
        if isinstance(fields, Mapping):
            for name, spec in fields.items():
                default = json.dumps(spec.get("default"))
                lines.append(f"| {name} | {spec.get('type')} | {default} |")
        if section == "tool_settings":
            _append_tool_schema(lines, fields.get("tools", {}))
        lines.append("")
    return "\n".join(lines)


def _append_tool_schema(lines: list[str], tools: Mapping[str, Any]) -> None:
    if not tools:
        return
    for tool, entries in sorted(tools.items()):
        lines.append(f"### {tool}")
        lines.append("| Setting | Type | Description |")
        lines.append("| --- | --- | --- |")
        for key, spec in sorted(entries.items()):
            lines.append(
                "| {key} | {type_} | {desc} |".format(
                    key=key,
                    type_=spec.get("type", ""),
                    desc=spec.get("description", ""),
                )
            )
        lines.append("")


def _diff_snapshots(base: Mapping[str, Any], updated: Mapping[str, Any]) -> Mapping[str, Any]:
    added: dict[str, Any] = {}
    removed: dict[str, Any] = {}
    changed: dict[str, Any] = {}

    def walk(prefix: tuple[str, ...], a: Any, b: Any) -> None:
        if a == b:
            return
        if isinstance(a, Mapping) and isinstance(b, Mapping):
            keys = set(a) | set(b)
            for key in keys:
                av = a.get(key, _MISSING)
                bv = b.get(key, _MISSING)
                walk(prefix + (str(key),), av, bv)
            return
        if a is _MISSING:
            if isinstance(b, Mapping):
                for key, value in b.items():
                    walk(prefix + (str(key),), _MISSING, value)
            else:
                added[".".join(prefix)] = b
        elif b is _MISSING:
            if isinstance(a, Mapping):
                for key, value in a.items():
                    walk(prefix + (str(key),), value, _MISSING)
            else:
                removed[".".join(prefix)] = a
        else:
            changed[".".join(prefix)] = {"from": a, "to": b}

    walk((), base, updated)
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
    }


_MISSING = object()


__all__ = ["config_app"]
