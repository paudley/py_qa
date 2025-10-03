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
    JSON_FORMAT,
    build_config_diff,
    diff_snapshots,
    UnknownConfigLayerError,
    build_tool_schema_payload,
    load_config_with_trace,
    render_config_mapping,
    render_schema,
    schema_to_markdown,
    summarise_updates,
    summarise_value,
    validate_config,
    write_output,
)
from .shared import CLIError, build_cli_logger, register_command

config_app = create_typer(help="Inspect, validate, and document configuration layers.")


@register_command(
    config_app,
    name="show",
    help_text="Print the effective configuration for the project.",
)
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

    logger = build_cli_logger(emoji=True)
    try:
        result = load_config_with_trace(root, strict=strict, logger=logger)
    except CLIError as exc:
        raise typer.Exit(code=exc.exit_code) from exc

    if output_format.lower() != JSON_FORMAT:
        raise typer.BadParameter("Only JSON output is supported at the moment")

    payload = json.dumps(render_config_mapping(result), indent=2, sort_keys=True)
    logger.echo(payload)

    if trace and result.updates:
        logger.echo("\n# Overrides")
        for update in summarise_updates(result.updates):
            logger.echo(update)
    if result.warnings:
        logger.echo("\n# Warnings")
        for warning in result.warnings:
            logger.warn(f"- {warning}")


@register_command(
    config_app,
    name="validate",
    help_text="Ensure the configuration loads successfully.",
)
def config_validate(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    strict: bool = typer.Option(False, "--strict", help="Treat configuration warnings as errors."),
) -> None:
    """Ensure the configuration loads successfully."""
    logger = build_cli_logger(emoji=True)
    try:
        validate_config(root, strict=strict, logger=logger)
    except CLIError as exc:
        raise typer.Exit(code=exc.exit_code) from exc


@register_command(
    config_app,
    name="schema",
    help_text="Emit a machine-readable description of configuration fields.",
)
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

    logger = build_cli_logger(emoji=True)
    content = render_schema(output_format)
    write_output(content, out=out, logger=logger)


@register_command(
    config_app,
    name="diff",
    help_text="Show the difference between two configuration layers.",
)
def config_diff(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    from_layer: str = typer.Option("defaults", "--from", help="Baseline layer."),
    to_layer: str = typer.Option("final", "--to", help="Comparison layer."),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Write diff output to the provided path.",
    ),
) -> None:
    """Show the difference between two configuration layers."""
    logger = build_cli_logger(emoji=True)
    try:
        result = load_config_with_trace(root, strict=False, logger=logger)
    except CLIError as exc:
        raise typer.Exit(code=exc.exit_code) from exc
    try:
        diff_result = build_config_diff(
            result,
            from_layer=from_layer,
            to_layer=to_layer,
        )
    except UnknownConfigLayerError as exc:
        available = ", ".join(exc.available)
        raise typer.BadParameter(
            f"Unknown layer '{exc.layer}'. Available: {available}",
        ) from exc

    write_output(
        json.dumps(diff_result.diff, indent=2, sort_keys=True),
        out=out,
        logger=logger,
    )


@register_command(
    config_app,
    name="export-tools",
    help_text="Write the tool settings schema to disk.",
)
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

    logger = build_cli_logger(emoji=True)
    out_path = out.resolve()
    payload = build_tool_schema_payload()
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if check:
        if not out_path.exists():
            logger.fail(f"{out_path} is missing")
            raise typer.Exit(code=1)
        existing = out_path.read_text(encoding="utf-8")
        if existing != text:
            logger.fail(f"{out_path} is out of date")
            raise typer.Exit(code=1)
        logger.echo(str(out_path))
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    logger.echo(str(out_path))


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

    return schema_to_markdown(schema)


class ToolSettingsDoc(BaseModel):
    """Documentation model for tool settings schema output."""

    model_config = ConfigDict(extra="allow")

    tools: dict[str, dict[str, Any]]


__all__ = ["config_app"]
