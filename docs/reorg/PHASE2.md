# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

# Phase 2 – Config, Cache, and Discovery Progress Log

## Completed

* Split legacy configuration helpers into the new `pyqa.config` package:
  * Section mergers now live under `pyqa.config.sections`, re-exported via
    `pyqa.config.sections.__all__`.
  * Shared helper functions were migrated to `pyqa.config.utils`, replacing the
    old `config_utils.py` module and updating all call sites.
  * The configuration package exposes models via `pyqa.config.models` and
    loader utilities via `pyqa.config.loaders`.
* Moved cache management code out of `pyqa.execution`:
  * `pyqa.cache.result_store` replaces `execution/cache.py`.
  * `pyqa.cache.context` replaces `execution/cache_context.py` and now depends on
    the relocated `pyqa.cache.tool_versions` module.
  * `pyqa.cache.__init__` re-exports cache primitives (containers, contexts,
    TTL decorators) for callers.
  * All orchestrator, executor, and test imports now point at the new cache
    modules.
* Relocated the project scanner logic to `pyqa.discovery.planners` and updated
  tooling strategies/tests to use the new path.
* Updated wrapper tests to reflect the current CLI launcher messages.

## Validation

* `uv run pyright src/pyqa`
* `pytest`
* `./lint -n`

## Next Steps

* Continue Phase 2 by migrating any residual configuration helpers (e.g.
  defaults, section docs) as follow-up improvements if needed.
* Begin preparing Phase 3 (catalog extraction) once cache/discovery changes have
  settled.
