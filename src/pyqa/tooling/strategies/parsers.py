"""Reusable parsers and diagnostic helpers for strategy definitions."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple

from ..loader import CatalogIntegrityError
from ..models import RawDiagnostic
from ..parsers.base import JsonParser, TextParser
from ..tools.base import ToolContext
from .common import _as_plain_json, _load_attribute, _require_str


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
            raise CatalogIntegrityError(f"parser_json_diagnostics: field '{name}' has non-string 'path' configuration")

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
                    raise CatalogIntegrityError(f"parser_json_diagnostics: field '{name}' mapping keys must be strings")
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


__all__ = ["json_parser", "text_parser", "parser_json_diagnostics"]
