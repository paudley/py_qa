# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Reusable strategy factories referenced by the tool catalog."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from ..parsers.base import JsonParser, JsonTransform, TextParser, TextTransform
from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_helpers import _resolve_path, download_tool_artifact
from .catalog.types import JSONValue
from .command_options import (
    OptionMapping,
    command_option_map,
    compile_option_mappings,
    require_str,
)
from .json_diagnostics import JsonDiagnosticExtractor
from .loader import CatalogIntegrityError
from .project_scanner import (
    _is_under_any,
    _normalise_path_requirement,
    _path_matches_requirements,
    build_project_scanner,
)

TargetSelectorMode = Literal["filePattern"]
_TARGET_SELECTOR_MODE_FILE_PATTERN: Final[TargetSelectorMode] = "filePattern"

__all__ = [
    "command_download_binary",
    "command_option_map",
    "command_project_scanner",
    "install_download_artifact",
    "json_parser",
    "parser_json_diagnostics",
    "text_parser",
]


def install_download_artifact(config: Mapping[str, JSONValue]) -> Callable[[ToolContext], None]:
    """Return a catalog-driven installer for download artifacts.

    Args:
        config: Catalog configuration defining download parameters.

    Returns:
        Callable[[ToolContext], None]: Installer function that downloads the
        artifact when invoked.

    Raises:
        CatalogIntegrityError: If mandatory configuration keys are missing or
            malformed.

    """
    plain_config = _as_plain_json(config)
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("install_download_artifact: configuration must be an object")

    download_config = plain_config.get("download")
    if not isinstance(download_config, Mapping):
        raise CatalogIntegrityError("install_download_artifact: 'download' must be an object")
    download_mapping: Mapping[str, JSONValue] = download_config

    version_value = plain_config.get("version")
    if version_value is not None and not isinstance(version_value, str):
        raise CatalogIntegrityError(
            "install_download_artifact: 'version' must be a string when provided",
        )

    context_label = plain_config.get("contextLabel")
    if context_label is None:
        context_value = "install_download_artifact.download"
    elif isinstance(context_label, str) and context_label.strip():
        context_value = context_label
    else:
        raise CatalogIntegrityError(
            "install_download_artifact: 'contextLabel' must be a non-empty string",
        )

    def installer(ctx: ToolContext) -> None:
        cache_root = ctx.root / ".lint-cache"
        _download_artifact_for_tool(
            download_mapping,
            version=version_value,
            cache_root=cache_root,
            context=context_value,
        )

    return installer


def _load_attribute(path: str, *, context: str) -> Any:
    """Import an attribute from a dotted path with contextual errors.

    Args:
        path: Fully qualified dotted path to the target attribute.
        context: Human-readable location used to annotate raised errors.

    Returns:
        Any: Imported attribute referenced by ``path``.

    Raises:
        CatalogIntegrityError: If the module cannot be imported or the
            attribute is missing.

    """

    module_path, _, attribute = path.rpartition(".")
    if not module_path:
        raise CatalogIntegrityError(f"{context}: '{path}' is not a valid import path")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise CatalogIntegrityError(f"{context}: unable to import module '{module_path}'") from exc
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise CatalogIntegrityError(
            f"{context}: module '{module_path}' has no attribute '{attribute}'",
        ) from exc


def json_parser(config: Mapping[str, Any]) -> JsonParser:
    """Construct a ``JsonParser`` wrapping the configured transform callable.

    Args:
        config: Mapping containing ``transform`` (fully qualified function path).

    Returns:
        JsonParser: Parser instance invoking the referenced transform.

    Raises:
        CatalogIntegrityError: If the transform cannot be imported or is not callable.

    """
    transform_path = require_str(config, "transform", context="json_parser")
    transform_candidate = _load_attribute(transform_path, context="json_parser.transform")
    if not callable(transform_candidate):
        raise CatalogIntegrityError(f"json_parser: transform '{transform_path}' is not callable")
    json_transform = cast(JsonTransform, transform_candidate)
    return JsonParser(json_transform)


def text_parser(config: Mapping[str, Any]) -> TextParser:
    """Construct a ``TextParser`` wrapping the configured transform callable.

    Args:
        config: Mapping containing ``transform`` (fully qualified function path).

    Returns:
        TextParser: Parser instance invoking the referenced transform.

    Raises:
        CatalogIntegrityError: If the transform cannot be imported or is not callable.

    """
    transform_path = require_str(config, "transform", context="text_parser")
    transform_candidate = _load_attribute(transform_path, context="text_parser.transform")
    if not callable(transform_candidate):
        raise CatalogIntegrityError(f"text_parser: transform '{transform_path}' is not callable")
    text_transform = cast(TextTransform, transform_candidate)
    return TextParser(text_transform)


