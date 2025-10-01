# SPDX-License-Identifier: MIT
"""Helpers for catalog-configured JSON diagnostic extraction."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from ..models import RawDiagnostic
from ..tools.base import ToolContext
from .loader import CatalogIntegrityError

__all__ = ["JsonDiagnosticExtractor"]


_PATH_SEPARATOR: Final[str] = "."
_BRACKET_OPEN: Final[str] = "["
_BRACKET_CLOSE: Final[str] = "]"
_WILDCARD_SYMBOL: Final[str] = "*"
_ROOT_TOKENS: Final[tuple[str, ...]] = ("", "$")
_QUOTE_CHAR: Final[str] = '"'
_MIN_QUOTED_LENGTH: Final[int] = 2
_DEFAULT_INDEX: Final[int] = 0


class PathTokenKind(StrEnum):
    """Enumerate path component flavours allowed in mappings."""

    KEY = "key"
    INDEX = "index"
    WILDCARD = "wildcard"


@dataclass(frozen=True)
class PathComponent:
    """Single navigation step within a dotted/array JSON path."""

    kind: PathTokenKind
    value: str | int | None


class FieldConfigKey(StrEnum):
    """Supported keys when defining diagnostic field mappings."""

    PATH = "path"
    VALUE = "value"
    DEFAULT = "default"
    MAP = "map"


@dataclass(slots=True)
class FieldSpec:
    """Descriptor instructing how to resolve a diagnostic field from JSON."""

    name: str
    path: tuple[PathComponent, ...] | None
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
        if value is None:
            return self.default if self.has_default else None
        if not self.remap:
            return value
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
class JsonDiagnosticExtractor:
    """Transform JSON payloads into ``RawDiagnostic`` sequences."""

    item_path: str | None
    mapping_config: Mapping[str, Any]
    input_format: str
    _field_specs: Mapping[str, FieldSpec] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Normalise configuration into efficient lookup structures."""

        self._field_specs = self._build_field_specs(self.mapping_config)
        mandatory_fields = {"message"}
        missing = mandatory_fields - self._field_specs.keys()
        if missing:
            names = ", ".join(sorted(missing))
            raise CatalogIntegrityError(
                f"parser_json_diagnostics: missing required field mapping(s): {names}",
            )

    def transform(self, payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
        """Convert JSON payload into ``RawDiagnostic`` entries."""

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

    def _build_field_specs(self, config: Mapping[str, Any]) -> Mapping[str, FieldSpec]:
        """Normalize mapping configuration into ``FieldSpec`` instances."""

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
        specs: dict[str, FieldSpec] = {}
        for field_name, raw_spec in config.items():
            if field_name not in allowed_fields:
                raise CatalogIntegrityError(
                    f"parser_json_diagnostics: unsupported field '{field_name}' in mappings",
                )
            specs[field_name] = self._build_field_spec(field_name, raw_spec)
        return specs

    def _build_field_spec(self, name: str, raw_spec: Any) -> FieldSpec:
        """Create a field specification for a single diagnostic attribute."""

        if isinstance(raw_spec, str):
            path_tokens = _tokenize_path(raw_spec, allow_wildcards=False)
            return FieldSpec(
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
                f"parser_json_diagnostics: mapping for field '{name}' must be a string or object",
            )

        path_value = raw_spec.get(FieldConfigKey.PATH)
        if path_value is None:
            path_tokens: tuple[PathComponent, ...] | None = None
        elif isinstance(path_value, str):
            path_tokens = _tokenize_path(path_value, allow_wildcards=False)
        else:
            raise CatalogIntegrityError(
                f"parser_json_diagnostics: field '{name}' has non-string 'path' configuration",
            )

        const_value = raw_spec.get(FieldConfigKey.VALUE)
        has_const = FieldConfigKey.VALUE in raw_spec

        default_value = raw_spec.get(FieldConfigKey.DEFAULT)
        has_default = FieldConfigKey.DEFAULT in raw_spec

        map_value = raw_spec.get(FieldConfigKey.MAP)
        remap: dict[str, Any] = {}
        if map_value is not None:
            if not isinstance(map_value, Mapping):
                raise CatalogIntegrityError(
                    f"parser_json_diagnostics: field '{name}' has non-object 'map' configuration",
                )
            for key, mapped_value in map_value.items():
                if not isinstance(key, str):
                    raise CatalogIntegrityError(
                        f"parser_json_diagnostics: field '{name}' mapping keys must be strings",
                    )
                remap[key.casefold()] = mapped_value
                remap[key] = mapped_value

        return FieldSpec(
            name=name,
            path=path_tokens,
            value=const_value,
            has_value=has_const,
            default=default_value,
            has_default=has_default,
            remap=remap,
        )


def _descend(nodes: Iterable[Any], token: PathComponent) -> Iterator[Any]:
    """Yield nodes after applying a path ``token`` to *nodes*."""

    if token.kind is PathTokenKind.KEY:
        yield from _descend_by_key(nodes, token)
        return
    if token.kind is PathTokenKind.INDEX:
        yield from _descend_by_index(nodes, token)
        return
    if token.kind is PathTokenKind.WILDCARD:
        yield from _descend_by_wildcard(nodes)


def _descend_by_key(nodes: Iterable[Any], token: PathComponent) -> Iterator[Any]:
    """Yield values by resolving *token* as a dictionary key."""

    key = token.value
    if not isinstance(key, str):
        return
    for node in nodes:
        if isinstance(node, Mapping) and key in node:
            yield node[key]


def _descend_by_index(nodes: Iterable[Any], token: PathComponent) -> Iterator[Any]:
    """Yield values by resolving *token* as a positional index."""

    index = int(token.value) if token.value is not None else _DEFAULT_INDEX
    for node in nodes:
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            if -len(node) <= index < len(node):
                yield node[index]


def _descend_by_wildcard(nodes: Iterable[Any]) -> Iterator[Any]:
    """Yield flattened sequence members for wildcard traversal."""

    for node in nodes:
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            yield from node


def _extract_path(entry: Mapping[str, Any], path: tuple[PathComponent, ...] | None) -> Any | None:
    """Resolve *path* against *entry* returning the final value."""

    if not path:
        return entry

    current: Any = entry
    for token in path:
        if token.kind is PathTokenKind.KEY:
            if not isinstance(current, Mapping):
                break
            key = token.value
            if not isinstance(key, str) or key not in current:
                break
            current = current[key]
            continue
        if token.kind is PathTokenKind.INDEX:
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes, bytearray)):
                break
            index = int(token.value) if token.value is not None else _DEFAULT_INDEX
            if index >= len(current) or index < -len(current):
                break
            current = current[index]
            continue
        break
    else:
        return current
    return None


