# SPDX-License-Identifier: MIT
"""Configuration inspection commands."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, ConfigDict

from ..config_loader import ConfigLoadResult, FieldUpdate
from .typer_ext import create_typer
from ._config_cmd_services import (
    FINAL_LAYER_KEY,
    JSON_FORMAT,
    JSON_TOOLS_FORMAT,
    collect_layer_snapshots,
    diff_snapshots,
    load_config,
    load_config_with_trace,
    render_config_mapping,
    render_schema,
    summarise_updates,
    summarise_value,
    write_output,
)

config_app = create_typer(help="Inspect, validate, and document configuration layers.")


@config_app.command("show")
def config_show(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    trace: bool = typer.Option(True, help="Show which source last set each field."),
    output_format: str = typer.Option(
        JSON_FORMAT,
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

    result = load_config_with_trace(root, strict=strict)

    if output_format.lower() != JSON_FORMAT:
        raise typer.BadParameter("Only JSON output is supported at the moment")

    payload = json.dumps(render_config_mapping(result), indent=2, sort_keys=True)
    typer.echo(payload)

    if trace and result.updates:
        typer.echo("\n# Overrides")
        for update in summarise_updates(result.updates):
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

    load_config(root, strict=strict)


@config_app.command("schema")
def config_schema(
    output_format: str = typer.Option(
        JSON_FORMAT,
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

    content = render_schema(output_format)
    write_output(content, out=out)


@config_app.command("diff")
def config_diff(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    from_layer: str = typer.Option("defaults", "--from", help="Baseline layer."),
    to_layer: str = typer.Option("final", "--to", help="Comparison layer."),
    out: Path | None = typer.Option(None, "--out", help="Write diff output to the provided path."),
) -> None:
    """Show the difference between two configuration layers."""

    result = load_config_with_trace(root, strict=False)
    snapshots = collect_layer_snapshots(result)
    from_key = from_layer.lower()
    to_key = to_layer.lower()
    if from_key not in snapshots:
        raise typer.BadParameter(
            f"Unknown layer '{from_layer}'. Available: {', '.join(sorted(snapshots))}",
        )
    if to_key not in snapshots:
        raise typer.BadParameter(
            f"Unknown layer '{to_layer}'. Available: {', '.join(sorted(snapshots))}",
        )

    diff = diff_snapshots(snapshots[from_key], snapshots[to_key])
    write_output(json.dumps(diff, indent=2, sort_keys=True), out=out)


@config_app.command("export-tools")
def config_export_tools(
    out: Path = typer.Argument(
        Path("tool-schema.json"),
        metavar="PATH",
        help="Destination file for the tool schema JSON.",
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help="Exit with status 1 if the target file is missing or out of date.",
    ),
) -> None:
    """Write the tool settings schema to disk."""

    from ..tools.settings import tool_setting_schema_as_dict  # local import

    out_path = out.resolve()
    payload: dict[str, Any] = {
        "_license": "SPDX-License-Identifier: MIT",
        "_copyright": "Copyright (c) 2025 Blackcat Informatics® Inc.",
    }
    payload.update(tool_setting_schema_as_dict())
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if check:
        if not out_path.exists():
            typer.echo(f"{out_path} is missing", err=True)
            raise typer.Exit(code=1)
        existing = out_path.read_text(encoding="utf-8")
        if existing != text:
            typer.echo(f"{out_path} is out of date", err=True)
            raise typer.Exit(code=1)
        typer.echo(str(out_path))
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    typer.echo(str(out_path))


def _config_to_mapping(result: ConfigLoadResult) -> Mapping[str, Any]:
    """Backwards compatible wrapper used by older callers."""

    return render_config_mapping(result)


def _summarise_updates(updates: list[FieldUpdate]) -> list[str]:
    """Backwards compatible wrapper around :func:`summarise_updates`."""

    return summarise_updates(updates)


def _summarise_value(field_path: str, value: Any) -> str:
    """Backwards compatible wrapper around :func:`summarise_value`."""

    return summarise_value(field_path, value)


def _diff_snapshots(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    """Backwards compatible wrapper for older imports."""

    return diff_snapshots(left, right)


def _schema_to_markdown(schema: Mapping[str, Any]) -> str:
    """Backwards compatible wrapper mirroring previous behaviour."""

    from ._config_cmd_services import schema_to_markdown

    return schema_to_markdown(schema)


class ToolSettingsDoc(BaseModel):
    """Documentation model for tool settings schema output."""

    model_config = ConfigDict(extra="allow")

    tools: dict[str, dict[str, Any]]


__all__ = ["config_app"]

