# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Provide cache utilities and provider factories for pyqa."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from ..interfaces.cache import CacheProvider
from ..protocols.serialization import SerializableValue
from .in_memory import ttl_cache
from .providers import DirectoryCacheProvider, InMemoryCacheProvider

ProviderKind = Literal["memory", "directory"]
_PROVIDER_ENV_VAR: Final[str] = "PYQA_CACHE_PROVIDER"
_MEMORY_KIND: Final[ProviderKind] = "memory"
_DIRECTORY_KIND: Final[ProviderKind] = "directory"


@dataclass(frozen=True, slots=True)
class CacheProviderSettings:
    """Define cache provider selection parameters.

    Attributes:
        kind: Backend identifier. ``"memory"`` yields an in-process cache, while
            ``"directory"`` persists JSON-serialisable values on disk.
        directory: Filesystem directory used when ``kind`` is ``"directory"``.
            This field is ignored for in-memory caches.
    """

    kind: ProviderKind = _MEMORY_KIND
    directory: Path | None = None


def _settings_from_environment(env: Mapping[str, str]) -> CacheProviderSettings | None:
    """Parse cache provider settings from ``env`` when overrides are configured.

    Args:
        env: Environment mapping consulted for cache provider overrides.

    Returns:
        CacheProviderSettings | None: Settings parsed from the environment when
        present; otherwise ``None`` to indicate defaults should apply.

    Raises:
        ValueError: If an unsupported provider kind is requested or a
        directory-backed provider omits the directory path.
    """

    specification = env.get(_PROVIDER_ENV_VAR)
    if not specification:
        return None

    token, _, remainder = specification.partition(":")
    kind = token.strip().lower()
    if kind == _MEMORY_KIND:
        return CacheProviderSettings(kind=_MEMORY_KIND)

    if kind == _DIRECTORY_KIND:
        path_token = remainder.strip()
        if not path_token:
            raise ValueError("PYQA_CACHE_PROVIDER=directory requires a directory path")
        return CacheProviderSettings(kind=_DIRECTORY_KIND, directory=Path(path_token).expanduser())

    raise ValueError(f"Unsupported cache provider specified via {_PROVIDER_ENV_VAR}: {specification!r}")


def resolve_cache_provider_settings(
    settings: CacheProviderSettings | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> CacheProviderSettings:
    """Return cache provider settings honouring overrides and defaults.

    Args:
        settings: Explicit settings that should take precedence over derived
            configuration when provided.
        env: Optional environment mapping used instead of :mod:`os.environ`.

    Returns:
        CacheProviderSettings: Effective settings after applying overrides or
        falling back to memory-backed defaults.
    """

    if settings is not None:
        return settings

    environment = env or os.environ
    env_settings = _settings_from_environment(environment)
    if env_settings is not None:
        return env_settings

    return CacheProviderSettings()


def create_cache_provider(settings: CacheProviderSettings | None = None) -> CacheProvider[SerializableValue]:
    """Build a cache provider configured according to ``settings``.

    Args:
        settings: Provider settings describing the desired backend.

    Returns:
        CacheProvider[SerializableValue]: Cache provider matching the requested
        backend configuration.

    Raises:
        ValueError: If directory-backed caching is requested without providing
        a directory path.
    """

    resolved = resolve_cache_provider_settings(settings)
    if resolved.kind == _MEMORY_KIND:
        return InMemoryCacheProvider()

    if resolved.directory is None:
        raise ValueError("CacheProviderSettings.directory must be set for directory-backed providers")
    provider = DirectoryCacheProvider(resolved.directory)
    return provider


# suppression_valid: lint=internal-cache reason=Reuse functools.lru_cache to preserve the default provider singleton.
@lru_cache(maxsize=1)
def _default_cache_provider_singleton() -> CacheProvider[SerializableValue]:
    """Return a module-wide default cache provider singleton.

    Returns:
        CacheProvider[SerializableValue]: Shared cache provider instance.
    """

    return create_cache_provider()


def default_cache_provider() -> CacheProvider[SerializableValue]:
    """Return the default cache provider honouring environment overrides.

    Returns:
        CacheProvider[SerializableValue]: Shared cache provider instance.
    """

    return _default_cache_provider_singleton()


__all__ = [
    "CacheProviderSettings",
    "create_cache_provider",
    "default_cache_provider",
    "resolve_cache_provider_settings",
    "ttl_cache",
]