def _tokenize_path(path: str, *, allow_wildcards: bool) -> tuple[PathComponent, ...]:
    """Tokenise dotted/array path expressions into components."""

    trimmed = path.strip()
    if not trimmed:
        return ()

    tokens: list[PathComponent] = []
    buffer: list[str] = []
    skip_until = -1
    for index, char in enumerate(trimmed):
        if index <= skip_until:
            continue
        if char == _PATH_SEPARATOR:
            _flush_buffer_as_key(buffer, tokens)
            continue
        if char == _BRACKET_OPEN:
            _flush_buffer_as_key(buffer, tokens)
            closing = trimmed.find(_BRACKET_CLOSE, index)
            if closing == -1:
                raise CatalogIntegrityError(
                    f"parser_json_diagnostics: unmatched '[' in path '{path}'",
                )
            segment = trimmed[index + 1 : closing].strip()
            _append_bracket_segment(tokens, segment, allow_wildcards, path)
            skip_until = closing
            continue
        buffer.append(char)

    _flush_buffer_as_key(buffer, tokens)

    filtered: list[PathComponent] = []
    for token in tokens:
        if token.kind is PathTokenKind.KEY and isinstance(token.value, str) and token.value in _ROOT_TOKENS:
            continue
        filtered.append(token)
    return tuple(filtered)


def _flush_buffer_as_key(buffer: list[str], tokens: list[PathComponent]) -> None:
    """Append buffered characters as a key token when non-empty."""

    if not buffer:
        return
    key = "".join(buffer).strip()
    buffer.clear()
    if key:
        tokens.append(PathComponent(PathTokenKind.KEY, key))


def _append_bracket_segment(
    tokens: list[PathComponent],
    segment: str,
    allow_wildcards: bool,
    path: str,
) -> None:
    """Append bracket segment tokens, enforcing wildcard policy."""

    if segment in {"", _WILDCARD_SYMBOL}:
        if not allow_wildcards:
            raise CatalogIntegrityError(
                "parser_json_diagnostics: wildcards are not permitted " f"in field paths ('{path}')",
            )
        tokens.append(PathComponent(PathTokenKind.WILDCARD, None))
        return

    cleaned = segment
    if segment.startswith(_QUOTE_CHAR) and segment.endswith(_QUOTE_CHAR) and len(segment) >= _MIN_QUOTED_LENGTH:
        cleaned = segment[1:-1]
    if cleaned.lstrip("-").isdigit():
        tokens.append(PathComponent(PathTokenKind.INDEX, int(cleaned)))
        return
    tokens.append(PathComponent(PathTokenKind.KEY, cleaned))


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
