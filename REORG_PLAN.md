<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# pyqa Module Reorg Implementation Plan

This implementation roadmap breaks the high-level goals from `REORG_MODULES.md`
into executable phases. It assumes no backwards-compatibility shims, immediate
adoption of entry-point plugins, and the eventual publication of the tooling
specification as a standalone project.

## Guiding Constraints

* Changes land incrementally behind short-lived feature branches; main stays
  releasable at all times.
* No legacy import aliases—call sites must migrate in the same change that
  moves code.
* Strict typing and SOLID guardrails from `REORG_MODULES.md` apply to every new
  module: clear inputs/outputs, interface-first wiring, contract tests.
* Tooling catalog code must remain pyqa-agnostic so it can ship independently.
* Runtime implementations live under `src/pyqa`, while the shared specification is
  published from the sibling `src/tooling_spec` module to keep code and spec
  assets side-by-side inside this repository.
* All third-party dependencies (e.g., spaCy, tree-sitter) are mandatory; missing modules must raise fatal errors rather than degrade gracefully.

## Coding RULES

* When editing files, make sure that all functions have valid and comprehensive google-style comments and that we are using SOLID principles where possible.
* Keep an eye out for overly complex functions that could benefit from being broken up into smaller, focussed and robust helpers (or where you can use existing helpers).
* Try to use the strictest types possible and avoid Any, object and optional None if possible.
* For functions that have more than 5 args or use kwargs, prefer using a paramater dataclass instead.
* Use typing.Literal, typing.Final, abc.\* and enum where possible to improve code.
* Consider adding dunder methods to classes where it makes them more useful to callers.i
* The use of lint warning suppression commments is FORBIDDEN, please remove them when found unless they are acompantied with a robust explanation - you MUST fix lint warnings by fixing code.
* Apply functools where profitable.

## Phase 0 – Readiness & Tooling (1 sprint)

1. **Inventory & ownership**
   * \[x] Generate a dependency graph (custom script) to confirm existing module
     coupling (`reorg/scripts/generate_dependency_graph.py`).
   * \[x] Mark files that will move to the new packages (`reorg/artifacts/phase0/module_move_candidates.json`).
2. **Automation scaffolding**
   * \[x] Add architectural tests (import lints) to enforce the new package
     boundaries as they are created (`tests/architecture/test_dependency_graph.py`).
   * \[ ] Extend CI to run contract suites (type checking, pytest selection)
     against both current and in-progress layouts (blocked by existing pyright failures; see `docs/reorg/PHASE0.md`).
3. **Entry-point skeletons**
   * \[x] Define plugin group names in `pyproject.toml`
     (`pyqa.catalog.plugins`, `pyqa.cli.plugins`, `pyqa.diagnostics.plugins`).
   * \[x] Create placeholder registries (currently under `pyqa.plugins`) that can
     hydrate entry points once the new interface layer exists.

## Phase 1 – Interfaces & Core Runtime (2 sprints)

1. **Introduce `interfaces/` package**
   * \[x] Create domain files (`analysis.py`, `catalog.py`, `cli.py`, `config.py`,
     `core.py`, `discovery.py`, `environment.py`, `orchestration.py`,
     `reporting.py`, `compliance.py`).
   * \[x] Lift existing `Protocol` definitions into the package, adding invariants
     and docstrings.
2. **Core runtime refresh**
   * \[x] Stand up `core/runtime/di.py` with a lightweight service container,
     default factories (console/logger/cache), and tests using stub bindings.
   * \[x] Move logging helpers into `core/logging/` with shared formatters and Rich
     adapters wrapped behind interfaces (currently re-exporting existing helpers).
   * \[x] Add `cache/in_memory.py` with TTL cache primitives; update call sites in
     modules that currently rely on `functools.cache` (available for adoption in
     subsequent phases).
3. **Gateway tests**
   * \[x] Provide contract fixtures ensuring components accept injected interfaces.
   * \[x] Wire entry-point registries to the DI container (even if no external
     plugins exist yet) so the seams are proven.

## Phase 2 – Config, Cache, and Discovery (2 sprints)

1. **Config decomposition**
   * Split `config.py`, `config_loader.py`, `config_loader_sections.py`, and
     `config_utils.py` into `config/models.py`, `config/loaders/`,
     `config/sections/`, `config/defaults/`.
   * Update CLI/config builders to consume the new modules exclusively via
     interfaces.
   * Add contract tests for `ConfigSource`/`ConfigResolver` mocks.
2. **Cache package**
   * Move `execution/cache.py` and `execution/cache_context.py` into
     `cache/result_store.py` and `cache/context.py`.
   * Integrate the new in-memory utilities and ensure disk vs memory
     implementations share the same interface.
3. **Discovery refactor**
   * Relocate `tooling/project_scanner.py` and supporting helpers into
     `discovery/planners.py` and `discovery/rules.py`.
   * Ensure catalog strategies consume discovery planners through interfaces.