def parser_json_diagnostics(config: Mapping[str, Any]) -> JsonParser:
    """Construct a JSON parser that maps entries to ``RawDiagnostic`` objects.

    The returned parser iterates over the configured JSON path, applies field
    mappings, and produces :class:`RawDiagnostic` instances.  Catalog authors can
    customise the target collection via ``path`` (supporting dotted access with
    ``[*]`` wildcards) and declare how each diagnostic field should be resolved
    using ``mappings``.  Each mapping may specify either a dotted ``path`` or a
    constant ``value``; lookups can optionally supply ``map`` dictionaries and
    ``default`` fallbacks.

    Args:
        config: JSON-like mapping containing ``path`` (optional), ``inputFormat``
            (optional), and ``mappings`` (required).

    Returns:
        JsonParser: Parser capable of transforming JSON payloads into
        ``RawDiagnostic`` entries.

    Raises:
        CatalogIntegrityError: If the configuration does not match the expected
            structure.

    """
    plain_config = _as_plain_json(config)
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("parser_json_diagnostics: configuration must be an object")

    path_value = plain_config.get("path")
    if path_value is not None and not isinstance(path_value, str):
        raise CatalogIntegrityError("parser_json_diagnostics: 'path' must be a string")

    input_format = plain_config.get("inputFormat")
    if input_format is None:
        normalized_input_format = "json"
    elif isinstance(input_format, str):
        normalized_input_format = input_format.strip().lower()
        if normalized_input_format in {"jsonlines", "ndjson"}:
            normalized_input_format = "json-lines"
        if normalized_input_format not in {"json", "json-lines"}:
            raise CatalogIntegrityError(
                "parser_json_diagnostics: 'inputFormat' must be one of 'json' or 'json-lines'",
            )
    else:
        raise CatalogIntegrityError(
            "parser_json_diagnostics: 'inputFormat' must be a string when provided",
        )

    mappings = plain_config.get("mappings")
    if not isinstance(mappings, Mapping):
        raise CatalogIntegrityError("parser_json_diagnostics: 'mappings' must be an object")

    extractor = JsonDiagnosticExtractor(
        item_path=path_value,
        mapping_config=_as_plain_json(mappings),
        input_format=normalized_input_format,
    )
    return JsonParser(extractor.transform)


DEFAULT_BINARY_PLACEHOLDER = "${binary}"


@dataclass(slots=True)
class _DownloadBinaryStrategy(CommandBuilder):
    """Command builder that executes downloaded binaries with mapped options."""

    version: str | None
    download: Mapping[str, Any]
    base: tuple[str, ...]
    placeholder: str
    options: tuple[OptionMapping, ...]
    target_selector: _TargetSelector | None

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Compose the command line for the configured binary."""

        cache_root = ctx.root / ".lint-cache"
        binary = _download_artifact_for_tool(
            self.download,
            version=self.version,
            cache_root=cache_root,
            context="command_download_binary.download",
        )
        command = [str(binary) if part == self.placeholder else str(part) for part in self.base]
        for mapping in self.options:
            mapping.apply(ctx=ctx, command=command)
        if self.target_selector is not None:
            targets = self.target_selector.select(ctx, excluded=set())
            if targets:
                command.extend(targets)
        return tuple(command)


def command_download_binary(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder that downloads a binary and applies option maps."""

    plain_config = _as_plain_json(config)
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("command_download_binary: configuration must be an object")

    download_config = plain_config.get("download")
    if not isinstance(download_config, Mapping):
        raise CatalogIntegrityError("command_download_binary: 'download' must be an object")

    version_value = plain_config.get("version")
    if version_value is not None and not isinstance(version_value, str):
        raise CatalogIntegrityError(
            "command_download_binary: 'version' must be a string when provided",
        )

    placeholder_value = plain_config.get("binaryPlaceholder")
    if placeholder_value is None:
        placeholder = DEFAULT_BINARY_PLACEHOLDER
    elif isinstance(placeholder_value, str) and placeholder_value.strip():
        placeholder = placeholder_value
    else:
        raise CatalogIntegrityError(
            "command_download_binary: 'binaryPlaceholder' must be a non-empty string",
        )

    base_config = plain_config.get("base")
    if base_config is None:
        base_parts: tuple[str, ...] = (placeholder,)
    elif isinstance(base_config, Sequence) and not isinstance(base_config, (str, bytes, bytearray)):
        extracted = [str(part) for part in base_config if part is not None]
        base_parts = tuple(extracted) if extracted else (placeholder,)
    else:
        raise CatalogIntegrityError("command_download_binary: 'base' must be an array of arguments")
    if placeholder not in base_parts:
        base_parts = (placeholder,) + base_parts

    raw_options = cast(JSONValue | None, plain_config.get("options"))
    option_mappings = compile_option_mappings(
        raw_options,
        context="command_download_binary.options",
    )

    target_selector_config = plain_config.get("targets")
    target_selector = None
    if target_selector_config is not None:
        target_selector = _parse_target_selector(
            target_selector_config,
            context="command_download_binary.targets",
        )

    return _DownloadBinaryStrategy(
        version=version_value,
        download=download_config,
        base=base_parts,
        placeholder=placeholder,
        options=option_mappings,
        target_selector=target_selector,
    )


