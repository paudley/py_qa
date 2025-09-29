"""Shared helper utilities for strategy implementations."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

from ..loader import CatalogIntegrityError
from ..catalog.types import JSONValue
from ..tools.base import ToolContext
from ..tools.builtin_helpers import download_tool_artifact


def install_download_artifact(config: Mapping[str, JSONValue]) -> Callable[[ToolContext], None]:
    """Return a catalog-driven installer for download artifacts.

    Args:
        config: Catalog configuration describing the download specification.

    Returns:
        Callable[[ToolContext], None]: Installer that ensures the artifact is
        materialised prior to tool execution.

    Raises:
        CatalogIntegrityError: If the configuration is malformed.
    """

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
    try:
        module_path, _, attribute = path.rpartition(".")
        if not module_path:
            raise CatalogIntegrityError(f"{context}: '{path}' is not a valid import path")
        module = importlib.import_module(module_path)
        return getattr(module, attribute)
    except (ImportError, AttributeError) as exc:
        raise CatalogIntegrityError(f"{context}: unable to import '{path}'") from exc


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


def _normalize_sequence(value: JSONValue) -> tuple[JSONValue, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_normalize_value(item) for item in value)
    if value in (None,):
        return ()
    raise CatalogIntegrityError("strategy configuration: 'args' must be a sequence")


def _normalize_mapping(value: JSONValue) -> dict[str, JSONValue]:
    if not value:
        return {}
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError("strategy configuration: 'kwargs' must be a mapping")
    return {str(key): _normalize_value(item) for key, item in value.items()}


def _normalize_value(value: JSONValue) -> JSONValue:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_normalize_value(item) for item in value)
    return value


def _download_artifact_for_tool(
    download_config: Mapping[str, JSONValue],
    *,
    version: str | None,
    cache_root: Path,
    context: str,
) -> Path:
    plain_config = cast(JSONValue, _as_plain_json(download_config))
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError(f"{context}: download configuration must be a mapping")
    return download_tool_artifact(plain_config, version=version, cache_root=cache_root, context=context)


def _as_plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _as_plain_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_as_plain_json(item) for item in value]
    return value


__all__ = [
    "install_download_artifact",
    "_as_plain_json",
    "_download_artifact_for_tool",
    "_load_attribute",
    "_normalize_mapping",
    "_normalize_sequence",
    "_normalize_value",
    "_require_str",
    "_require_string_sequence",
]
