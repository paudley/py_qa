"""Reusable strategy factories referenced by the tool catalog."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast
from .catalog.types import JSONValue
from collections.abc import Iterator

from ..models import RawDiagnostic
from ..parsers.base import JsonParser, TextParser
from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_commands_python import (
    _discover_pylint_plugins,
    _python_target_version,
    _python_version_number,
    _python_version_tag,
    _pyupgrade_flag_from_version,
)
from ..tools.builtin_helpers import (
    _as_bool,
    _resolve_path,
    _setting,
    _settings_list,
    download_tool_artifact,
)
from .loader import CatalogIntegrityError

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
    """Return a catalog-driven installer for download artifacts."""

    plain_config = cast(JSONValue, _as_plain_json(config))
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("install_download_artifact: configuration must be an object")

    download_config = plain_config.get("download")
    if not isinstance(download_config, Mapping):
        raise CatalogIntegrityError("install_download_artifact: 'download' must be an object")
    download_mapping = cast(Mapping[str, JSONValue], download_config)

    version_value = plain_config.get("version")
    if version_value is not None and not isinstance(version_value, str):
        raise CatalogIntegrityError("install_download_artifact: 'version' must be a string when provided")

    context_label = plain_config.get("contextLabel")
    if context_label is None:
        context_value = "install_download_artifact.download"
    elif isinstance(context_label, str) and context_label.strip():
        context_value = context_label
    else:
        raise CatalogIntegrityError("install_download_artifact: 'contextLabel' must be a non-empty string")

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
        raise CatalogIntegrityError(f"{context}: module '{module_path}' has no attribute '{attribute}'") from exc


def _require_string_sequence(
    config: Mapping[str, JSONValue],
    key: str,
    *,
    context: str,
) -> tuple[str, ...]:
    value = config.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an array of arguments")
    result = tuple(str(item) for item in value)
    if not result:
        raise CatalogIntegrityError(f"{context}: '{key}' must contain at least one argument")
    return result


def _require_str(config: Mapping[str, JSONValue], key: str, *, context: str) -> str:
    value = config.get(key)
    if not isinstance(value, str):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be a string")
    return value


@dataclass(slots=True)
class _OptionMapping:
    """Declarative mapping between tool settings and CLI arguments."""

    settings: tuple[str, ...]
    option_type: Literal["value", "path", "args", "flag", "repeatFlag"]
    flag: str | None
    join_separator: str | None
    negate_flag: str | None
    literal_values: tuple[str, ...]
    default: JSONValue | None
    default_from: str | None
    transform: str | None

    def apply(self, ctx: ToolContext, command: list[str]) -> None:
        """Append CLI fragments derived from the configured option."""

        value = self._resolve_value(ctx)
        if value is None:
            return
        if self.transform:
            value = self._apply_transform(value, ctx)
        if self.option_type == "args":
            values = _settings_list(value)
            if not values:
                return
            if self.join_separator is not None:
                combined = self.join_separator.join(str(item) for item in values)
                if self.flag:
                    if self.flag.endswith("="):
                        command.append(f"{self.flag}{combined}")
                    else:
                        command.extend([self.flag, combined])
                else:
                    command.append(combined)
                return
            for entry in values:
                if self.flag:
                    text = str(entry)
                    if self.flag.endswith("="):
                        command.append(f"{self.flag}{text}")
                    else:
                        command.extend([self.flag, text])
                else:
                    command.append(str(entry))
            return
        if self.option_type == "path":
            values: Sequence[JSONValue]
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                values = cast(Sequence[JSONValue], value)
            else:
                values = (value,)
            for entry in values:
                if entry is None:
                    continue
                if isinstance(entry, (str, Path)) and str(entry) in self.literal_values:
                    resolved = str(entry)
                else:
                    resolved = str(_resolve_path(ctx.root, entry))
                if self.flag:
                    if self.flag.endswith("="):
                        command.append(f"{self.flag}{resolved}")
                    else:
                        command.extend([self.flag, resolved])
                else:
                    command.append(resolved)
            return
        if self.option_type == "value":
            text = str(value)
            if self.flag:
                if self.flag.endswith("="):
                    command.append(f"{self.flag}{text}")
                else:
                    command.extend([self.flag, text])
            else:
                command.append(text)
            return
        if self.option_type == "flag":
            bool_value = _as_bool(value)
            if bool_value is None:
                return
            if bool_value:
                if self.flag:
                    command.append(self.flag)
            elif self.negate_flag:
                command.append(self.negate_flag)
            return
        if self.option_type == "repeatFlag":
            if self.flag is None:
                return
            count = _coerce_repeat_count(value)
            if count == 0:
                if self.negate_flag:
                    command.append(self.negate_flag)
                return
            command.extend([self.flag] * count)
            return
        raise CatalogIntegrityError("command_option_map: unsupported option type")

    def _resolve_value(self, ctx: ToolContext) -> JSONValue | None:
        value: JSONValue | None = None
        for name in self.settings:
            candidate = cast(JSONValue | None, _setting(ctx.settings, name))
            if candidate is not None:
                value = candidate
                break
        if value is None and self.default is not None:
            value = self.default
        if value is None and self.default_from is not None:
            value = _resolve_default_reference(self.default_from, ctx)
        return value

    def _apply_transform(self, value: JSONValue, ctx: ToolContext) -> JSONValue:
        if self.transform == "python_version_tag":
            return _python_version_tag(_coerce_version_string(value, ctx))
        if self.transform == "python_version_number":
            return _python_version_number(_coerce_version_string(value, ctx))
        if self.transform == "pyupgrade_flag":
            return _pyupgrade_flag_from_version(_coerce_version_string(value, ctx))
        if self.transform == "strictness_is_strict":
            if isinstance(value, str):
                return value.strip().lower() == "strict"
            if isinstance(value, bool):
                return value
            return bool(value)
        if self.transform == "strictness_is_lenient":
            if isinstance(value, str):
                return value.strip().lower() == "lenient"
            return False
        if self.transform == "bool_to_yn":
            bool_value = _as_bool(value)
            if bool_value is None:
                bool_value = bool(value)
            return "y" if bool_value else "n"
        if self.transform == "bool_to_str":
            bool_value = _as_bool(value)
            if bool_value is None:
                bool_value = bool(value)
            return "true" if bool_value else "false"
        return value


def _resolve_default_reference(token: str, ctx: ToolContext) -> JSONValue | None:
    mapping = {
        "execution.line_length": ctx.cfg.execution.line_length,
        "complexity.max_complexity": ctx.cfg.complexity.max_complexity,
        "complexity.max_arguments": ctx.cfg.complexity.max_arguments,
        "severity.bandit_level": ctx.cfg.severity.bandit_level,
        "severity.bandit_confidence": ctx.cfg.severity.bandit_confidence,
        "severity.pylint_fail_under": ctx.cfg.severity.pylint_fail_under,
        "severity.max_warnings": ctx.cfg.severity.max_warnings,
        "strictness.type_checking": ctx.cfg.strictness.type_checking,
        "execution.sql_dialect": getattr(ctx.cfg.execution, "sql_dialect", None),
    }
    if token in mapping:
        return mapping[token]
    if token == "python.target_version_tag":
        return _python_version_tag(_python_target_version(ctx))
    if token == "python.target_version":
        return _python_target_version(ctx)
    if token == "python.target_version_number":
        return _python_version_number(_python_target_version(ctx))
    if token == "python.discover_pylint_plugins":
        plugins = _discover_pylint_plugins(ctx.root)
        return tuple(plugins)
    if token == "tool.root":
        return str(ctx.root)
    if token.startswith("tool_setting."):
        setting_name = token.split(".", 1)[1]
        return cast(JSONValue | None, _setting(ctx.settings, setting_name))
    return None


def _coerce_repeat_count(value: JSONValue) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return max(int(value), 0)
    try:
        return max(int(str(value)), 0)
    except (TypeError, ValueError):
        return 0


def _coerce_version_string(value: JSONValue, ctx: ToolContext) -> str:
    if value is None:
        return _python_target_version(ctx)
    return str(value)


def json_parser(config: Mapping[str, Any]) -> JsonParser:
    """Construct a ``JsonParser`` wrapping the configured transform callable.

    Args:
        config: Mapping containing ``transform`` (fully qualified function path).

    Returns:
        JsonParser: Parser instance invoking the referenced transform.

    Raises:
        CatalogIntegrityError: If the transform cannot be imported or is not callable.
    """

    transform_path = _require_str(config, "transform", context="json_parser")
    transform = _load_attribute(transform_path, context="json_parser.transform")
    if not callable(transform):
        raise CatalogIntegrityError(f"json_parser: transform '{transform_path}' is not callable")
    return JsonParser(transform)


def text_parser(config: Mapping[str, Any]) -> TextParser:
    """Construct a ``TextParser`` wrapping the configured transform callable.

    Args:
        config: Mapping containing ``transform`` (fully qualified function path).

    Returns:
        TextParser: Parser instance invoking the referenced transform.

    Raises:
        CatalogIntegrityError: If the transform cannot be imported or is not callable.
    """

    transform_path = _require_str(config, "transform", context="text_parser")
    transform = _load_attribute(transform_path, context="text_parser.transform")
    if not callable(transform):
        raise CatalogIntegrityError(f"text_parser: transform '{transform_path}' is not callable")
    return TextParser(transform)


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
            raise CatalogIntegrityError("parser_json_diagnostics: 'inputFormat' must be one of 'json' or 'json-lines'")
    else:
        raise CatalogIntegrityError("parser_json_diagnostics: 'inputFormat' must be a string when provided")

    mappings = plain_config.get("mappings")
    if not isinstance(mappings, Mapping):
        raise CatalogIntegrityError("parser_json_diagnostics: 'mappings' must be an object")

    extractor = _JsonDiagnosticExtractor(
        item_path=path_value,
        mapping_config=_as_plain_json(mappings),
        input_format=normalized_input_format,
    )
    return JsonParser(extractor.transform)


class _PathComponent(NamedTuple):
    """Single navigation step within a dotted/array JSON path."""

    kind: Literal["key", "index", "wildcard"]
    value: str | int | None


@dataclass(slots=True)
class _FieldSpec:
    """Descriptor instructing how to resolve a diagnostic field from JSON."""

    name: str
    path: tuple[_PathComponent, ...] | None
    value: Any | None
    has_value: bool
    default: Any | None
    has_default: bool
    remap: Mapping[str, Any]

    def resolve(self, entry: Mapping[str, Any]) -> Any | None:
        """Return the resolved field value for *entry* applying defaults/maps."""

        if self.has_value:
            return self.value
        value = _extract_path(entry, self.path) if self.path is not None else None
        if value is None and self.has_default:
            return self.default
        if value is None:
            return None
        if self.remap:
            mapped = self._apply_remap(value)
            if mapped is not None:
                return mapped
            if self.has_default:
                return self.default
        return value

    def _apply_remap(self, value: Any) -> Any | None:
        """Return remapped value when a mapping entry matches ``value``."""

        if isinstance(value, str):
            key = value.casefold()
            return self.remap.get(key, self.remap.get(value))
        key = str(value).casefold()
        return self.remap.get(key)


@dataclass(slots=True)
class _JsonDiagnosticExtractor:
    """Transform JSON payloads into ``RawDiagnostic`` sequences."""

    item_path: str | None
    mapping_config: Mapping[str, Any]
    input_format: str
    _field_specs: Mapping[str, _FieldSpec] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Normalise configuration into efficient lookup structures."""

        self._field_specs = self._build_field_specs(self.mapping_config)
        mandatory_fields = {"message"}
        missing = mandatory_fields - self._field_specs.keys()
        if missing:
            names = ", ".join(sorted(missing))
            raise CatalogIntegrityError(f"parser_json_diagnostics: missing required field mapping(s): {names}")

    def transform(self, payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
        """Convert JSON payload into ``RawDiagnostic`` entries.

        Args:
            payload: Parsed JSON output from the tool process.
            context: Execution context (unused but part of the interface).

        Returns:
            Sequence[RawDiagnostic]: Diagnostics extracted from the payload.
        """

        del context
        items = list(self._iterate_items(payload))
        diagnostics: list[RawDiagnostic] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            diagnostic = self._build_diagnostic(item)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        return diagnostics

    def _iterate_items(self, payload: Any) -> Iterator[Any]:
        """Yield items addressed by ``item_path`` from *payload*."""

        if self.item_path is None or not self.item_path.strip():
            if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
                yield from payload
            elif payload is not None:
                yield payload
            return

        tokens = _tokenize_path(self.item_path, allow_wildcards=True)
        nodes: list[Any] = [payload]
        for token in tokens:
            nodes = list(_descend(nodes, token))
            if not nodes:
                return
        yield from nodes

    def _build_diagnostic(self, entry: Mapping[str, Any]) -> RawDiagnostic | None:
        """Return a ``RawDiagnostic`` constructed from *entry*."""

        values: dict[str, Any] = {}
        for name, spec in self._field_specs.items():
            values[name] = spec.resolve(entry)

        message_value = values.get("message")
        if message_value is None:
            return None

        diagnostic = RawDiagnostic(
            file=_coerce_str(values.get("file")),
            line=_coerce_int(values.get("line")),
            column=_coerce_int(values.get("column")),
            severity=_coerce_severity(values.get("severity")),
            message=str(message_value),
            code=_coerce_str(values.get("code")),
            tool=_coerce_str(values.get("tool")),
            group=_coerce_str(values.get("group")),
            function=_coerce_str(values.get("function")),
        )
        return diagnostic

    def _build_field_specs(self, config: Mapping[str, Any]) -> Mapping[str, _FieldSpec]:
        """Normalize mapping configuration into ``_FieldSpec`` instances."""

        allowed_fields = {
            "file",
            "line",
            "column",
            "code",
            "message",
            "severity",
            "tool",
            "group",
            "function",
        }
        specs: dict[str, _FieldSpec] = {}
        for field_name, raw_spec in config.items():
            if field_name not in allowed_fields:
                raise CatalogIntegrityError(f"parser_json_diagnostics: unsupported field '{field_name}' in mappings")
            specs[field_name] = self._build_field_spec(field_name, raw_spec)
        return specs

    def _build_field_spec(self, name: str, raw_spec: Any) -> _FieldSpec:
        """Create a field specification for a single diagnostic attribute."""

        if isinstance(raw_spec, str):
            path_tokens = _tokenize_path(raw_spec, allow_wildcards=False)
            return _FieldSpec(
                name=name,
                path=path_tokens,
                value=None,
                has_value=False,
                default=None,
                has_default=False,
                remap={},
            )

        if not isinstance(raw_spec, Mapping):
            raise CatalogIntegrityError(
                f"parser_json_diagnostics: mapping for field '{name}' must be a string or object"
            )

        path_value = raw_spec.get("path")
        if path_value is None:
            path_tokens: tuple[_PathComponent, ...] | None = None
        elif isinstance(path_value, str):
            path_tokens = _tokenize_path(path_value, allow_wildcards=False)
        else:
            raise CatalogIntegrityError(
                f"parser_json_diagnostics: field '{name}' has non-string 'path' configuration"
            )

        const_value = raw_spec.get("value")
        has_const = "value" in raw_spec

        default_value = raw_spec.get("default")
        has_default = "default" in raw_spec

        map_value = raw_spec.get("map")
        remap: dict[str, Any] = {}
        if map_value is not None:
            if not isinstance(map_value, Mapping):
                raise CatalogIntegrityError(
                    f"parser_json_diagnostics: field '{name}' has non-object 'map' configuration"
                )
            for key, mapped_value in map_value.items():
                if not isinstance(key, str):
                    raise CatalogIntegrityError(
                        f"parser_json_diagnostics: field '{name}' mapping keys must be strings"
                    )
                remap[key.casefold()] = mapped_value
                remap[key] = mapped_value

        return _FieldSpec(
            name=name,
            path=path_tokens,
            value=const_value,
            has_value=has_const,
            default=default_value,
            has_default=has_default,
            remap=remap,
        )


@dataclass(slots=True)
class _OptionCommandStrategy(CommandBuilder):
    """Command builder driven by declarative option mappings."""

    base: tuple[str, ...]
    append_files: bool
    options: tuple[_OptionMapping, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        command = list(self.base)
        for option in self.options:
            option.apply(ctx, command)
        if self.append_files and ctx.files:
            command.extend(str(path) for path in ctx.files)
        return tuple(command)


def command_option_map(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder that maps settings to CLI flags.

    Args:
        config: Mapping describing the base command, optional file append
            behaviour, and option mappings.

    Returns:
        CommandBuilder: Strategy capable of rendering the command for the
        configured tool action.

    Raises:
        CatalogIntegrityError: If required configuration fields are missing or
            invalid.
    """

    base_args = _require_string_sequence(config, "base", context="command_option_map")
    append_files = bool(config.get("appendFiles", True))
    options_config = config.get("options", ())
    mappings: list[_OptionMapping] = []
    if options_config is not None:
        if not isinstance(options_config, Sequence) or isinstance(options_config, (str, bytes, bytearray)):
            raise CatalogIntegrityError("command_option_map: 'options' must be an array of objects")
        for index, entry in enumerate(options_config):
            context = f"command_option_map.options[{index}]"
            if not isinstance(entry, Mapping):
                raise CatalogIntegrityError(f"{context}: option must be an object")
            mappings.append(_parse_option_mapping(entry, context=context))
    return _OptionCommandStrategy(
        base=base_args,
        append_files=append_files,
        options=tuple(mappings),
    )


def _parse_option_mapping(entry: Mapping[str, Any], *, context: str) -> _OptionMapping:
    setting_value = entry.get("setting")
    if isinstance(setting_value, str):
        names = (setting_value,)
    elif isinstance(setting_value, Sequence) and not isinstance(setting_value, (str, bytes, bytearray)):
        names = tuple(str(name) for name in setting_value if name is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'setting' must be a string or array of strings")
    if not names:
        raise CatalogIntegrityError(f"{context}: 'setting' must provide at least one entry")

    type_value = entry.get("type", "value")
    if not isinstance(type_value, str):
        raise CatalogIntegrityError(f"{context}: 'type' must be a string")
    normalized_type_key = type_value.strip().lower()
    type_mapping: dict[str, Literal["value", "path", "args", "flag", "repeatFlag"]] = {
        "value": "value",
        "path": "path",
        "args": "args",
        "flag": "flag",
        "repeatflag": "repeatFlag",
    }
    option_type = type_mapping.get(normalized_type_key)
    if option_type is None:
        raise CatalogIntegrityError(f"{context}: unsupported option type '{type_value}'")

    flag_value = entry.get("flag")
    if flag_value is not None and not isinstance(flag_value, str):
        raise CatalogIntegrityError(f"{context}: 'flag' must be a string when provided")
    join_value = entry.get("joinWith")
    if join_value is None:
        join_separator = None
    elif isinstance(join_value, str):
        join_separator = join_value
    else:
        raise CatalogIntegrityError(f"{context}: 'joinWith' must be a string when provided")

    negate_flag_value = entry.get("negateFlag")
    if negate_flag_value is None:
        negate_flag = None
    elif isinstance(negate_flag_value, str):
        negate_flag = negate_flag_value
    else:
        raise CatalogIntegrityError(f"{context}: 'negateFlag' must be a string when provided")

    literal_values_value = entry.get("literalValues", ())
    if isinstance(literal_values_value, str):
        literal_values = (literal_values_value,)
    elif isinstance(literal_values_value, Sequence) and not isinstance(
        literal_values_value,
        (str, bytes, bytearray),
    ):
        literal_values = tuple(str(item) for item in literal_values_value if item is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'literalValues' must be a string or array of strings")

    default_value = entry.get("default")
    default_from_value = entry.get("defaultFrom")
    if default_from_value is not None and not isinstance(default_from_value, str):
        raise CatalogIntegrityError(f"{context}: 'defaultFrom' must be a string when provided")

    transform_value = entry.get("transform")
    if transform_value is not None and not isinstance(transform_value, str):
        raise CatalogIntegrityError(f"{context}: 'transform' must be a string when provided")

    return _OptionMapping(
        settings=names,
        option_type=option_type,
        flag=flag_value,
        join_separator=join_separator,
        negate_flag=negate_flag,
        literal_values=literal_values,
        default=cast(JSONValue | None, default_value),
        default_from=default_from_value,
        transform=transform_value,
    )


def _coerce_int(value: Any | None) -> int | None:
    """Return an ``int`` when *value* can be losslessly coerced."""

    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 10)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any | None) -> str | None:
    """Return a ``str`` representation of *value* when not ``None``."""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_severity(value: Any | None) -> str | None:
    """Return severity coerced to a ``str`` where applicable."""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _descend(nodes: Iterable[Any], token: _PathComponent) -> Iterator[Any]:
    """Yield nodes after applying a path ``token`` to *nodes*."""

    if token.kind == "key":
        key = token.value
        for node in nodes:
            if isinstance(node, Mapping) and isinstance(key, str):
                if key in node:
                    yield node[key]
    elif token.kind == "index":
        index = int(token.value) if token.value is not None else 0
        for node in nodes:
            if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
                if -len(node) <= index < len(node):
                    yield node[index]
    elif token.kind == "wildcard":
        for node in nodes:
            if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
                yield from node


def _extract_path(entry: Mapping[str, Any], path: tuple[_PathComponent, ...] | None) -> Any | None:
    """Resolve *path* against *entry* returning the final value."""

    if not path:
        return entry
    current: Any = entry
    for token in path:
        if token.kind == "key":
            if not isinstance(current, Mapping):
                return None
            key = token.value
            if not isinstance(key, str) or key not in current:
                return None
            current = current[key]
        elif token.kind == "index":
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes, bytearray)):
                return None
            index = int(token.value) if token.value is not None else 0
            if index >= len(current) or index < -len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _tokenize_path(path: str, *, allow_wildcards: bool) -> tuple[_PathComponent, ...]:
    """Tokenise dotted/array path expressions into components."""

    trimmed = path.strip()
    if not trimmed:
        return ()

    tokens: list[_PathComponent] = []
    buffer: list[str] = []
    index = 0
    length = len(trimmed)
    while index < length:
        char = trimmed[index]
        if char == ".":
            _flush_buffer_as_key(buffer, tokens)
            index += 1
            continue
        if char == "[":
            _flush_buffer_as_key(buffer, tokens)
            closing = trimmed.find("]", index)
            if closing == -1:
                raise CatalogIntegrityError(f"parser_json_diagnostics: unmatched '[' in path '{path}'")
            segment = trimmed[index + 1 : closing].strip()
            if segment in {"", "*"}:
                if not allow_wildcards:
                    raise CatalogIntegrityError(
                        f"parser_json_diagnostics: wildcards are not permitted in field paths ('{path}')"
                    )
                tokens.append(_PathComponent("wildcard", None))
            else:
                if segment.startswith('"') and segment.endswith('"') and len(segment) >= 2:
                    segment = segment[1:-1]
                if segment.lstrip("-").isdigit():
                    tokens.append(_PathComponent("index", int(segment)))
                else:
                    tokens.append(_PathComponent("key", segment))
            index = closing + 1
            continue
        buffer.append(char)
        index += 1

    _flush_buffer_as_key(buffer, tokens)

    filtered: list[_PathComponent] = []
    for token in tokens:
        if token.kind == "key" and isinstance(token.value, str) and token.value in {"", "$"}:
            continue
        filtered.append(token)
    return tuple(filtered)


def _flush_buffer_as_key(buffer: list[str], tokens: list[_PathComponent]) -> None:
    """Append buffered characters as a key token when non-empty."""

    if not buffer:
        return
    key = "".join(buffer).strip()
    buffer.clear()
    if key:
        tokens.append(_PathComponent("key", key))


DEFAULT_BINARY_PLACEHOLDER = "${binary}"


@dataclass(slots=True)
class _CommandOption:
    """Declarative mapping between tool settings and CLI arguments."""

    primary: str
    aliases: tuple[str, ...]
    kind: Literal["value", "path", "args", "flag", "repeatFlag"]
    flag: str | None
    join_separator: str | None
    negate_flag: str | None
    literal_values: tuple[str, ...]
    default: Any | None
    default_from: str | None

    def apply(self, *, ctx: ToolContext, command: list[str]) -> None:
        """Append CLI arguments derived from the configured option.

        Args:
            ctx: Tool execution context containing user settings.
            command: Mutable command list to augment with option-derived values.
        """

        raw_value = _setting(ctx.settings, self.primary, *self.aliases)
        if raw_value is None and self.default is not None:
            raw_value = self.default
        if raw_value is None and self.default_from is not None:
            raw_value = _resolve_default_reference(self.default_from, ctx)
        if raw_value is None:
            return
        if self.kind == "args":
            values = _settings_list(raw_value)
            if not values:
                return
            if self.join_separator is not None:
                combined = self.join_separator.join(str(item) for item in values)
                if self.flag:
                    command.extend([self.flag, combined])
                else:
                    command.append(combined)
                return
            for entry in values:
                if self.flag:
                    command.extend([self.flag, str(entry)])
                else:
                    command.append(str(entry))
            return
        if self.kind == "path":
            if isinstance(raw_value, (str, Path)) and str(raw_value) in self.literal_values:
                value = str(raw_value)
            else:
                value = str(_resolve_path(ctx.root, raw_value))
            if self.flag:
                command.extend([self.flag, value])
            else:
                command.append(value)
            return
        if self.kind == "value":
            value = str(raw_value)
            if self.flag:
                command.extend([self.flag, value])
            else:
                command.append(value)
            return
        if self.kind == "flag":
            bool_value = _as_bool(raw_value)
            if bool_value is None:
                return
            if bool_value:
                if self.flag:
                    command.append(self.flag)
            elif self.negate_flag:
                command.append(self.negate_flag)
            return
        if self.kind == "repeatFlag":
            if self.flag is None:
                return
            count: int
            if isinstance(raw_value, bool):
                count = 1 if raw_value else 0
            elif isinstance(raw_value, (int, float)):
                count = max(int(raw_value), 0)
            else:
                try:
                    count = max(int(str(raw_value)), 0)
                except (TypeError, ValueError):
                    count = 0
            if count == 0:
                if self.negate_flag:
                    command.append(self.negate_flag)
                return
            command.extend([self.flag] * count)
            return
        raise CatalogIntegrityError("command option encountered unsupported type")


@dataclass(slots=True)
class _TargetSelector:
    """Derive command targets from file discovery metadata."""

    mode: Literal["filePattern"]
    suffixes: tuple[str, ...]
    contains: tuple[str, ...]
    fallback_directory: str | None
    default_to_root: bool

    def select(self, ctx: ToolContext, *, excluded: set[Path]) -> list[str]:
        """Return target arguments resolved from the tool context."""

        matched: list[Path] = []
        for path in ctx.files:
            if not isinstance(path, Path):
                candidate = Path(str(path))
            else:
                candidate = path
            text = str(candidate)
            if self.suffixes and not text.endswith(self.suffixes):
                continue
            if self.contains and not any(fragment in text for fragment in self.contains):
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


@dataclass(slots=True)
class _DownloadBinaryStrategy(CommandBuilder):
    """Command builder that executes downloaded binaries with mapped options."""

    version: str | None
    download: Mapping[str, Any]
    base: tuple[str, ...]
    placeholder: str
    options: tuple[_CommandOption, ...]
    target_selector: _TargetSelector | None

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Compose the command line for the configured binary.

        Args:
            ctx: Tool execution context containing repository metadata and settings.

        Returns:
            Sequence[str]: Fully rendered command arguments.
        """

        cache_root = ctx.root / ".lint-cache"
        binary = _download_artifact_for_tool(
            self.download,
            version=self.version,
            cache_root=cache_root,
            context="command_download_binary.download",
        )
        command = [str(binary) if part == self.placeholder else str(part) for part in self.base]
        for option in self.options:
            option.apply(ctx=ctx, command=command)
        if self.target_selector is not None:
            targets = self.target_selector.select(ctx, excluded=set())
            if targets:
                command.extend(targets)
        return tuple(command)


def command_download_binary(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder that downloads a binary and applies option maps.

    Args:
        config: Mapping describing the download specification, base arguments, and
            option mappings.

    Returns:
        CommandBuilder: Builder that materialises the CLI invocation for the tool.

    Raises:
        CatalogIntegrityError: If the configuration is missing required fields or
            contains invalid values.
    """

    plain_config = _as_plain_json(config)
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("command_download_binary: configuration must be an object")

    download_config = plain_config.get("download")
    if not isinstance(download_config, Mapping):
        raise CatalogIntegrityError("command_download_binary: 'download' must be an object")

    version_value = plain_config.get("version")
    if version_value is not None and not isinstance(version_value, str):
        raise CatalogIntegrityError("command_download_binary: 'version' must be a string when provided")

    placeholder_value = plain_config.get("binaryPlaceholder")
    if placeholder_value is None:
        placeholder = DEFAULT_BINARY_PLACEHOLDER
    elif isinstance(placeholder_value, str) and placeholder_value.strip():
        placeholder = placeholder_value
    else:
        raise CatalogIntegrityError("command_download_binary: 'binaryPlaceholder' must be a non-empty string")

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

    options_config = plain_config.get("options")
    option_specs: list[_CommandOption] = []
    if options_config is not None:
        if not isinstance(options_config, Sequence) or isinstance(options_config, (str, bytes, bytearray)):
            raise CatalogIntegrityError("command_download_binary: 'options' must be an array of objects")
        for index, entry in enumerate(options_config):
            option_specs.append(_parse_command_option(entry, index=index))

    target_selector_config = plain_config.get("targets")
    target_selector = None
    if target_selector_config is not None:
        target_selector = _parse_target_selector(target_selector_config, context="command_download_binary.targets")

    return _DownloadBinaryStrategy(
        version=version_value,
        download=download_config,
        base=base_parts,
        placeholder=placeholder,
        options=tuple(option_specs),
        target_selector=target_selector,
    )


def _parse_command_option(entry: Any, *, index: int) -> _CommandOption:
    """Materialise a command option from catalog configuration.

    Args:
        entry: Raw JSON entry describing the option.
        index: Index of the option within the configuration array, used for errors.

    Returns:
        _DownloadBinaryOption: Parsed option ready for application during command build.

    Raises:
        CatalogIntegrityError: If the option definition is malformed.
    """

    context = f"command_download_binary.options[{index}]"
    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError(f"{context}: option must be an object")

    setting_value = entry.get("setting")
    if isinstance(setting_value, str):
        names = (setting_value,)
    elif isinstance(setting_value, Sequence) and not isinstance(setting_value, (str, bytes, bytearray)):
        names = tuple(str(name) for name in setting_value if name is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'setting' must be a string or array of strings")
    if not names:
        raise CatalogIntegrityError(f"{context}: 'setting' must provide at least one entry")

    type_value = entry.get("type", "value")
    if not isinstance(type_value, str):
        raise CatalogIntegrityError(f"{context}: 'type' must be a string")
    normalized_type_key = type_value.strip().lower()
    type_mapping = {
        "value": "value",
        "path": "path",
        "args": "args",
        "flag": "flag",
        "repeatflag": "repeatFlag",
    }
    normalized_type = type_mapping.get(normalized_type_key)
    if normalized_type is None:
        raise CatalogIntegrityError(f"{context}: unsupported option type '{type_value}'")

    flag_value = entry.get("flag")
    if flag_value is not None and not isinstance(flag_value, str):
        raise CatalogIntegrityError(f"{context}: 'flag' must be a string when provided")
    join_value = entry.get("joinWith")
    if join_value is None:
        join_separator = None
    elif isinstance(join_value, str):
        join_separator = join_value
    else:
        raise CatalogIntegrityError(f"{context}: 'joinWith' must be a string when provided")

    negate_flag_value = entry.get("negateFlag")
    if negate_flag_value is None:
        negate_flag = None
    elif isinstance(negate_flag_value, str):
        negate_flag = negate_flag_value
    else:
        raise CatalogIntegrityError(f"{context}: 'negateFlag' must be a string when provided")

    literal_values_value = entry.get("literalValues", ())
    if isinstance(literal_values_value, str):
        literal_values = (literal_values_value,)
    elif isinstance(literal_values_value, Sequence) and not isinstance(literal_values_value, (str, bytes, bytearray)):
        literal_values = tuple(str(item) for item in literal_values_value if item is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'literalValues' must be a string or array of strings")

    default_value = entry.get("default")
    default_from_value = entry.get("defaultFrom")
    if default_from_value is None:
        default_from = None
    elif isinstance(default_from_value, str):
        default_from = default_from_value
    else:
        raise CatalogIntegrityError(f"{context}: 'defaultFrom' must be a string when provided")

    return _CommandOption(
        primary=names[0],
        aliases=tuple(names[1:]),
        kind=cast(Literal["value", "path", "args", "flag", "repeatFlag"], normalized_type),
        flag=flag_value,
        join_separator=join_separator,
        negate_flag=negate_flag,
        literal_values=literal_values,
        default=default_value,
        default_from=default_from,
    )


def _parse_target_selector(entry: Any, *, context: str) -> _TargetSelector:
    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError(f"{context}: target selector must be an object")

    mode_value = entry.get("type", "filePattern")
    if not isinstance(mode_value, str):
        raise CatalogIntegrityError(f"{context}: 'type' must be a string")
    normalized_mode = mode_value.strip()
    if normalized_mode != "filePattern":
        raise CatalogIntegrityError(f"{context}: unsupported target selector type '{mode_value}'")

    suffixes_value = entry.get("suffixes", ())
    if isinstance(suffixes_value, str):
        suffixes = (suffixes_value,)
    elif isinstance(suffixes_value, Sequence) and not isinstance(suffixes_value, (str, bytes, bytearray)):
        suffixes = tuple(str(item) for item in suffixes_value if item is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'suffixes' must be a string or array of strings")

    contains_value = entry.get("contains", ())
    if isinstance(contains_value, str):
        contains = (contains_value,)
    elif isinstance(contains_value, Sequence) and not isinstance(contains_value, (str, bytes, bytearray)):
        contains = tuple(str(item) for item in contains_value if item is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'contains' must be a string or array of strings")

    fallback_value = entry.get("fallbackDirectory")
    if fallback_value is None:
        fallback_directory: str | None = None
    elif isinstance(fallback_value, str) and fallback_value.strip():
        fallback_directory = fallback_value
    else:
        raise CatalogIntegrityError(f"{context}: 'fallbackDirectory' must be a non-empty string if provided")

    default_to_root_value = entry.get("defaultToRoot", False)
    if isinstance(default_to_root_value, bool):
        default_to_root = default_to_root_value
    else:
        raise CatalogIntegrityError(f"{context}: 'defaultToRoot' must be a boolean")

    return _TargetSelector(
        mode="filePattern",
        suffixes=suffixes,
        contains=contains,
        fallback_directory=fallback_directory,
        default_to_root=default_to_root,
    )


@dataclass(slots=True)
class _ProjectTargetPlan:
    """Configuration for deriving scanner targets."""

    settings: tuple[str, ...]
    include_discovery_roots: bool
    include_discovery_explicit: bool
    fallback_paths: tuple[str, ...]
    default_to_root: bool
    filter_excluded: bool
    prefix: str | None

    def resolve(self, ctx: ToolContext, *, excluded: set[Path], root: Path) -> list[str]:
        targets: set[Path] = set()
        for name in self.settings:
            for value in _settings_list(_setting(ctx.settings, name)):
                candidate = _resolve_path(root, value)
                if self.filter_excluded and _is_under_any(candidate, excluded):
                    continue
                targets.add(candidate)

        discovery = getattr(ctx.cfg, "file_discovery", None)
        if discovery is not None:
            if self.include_discovery_roots:
                for directory in discovery.roots:
                    resolved = directory if directory.is_absolute() else root / directory
                    if resolved == root:
                        continue
                    if self.filter_excluded and _is_under_any(resolved, excluded):
                        continue
                    targets.add(resolved)
            if self.include_discovery_explicit:
                for file_path in discovery.explicit_files:
                    resolved_file = file_path if file_path.is_absolute() else root / file_path
                    parent = resolved_file.parent
                    if self.filter_excluded and _is_under_any(parent, excluded):
                        continue
                    targets.add(parent)

        if not targets:
            for fallback in self.fallback_paths:
                candidate = _resolve_path(root, fallback)
                if fallback != "." and not candidate.exists():
                    continue
                if self.filter_excluded and _is_under_any(candidate, excluded):
                    continue
                targets.add(candidate)
                break

        if not targets and self.default_to_root:
            if not self.filter_excluded or not _is_under_any(root, excluded):
                targets.add(root)

        return sorted({str(path) for path in targets})


@dataclass(slots=True)
class _ProjectScannerStrategy(CommandBuilder):
    """Command builder orchestrating project-aware scanners."""

    base: tuple[str, ...]
    options: tuple[_CommandOption, ...]
    exclude_settings: tuple[str, ...]
    include_discovery_excludes: bool
    exclude_flag: str | None
    exclude_separator: str
    target_plan: _ProjectTargetPlan | None

    def build(self, ctx: ToolContext) -> Sequence[str]:
        root = ctx.root
        command = list(self.base)

        excluded_paths: set[Path] = set()
        for name in self.exclude_settings:
            for value in _settings_list(_setting(ctx.settings, name)):
                excluded_paths.add(_resolve_path(root, value))

        if self.include_discovery_excludes:
            discovery = getattr(ctx.cfg, "file_discovery", None)
            if discovery is not None:
                for path in discovery.excludes:
                    resolved = path if path.is_absolute() else root / path
                    excluded_paths.add(resolved)

        if self.exclude_flag and excluded_paths:
            exclude_args = _compile_exclude_arguments(excluded_paths, root)
            if exclude_args:
                command.extend([self.exclude_flag, self.exclude_separator.join(sorted(exclude_args))])

        for option in self.options:
            option.apply(ctx=ctx, command=command)

        if self.target_plan is not None:
            targets = self.target_plan.resolve(ctx, excluded=excluded_paths, root=root)
            if targets:
                if self.target_plan.prefix:
                    command.append(self.target_plan.prefix)
                command.extend(targets)

        return tuple(command)


def command_project_scanner(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a project-aware scanner command builder driven by catalog data."""

    plain_config = _as_plain_json(config)
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("command_project_scanner: configuration must be an object")

    base_config = plain_config.get("base")
    if not isinstance(base_config, Sequence) or isinstance(base_config, (str, bytes, bytearray)):
        raise CatalogIntegrityError("command_project_scanner: 'base' must be an array of arguments")
    base_args = tuple(str(part) for part in base_config)
    if not base_args:
        raise CatalogIntegrityError("command_project_scanner: 'base' must contain at least one argument")

    options_config = plain_config.get("options")
    option_specs: list[_CommandOption] = []
    if options_config is not None:
        if not isinstance(options_config, Sequence) or isinstance(options_config, (str, bytes, bytearray)):
            raise CatalogIntegrityError("command_project_scanner: 'options' must be an array of objects")
        for index, entry in enumerate(options_config):
            option_specs.append(_parse_command_option(entry, index=index))

    exclude_config = plain_config.get("exclude", {})
    if not isinstance(exclude_config, Mapping):
        raise CatalogIntegrityError("command_project_scanner: 'exclude' must be an object when provided")
    exclude_settings_value = exclude_config.get("settings", ())
    if isinstance(exclude_settings_value, str):
        exclude_settings = (exclude_settings_value,)
    elif isinstance(exclude_settings_value, Sequence) and not isinstance(
        exclude_settings_value, (str, bytes, bytearray)
    ):
        exclude_settings = tuple(str(item) for item in exclude_settings_value if item is not None)
    else:
        raise CatalogIntegrityError("command_project_scanner: exclude.settings must be string or array of strings")

    include_discovery_excludes = bool(exclude_config.get("includeDiscovery", False))
    exclude_flag_value = exclude_config.get("flag")
    if exclude_flag_value is None:
        exclude_flag = None
    elif isinstance(exclude_flag_value, str):
        exclude_flag = exclude_flag_value
    else:
        raise CatalogIntegrityError("command_project_scanner: exclude.flag must be a string when provided")

    separator_value = exclude_config.get("separator", ",")
    if not isinstance(separator_value, str) or not separator_value:
        raise CatalogIntegrityError("command_project_scanner: exclude.separator must be a non-empty string")

    targets_config = plain_config.get("targets")
    target_plan = None
    if targets_config is not None:
        target_plan = _parse_project_target_plan(targets_config)

    return _ProjectScannerStrategy(
        base=base_args,
        options=tuple(option_specs),
        exclude_settings=exclude_settings,
        include_discovery_excludes=include_discovery_excludes,
        exclude_flag=exclude_flag,
        exclude_separator=separator_value,
        target_plan=target_plan,
    )


def _parse_project_target_plan(entry: Any) -> _ProjectTargetPlan:
    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError("command_project_scanner.targets must be an object")

    settings_value = entry.get("settings", ())
    if isinstance(settings_value, str):
        settings = (settings_value,)
    elif isinstance(settings_value, Sequence) and not isinstance(settings_value, (str, bytes, bytearray)):
        settings = tuple(str(item) for item in settings_value if item is not None)
    else:
        raise CatalogIntegrityError("command_project_scanner.targets.settings must be string or array of strings")

    include_roots = bool(entry.get("includeDiscoveryRoots", False))
    include_explicit = bool(entry.get("includeDiscoveryExplicit", False))

    fallback_value = entry.get("fallback", ())
    if isinstance(fallback_value, str):
        fallback_paths = (fallback_value,)
    elif isinstance(fallback_value, Sequence) and not isinstance(fallback_value, (str, bytes, bytearray)):
        fallback_paths = tuple(str(item) for item in fallback_value if item is not None)
    else:
        raise CatalogIntegrityError("command_project_scanner.targets.fallback must be string or array of strings")

    default_to_root = bool(entry.get("defaultToRoot", False))
    filter_excluded = bool(entry.get("filterExcluded", True))

    prefix_value = entry.get("prefix")
    if prefix_value is None:
        prefix = None
    elif isinstance(prefix_value, str):
        prefix = prefix_value
    else:
        raise CatalogIntegrityError("command_project_scanner.targets.prefix must be a string when provided")

    return _ProjectTargetPlan(
        settings=settings,
        include_discovery_roots=include_roots,
        include_discovery_explicit=include_explicit,
        fallback_paths=fallback_paths,
        default_to_root=default_to_root,
        filter_excluded=filter_excluded,
        prefix=prefix,
    )


def _normalize_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_normalize_value(item) for item in value)
    if value in (None,):
        return ()
    raise CatalogIntegrityError("strategy configuration: 'args' must be a sequence")


def _normalize_mapping(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError("strategy configuration: 'kwargs' must be a mapping")
    return {str(key): _normalize_value(item) for key, item in value.items()}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_normalize_value(item) for item in value)
    return value


def _download_artifact_for_tool(
    download_config: Mapping[str, Any],
    *,
    version: str | None,
    cache_root: Path,
    context: str,
) -> Path:
    plain_config = _as_plain_json(download_config)
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError(f"{context}: download configuration must be a mapping")
    return download_tool_artifact(plain_config, version=version, cache_root=cache_root, context=context)


def _as_plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _as_plain_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_as_plain_json(item) for item in value]
    return value


def _compile_exclude_arguments(excluded_paths: set[Path], root: Path) -> set[str]:
    arguments: set[str] = set()
    for path in excluded_paths:
        resolved = path.resolve()
        arguments.add(str(resolved))
        try:
            relative = resolved.relative_to(root.resolve())
            arguments.add(str(relative))
        except ValueError:
            continue
    return arguments


def _is_under_any(candidate: Path, bases: set[Path]) -> bool:
    for base in bases:
        try:
            candidate.resolve().relative_to(base.resolve())
            return True
        except ValueError:
            continue
    return False