@dataclass(slots=True)
class _TargetSelector:
    """Derive command targets from file discovery metadata."""

    mode: TargetSelectorMode
    suffixes: tuple[str, ...]
    contains: tuple[str, ...]
    path_requires: tuple[tuple[str, ...], ...]
    fallback_directory: str | None
    default_to_root: bool

    def select(self, ctx: ToolContext, *, excluded: set[Path]) -> list[str]:
        """Return target arguments resolved from the tool context.

        Args:
            ctx: Tool execution context providing file selections.
            excluded: Filesystem paths that should be omitted from results.

        Returns:
            list[str]: Candidate target paths formatted for CLI consumption.

        """
        matched: list[Path] = []
        for path in ctx.files:
            candidate = path if isinstance(path, Path) else Path(str(path))
            text = str(candidate)
            if self.suffixes and not text.endswith(self.suffixes):
                continue
            if self.contains and not any(fragment in text for fragment in self.contains):
                continue
            if self.path_requires and not _path_matches_requirements(
                candidate,
                ctx.root,
                self.path_requires,
            ):
                continue
            matched.append(candidate)

        if matched:
            return [str(path) for path in matched]

        root = ctx.root
        if self.fallback_directory:
            fallback_path = _resolve_path(root, self.fallback_directory)
            if fallback_path.exists() and not _is_under_any(fallback_path, excluded):
                return [str(fallback_path)]

        if self.default_to_root:
            return [str(root)]
        return []


def _coerce_string_tuple(
    value: Any,
    *,
    field_name: str,
    context: str,
) -> tuple[str, ...]:
    """Return tuple of strings parsed from ``value``."""

    if value in (None, ()):  # treat empty as no entries
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if item is not None)
    raise CatalogIntegrityError(f"{context}: '{field_name}' must be a string or array of strings")


def _coerce_optional_non_empty_string(
    value: Any,
    *,
    field_name: str,
    context: str,
) -> str | None:
    """Return string when provided ensuring it is non-empty."""

    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    raise CatalogIntegrityError(
        f"{context}: '{field_name}' must be a non-empty string when provided",
    )


def _parse_target_selector(entry: Any, *, context: str) -> _TargetSelector:
    """Parse target selector configuration for binary download commands."""

    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError(f"{context}: target selector must be an object")

    mode_value = entry.get("type", _TARGET_SELECTOR_MODE_FILE_PATTERN)
    if not isinstance(mode_value, str):
        raise CatalogIntegrityError(f"{context}: 'type' must be a string")
    if mode_value.strip() != _TARGET_SELECTOR_MODE_FILE_PATTERN:
        raise CatalogIntegrityError(
            f"{context}: unsupported target selector type '{mode_value}'",
        )

    suffixes = _coerce_string_tuple(
        entry.get("suffixes", ()),
        field_name="suffixes",
        context=context,
    )
    contains = _coerce_string_tuple(
        entry.get("contains", ()),
        field_name="contains",
        context=context,
    )
    raw_requires = _coerce_string_tuple(
        entry.get("pathMustInclude", ()),
        field_name="pathMustInclude",
        context=context,
    )
    path_requires = tuple(
        requirement
        for item in raw_requires
        if (requirement := _normalise_path_requirement(item))
    )

    fallback_directory = _coerce_optional_non_empty_string(
        entry.get("fallbackDirectory"),
        field_name="fallbackDirectory",
        context=context,
    )

    default_to_root_value = entry.get("defaultToRoot", False)
    if not isinstance(default_to_root_value, bool):
        raise CatalogIntegrityError(f"{context}: 'defaultToRoot' must be a boolean")

    return _TargetSelector(
        mode=_TARGET_SELECTOR_MODE_FILE_PATTERN,
        suffixes=suffixes,
        contains=contains,
        path_requires=path_requires,
        fallback_directory=fallback_directory,
        default_to_root=default_to_root_value,
    )


def command_project_scanner(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a project-aware scanner command builder driven by catalog data."""

    plain_config = _as_plain_json(config)
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("command_project_scanner: configuration must be an object")

    return build_project_scanner(cast(Mapping[str, Any], plain_config))


def _download_artifact_for_tool(
    download_config: Mapping[str, Any],
    *,
    version: str | None,
    cache_root: Path,
    context: str,
) -> Path:
    """Download or reuse a tool artifact described by a catalog snippet.

    Args:
        download_config: Raw download configuration extracted from the tool
            catalog.
        version: Optional version override to request from the artifact
            provider.
        cache_root: Directory used to store cached artifacts.
        context: Identifier describing the caller for error messaging.

    Returns:
        Path: Filesystem path pointing to the resolved artifact.

    Raises:
        CatalogIntegrityError: If ``download_config`` is not mapping-like.

    """

    plain_config = _as_plain_json(download_config)
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError(f"{context}: download configuration must be a mapping")
    return download_tool_artifact(
        plain_config,
        version=version,
        cache_root=cache_root,
        context=context,
    )


def _as_plain_json(value: Any) -> Any:
    """Return ``value`` converted into a JSON-compatible structure.

    Args:
        value: Arbitrary configuration object.

    Returns:
        Any: Structure comprised exclusively of plain Python types suitable for
        JSON serialisation.

    """

    if isinstance(value, Mapping):
        return {str(key): _as_plain_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_as_plain_json(item) for item in value]
    return value
