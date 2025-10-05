<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Phase 1 – Interfaces & Core Runtime Progress Log

## Completed

* Introduced the `pyqa.interfaces` package with domain-specific protocol files
  (`analysis`, `catalog`, `cli`, `config`, `core`, `discovery`, `environment`,
  `orchestration`, `reporting`, `compliance`).
* Added `pyqa.core.runtime.di.ServiceContainer` plus default service
  registrations and tests, enabling DI-driven wiring for future phases.
* Re-exported shared logging helpers from `pyqa.core.logging` to prepare for
  CLI/orchestrator integration.
* Added `pyqa.cache.in_memory.ttl_cache` decorator and regression tests so code
  can migrate away from ad-hoc `functools.cache` usage.
* Converted `pyqa.config` into a package (`config/models.py`,
  `config/loaders/sources.py`) laying the groundwork for Phase 2 config/cache
  decomposition.
* Registered plugin loaders with the DI container and added protocol contract
  tests (`tests/interfaces/test_protocols.py`) to ensure runtime compliance.

## In Flight

* Update call sites to adopt the new cache helpers and the DI container as
  packages migrate.
* Flesh out logging adapters once CLI/orchestrator refactors land (Phase 4).
* Adopt interfaces in existing modules to reduce direct cross-package imports.
* Decompose remaining configuration helpers (section mergers, resolver) into
  the new `config/` subpackages during Phase 2.

## Next Steps

1. Begin migrating real components (config/cache/discovery) to depend on the
   new interfaces in Phase 2.
2. Decide on default service keys consumers should use (document in developer
   guides).
3. Consider exposing optional service hooks via entry points once catalog/CLI
   integration is underway.
