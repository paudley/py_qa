<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Cache

## Overview

`pyqa.cache` provides the caching infrastructure used by the orchestrator and
higher-level services. The package is split into three primary concerns:

* **Provider selection (`__init__.py`)** – Parses `PYQA_CACHE_PROVIDER` or
  explicit settings to create either in-memory or directory-backed cache
  providers. These providers implement the `pyqa.interfaces.cache.CacheProvider`
  Protocol and store JSON-serialisable `SerializableValue` payloads.
* **Execution cache context (`context.py`)** – Builds per-run cache contexts that
  track cache tokens, version metadata, and persistence helpers. Orchestrator
  components consume `CacheContext` to load cached outcomes and persist tool
  version manifests.
* **Utility modules** – `result_store.py` defines the on-disk result cache
  format, `tool_versions.py` reads/writes version manifests, `providers.py`
  supplies provider implementations, and `in_memory.py` contains memoization
  decorators (`ttl_cache`) reused across packages.

All modules rely on the serialization interfaces and avoid importing CLI/runtime
code to maintain strict layering.

## Patterns

* **Factory wrappers** – `ResultCacheClassFactory`, `DefaultCacheContextFactory`,
  and provider helpers abstract object creation so callers depend on interfaces.
* **Token builders** – `DefaultCacheTokenBuilder` turns configuration state into
  cache tokens by hashing relevant knobs and tool settings, ensuring deterministic
  cache keys.
* **Version tracking** – `FileSystemCacheVersionStore` records tool versions next
  to cache data so future runs can invalidate stale entries when tooling is
  upgraded.
* **Memoization decorators** – `_MemoizedCallable` and `_TTLCacheCallable`
  implement lru/ttl behaviour without nested closures, keeping cache decorators
  SOLID-friendly and lint-compliant.

## DI Seams

* Inject `CacheProvider` implementations via `create_cache_provider` or the
  module-level `default_cache_provider`. Runtime code should accept the Protocol,
  not concrete providers.
* The orchestrator receives a `CacheContextFactory` (defaulting to
  `DefaultCacheContextFactory`) so tests can supply fake caches or token builders.
* Token builders and version stores are resolved through the interfaces package.
  Custom implementations should implement
  `pyqa.interfaces.cache.CacheTokenBuilder`/`CacheVersionStore` and be injected
  via the factory constructor.

## Extension Points

* **Custom providers** – Implement `CacheProvider` (e.g., Redis-backed) and call
  `create_cache_provider` with bespoke settings, or register new `ProviderKind`
  parsing logic if the environment variable needs to support additional kinds.
* **Alternate token builders** – Subclass `CacheTokenBuilderProtocol` when cache
  invalidation needs to consider different configuration knobs. Pass the builder
  into `DefaultCacheContextFactory`.
* **Additional memoization policies** – Reuse `ttl_cache` or extend
  `in_memory.py` with new decorators (e.g., size-based eviction) so modules avoid
  bespoke caching logic.
