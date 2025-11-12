# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Configuration inspection commands."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict

from pyqa.cli.protocols import TyperAdapter
from pyqa.core.config.loader import ConfigLoadResult, FieldUpdate
from pyqa.core.serialization import JsonValue
from pyqa.platform.paths import strip_repo_root_from_text

from ...core.shared import CLIError, build_cli_logger, register_command
from ...core.typer_ext import TyperAppConfig, create_typer
from .services import (
    JSON_FORMAT,
    SchemaFormatLiteral,
    UnknownConfigLayerError,
    build_config_diff,
    build_tool_schema_payload,
    diff_snapshots,
    load_config_with_trace,
    render_config_mapping,
    render_schema,
    schema_to_markdown,
    summarise_updates,
    summarise_value,
    validate_config,
    write_output,
)

_CONFIG_TY = create_typer(config=TyperAppConfig(help_text="Inspect, validate, and document configuration layers."))
config_app = TyperAdapter(_CONFIG_TY)


@register_command(
    config_app,
    name="show",
    help_text="Print the effective configuration for the project.",
)
def config_show(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    trace: bool = typer.Option(True, help="Show which source last set each field."),
    output_format: SchemaFormatLiteral = typer.Option(
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
    """Print the effective configuration for the project.

    Args:
        root: Project root directory used to locate configuration files.
        trace: Whether to display configuration overrides.
        output_format: Output format for the rendered configuration.
        strict: Whether configuration warnings should be treated as errors.

    Raises:
        typer.BadParameter: If an unsupported output format is requested.
        typer.Exit: Raised with a non-zero status when configuration loading fails.
    """

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
    """Ensure the configuration loads successfully.

    Args:
        root: Project root directory used to locate configuration files.
        strict: Whether configuration warnings should be treated as errors.

    Raises:
        typer.Exit: Raised with a non-zero status when validation fails.
    """
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
    output_format: SchemaFormatLiteral = typer.Option(
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
    """Emit a machine-readable description of configuration fields.

    Args:
        output_format: Requested schema format.
        out: Optional file path where the schema should be written.
    """

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
    """Show the difference between two configuration layers.

    Args:
        root: Project root directory used to locate configuration files.
        from_layer: Baseline configuration layer name.
        to_layer: Comparison configuration layer name.
        out: Optional file path where the diff should be written.

    Raises:
        typer.Exit: Raised when configuration loading fails.
        typer.BadParameter: Raised when the requested layers are unknown.
    """
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
    """Write the tool settings schema to disk.

    Args:
        out: Destination file for the tool schema JSON payload.
        check: When ``True`` verify the schema file is up-to-date instead of writing.

    Raises:
        typer.Exit: Raised with status 1 when ``check`` fails.
    """

    logger = build_cli_logger(emoji=True)
    out_path = out.resolve()
    payload = build_tool_schema_payload()
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    text = strip_repo_root_from_text(text)
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


def _config_to_mapping(result: ConfigLoadResult) -> Mapping[str, JsonValue]:
    """Produce config mappings for legacy callers.

    Args:
        result: Configuration load result returned by the loader.

    Returns:
        Mapping[str, JsonValue]: Serialisable configuration sections.
    """

    return render_config_mapping(result)


def _summarise_updates(updates: list[FieldUpdate]) -> list[str]:
    """Produce update summaries for legacy imports.

    Args:
        updates: Sequence of field updates produced by the configuration diff.

    Returns:
        list[str]: Human-readable descriptions of each update.
    """

    return summarise_updates(updates)


def _summarise_value(field_path: str, value: JsonValue) -> str:
    """Render update values for legacy imports.

    Args:
        field_path: Dot-delimited configuration field path.
        value: Value associated with the configuration update.

    Returns:
        str: Text representation suitable for CLI output.
    """

    return summarise_value(field_path, value)


def _diff_snapshots(
    left: Mapping[str, JsonValue],
    right: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    """Build snapshot diffs for legacy callers.

    Args:
        left: Baseline snapshot mapping.
        right: Comparison snapshot mapping.

    Returns:
        dict[str, JsonValue]: Differences between the provided snapshots.
    """

    return diff_snapshots(left, right)


def _schema_to_markdown(schema: Mapping[str, JsonValue]) -> str:
    """Render schema markdown for legacy callers.

    Args:
        schema: Mapping produced by :func:`generate_config_schema`.

    Returns:
        str: Markdown-formatted documentation.
    """

    return schema_to_markdown(schema)


class ToolSettingsDoc(BaseModel):
    """Define the documentation payload for tool settings output."""

    model_config = ConfigDict(extra="allow")

    tools: dict[str, dict[str, dict[str, str | int | float | bool | None | list[str]]]]


__all__ = ["config_app"]
