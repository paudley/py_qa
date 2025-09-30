# SPDX-License-Identifier: MIT
"""Helpers for catalog-configured JSON diagnostic extraction."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from ..models import RawDiagnostic
from ..tools.base import ToolContext
from .loader import CatalogIntegrityError

__all__ = ["JsonDiagnosticExtractor"]


@dataclass(frozen=True)
class PathComponent:
    """Single navigation step within a dotted/array JSON path."""

    kind: Literal["key", "index", "wildcard"]
    value: str | int | None


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

        path_value = raw_spec.get("path")
        if path_value is None:
            path_tokens: tuple[PathComponent, ...] | None = None
        elif isinstance(path_value, str):
            path_tokens = _tokenize_path(path_value, allow_wildcards=False)
        else:
            raise CatalogIntegrityError(
                f"parser_json_diagnostics: field '{name}' has non-string 'path' configuration",
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


def _extract_path(entry: Mapping[str, Any], path: tuple[PathComponent, ...] | None) -> Any | None:
    """Resolve *path* against *entry* returning the final value."""

    if not path:
        return entry

    current: Any = entry
    for token in path:
        if token.kind == "key":
            if not isinstance(current, Mapping):
                break
            key = token.value
            if not isinstance(key, str) or key not in current:
                break
            current = current[key]
            continue
        if token.kind == "index":
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes, bytearray)):
                break
            index = int(token.value) if token.value is not None else 0
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
                raise CatalogIntegrityError(
                    f"parser_json_diagnostics: unmatched '[' in path '{path}'",
                )
            segment = trimmed[index + 1 : closing].strip()
            _append_bracket_segment(tokens, segment, allow_wildcards, path)
            index = closing + 1
            continue
        buffer.append(char)
        index += 1

    _flush_buffer_as_key(buffer, tokens)

    filtered: list[PathComponent] = []
    for token in tokens:
        if token.kind == "key" and isinstance(token.value, str) and token.value in {"", "$"}:
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
        tokens.append(PathComponent("key", key))


def _append_bracket_segment(
    tokens: list[PathComponent],
    segment: str,
    allow_wildcards: bool,
    path: str,
) -> None:
    """Append bracket segment tokens, enforcing wildcard policy."""

    if segment in {"", "*"}:
        if not allow_wildcards:
            raise CatalogIntegrityError(
                "parser_json_diagnostics: wildcards are not permitted " f"in field paths ('{path}')",
            )
        tokens.append(PathComponent("wildcard", None))
        return

    cleaned = segment
    if segment.startswith('"') and segment.endswith('"') and len(segment) >= 2:
        cleaned = segment[1:-1]
    if cleaned.lstrip("-").isdigit():
        tokens.append(PathComponent("index", int(cleaned)))
        return
    tokens.append(PathComponent("key", cleaned))


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