4. **Testing**
   * Run targeted integration tests (`pytest tests/test_tooling_loader.py`,
     discovery suites) with the new module layout.

## Phase 3 – Catalog & Tooling Spec Extraction (3 sprints)

1. **Catalog package move**
   * Relocate `tooling/loader.py`, `tooling/catalog/*`, `tooling/schema/*`, and
     `tools/catalog_metadata.py` into the new `catalog/` package.
   * Remove pyqa-specific imports; rely on `interfaces/catalog.py` exclusively.
2. **Public API polish**
   * Convert catalog models to dataclasses/pydantic models with rich dunders
     (`__repr__`, `__eq__`, optional `__hash__`) and `to_dict`/`from_dict`
     helpers.
   * Document each public class and function with Google-style docstrings.
3. **Standalone `tooling_spec` package**
   * Create `tooling_spec/` (or `tooling_spec/`) exposing schemas,
     metadata models, loader APIs, and examples.
   * Set up packaging metadata, versioning strategy (SemVer + schema version),
     changelog automation, and release scripts.
   * Write migration and integration guides for external consumers.
4. **Plugin hooks**
   * Implement entry-point loading for catalog extensions (tool packs,
     strategy packs) and cover with tests using stub distributions.
5. **Deliverables**
   * Ship initial pre-release of the tooling spec to PyPI/GitHub Packages.
   * Announce availability and document contribution guidelines.

## Phase 4 – CLI & Orchestration Realignment (2 sprints)

1. **CLI command packages**
   * Restructure `src/pyqa/cli` into `cli/commands/*`, `cli/core/`,
     `cli/launcher/`, updating Typer registration.
   * Inject services via constructors/factories to satisfy interface contracts.
   * Add entry-point support for third-party CLI commands.
2. **Orchestration package**
   * Move `execution/orchestrator.py`, `execution/action_executor.py`,
     `execution/tool_selection.py`, `execution/runtime.py`, and `execution/worker.py`
     into `orchestration/` submodules.
   * Establish lifecycle hooks and ensure CLI/quality commands depend only on
     `interfaces/orchestration.py`.
3. **Progress and diagnostics integration**
   * Verify new dependency graph maintains SOLID guardrails (no CLI → cache
     imports, etc.).

## Phase 5 – Diagnostics, Reporting, Compliance (2 sprints)

1. **Diagnostics pipeline**
   * Create `diagnostics/core.py`, `diagnostics/filtering.py`,
     `diagnostics/json_import.py`, and register stages via interface-driven
     pipelines.
2. **Reporting realignment**
   * Break reporting into `reporting/advice/`, `reporting/output/`, and
     `reporting/presenters/`; migrate to diagnostics interfaces.
3. **Compliance package**
   * Move policy code (`quality`, `banned`, `checks/`, `security`) into the new
     `compliance/` package with service-oriented APIs.
4. **Testing**
   * Extend snapshot and contract tests to validate alternative presenters,
     advice providers, and compliance policies via interface injection.

## Phase 6 – Hardening & Release (1–2 sprints)

1. **Docs & communication**
   * Update README, CLI guides, tooling docs, and release notes to reference the
     new package layout and standalone tooling spec.
2. **Architecture verification**
   * Run final dependency analysis ensuring layering rules hold (core →
     interfaces only, etc.).
3. **Release sequencing**
   * Publish the tooling spec final release.
   * Tag pyqa releases containing the reorganized modules, highlighting breaking
     changes and upgrade instructions.
4. **Post-release monitoring**
   * Track plugin adoption, gather feedback, and schedule follow-up work for
     additional tooling spec features.

## Risk Mitigation & QA

* **CI gating:** Block merges unless type checks, unit tests, and architectural
  lints pass for both pyqa and the tooling spec package.
* **Integration tests:** Maintain smoke suites that run the orchestrator end to
  end after each phase to catch regressions early.
* **Documentation debt:** Treat docs/testing tasks as required deliverables for
  each phase—not optional—to keep the spec consumable by third parties.

## Timeline Snapshot (approximate)

| Phase | Sprints | Key Deliverable                                                  |
| ----- | ------- | ---------------------------------------------------------------- |
| 0     | 1       | Architectural guardrails & entry-point scaffolding               |
| 1     | 2       | Interfaces package, DI container, shared logging/cache utilities |
| 2     | 2       | Config/cache/discovery refactor                                  |
| 3     | 3       | Catalog extraction + tooling spec pre-release                    |
| 4     | 2       | CLI/orchestration realignment                                    |
| 5     | 2       | Diagnostics/reporting/compliance packages                        |
| 6     | 1–2     | Final docs, releases, monitoring                                 |

Total: roughly 13–14 sprints (~6 months) assuming two-week iterations and
parallel work streams where feasible.
