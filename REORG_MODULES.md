<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# pyqa Module Reorganization Plan

## Objectives

* Structure packages around single responsibilities to reinforce SOLID boundaries.
* Isolate third-party integrations (spaCy, tree-sitter) so they can evolve independently.
* Consolidate caching and diagnostic flows to simplify import graphs and make dependencies explicit.
* Introduce a dedicated interfaces layer that defines stable protocols and abstractions consumed by higher-level modules.
* Embed SOLID acceptance criteria so each package advertises its seam (inputs/outputs, owning services, permitted dependencies) before code moves.
* Shape the tooling catalog as a self-contained specification that can be published independently for the wider lint tooling ecosystem.

## Proposed Package Layout

### cache/

* **Scope:** Result caching, cache token computation, persistence of tool metadata, helpers for cache-aware orchestration.
* **Candidate moves:**
  * `execution/cache.py` → `cache/result_store.py` (consider splitting Request models vs persistence helpers).
  * `execution/cache_context.py` → `cache/context.py` (wrap cache\_dir resolution + token building).
  * `tool_versions.py` → `cache/tool_versions.py` (used by execution cache context).
  * Cache-related helpers in `config_loader.py` / `config_loader_sections.py` (e.g., TOML cache) should be reviewed—either remain near config or migrate to `cache/config_sources.py` if shared.
  * Add `cache/in_memory.py` with shared decorators/TTL stores to replace ad-hoc `functools.cache` usage across modules.
  * `console.ConsoleManager` cache is orthogonal; recommend leaving under `console` unless we generalize small in-memory caches through the new in-memory helpers.
* **Interfaces:** expose narrow APIs (`CacheRepository`, `CacheTokenBuilder`) to decouple orchestrator from implementation details.
* **SOLID guardrails:** Document cache module inputs/outputs (e.g., `CacheRequest`, `CacheEntry` DTOs), require dedicated tests for in-memory vs disk implementations, and forbid CLI imports to keep responsibility limited to persistence.

### analysis/

* **Scope:** Code analysis utilities and integrations beyond core lint orchestration. Provide sub-packages to isolate external dependencies.
* **Restructure:**
  * `analysis/` remains top-level home for generic analysis helpers (`change_impact.py`, `navigator.py`, `suppression.py`).
  * Create `analysis/spacy/` for spaCy-specific NLP logic.
    * Move `annotations.py` (rename to `analysis/spacy/annotations.py`) and align exports via `analysis/spacy/__init__.py`.
    * Ensure tests stub `spacy` via new import path.
  * Create `analysis/treesitter/` for tree-sitter integration.
    * Extract tree-sitter utilities from `context.py` into `analysis/treesitter/parsers.py` or similar.
    * Evaluate `context.py` to keep only generic workspace context; delegate parser loading through new module.
* **SOLID guardrails:** Provide minimal `SpacyAnalyser`/`TreeSitterParser` interfaces in `interfaces/analysis.py`, supply fake implementations in tests to prove LSP, and ensure higher layers consume analyzers via factories rather than direct module imports.

### diagnostics/

* **Scope:** Tool-agnostic diagnostic models, flows, filtering, and presentation-ready transformations.
* **Candidate moves:**
  * `diagnostics.py` → reorganized into `diagnostics/core.py` (data structures) and `diagnostics/formatters.py` if needed.
  * `execution/diagnostic_filter.py` (and related filtering logic) → `diagnostics/filtering.py`.
  * `tooling/json_diagnostics.py` (parsing aggregated diagnostics) → `diagnostics/json_import.py`.
  * Reporting glue currently under `reporting/` should depend on these new abstractions rather than reimplementing conversions.
* **Goals:** Provide a single entry point (e.g., `diagnostics.api`) that orchestrator, reporting, and CLI consumers use.
* **SOLID guardrails:** Require diagnostics modules to expose a `PipelineDefinition` describing stages, enforce ISP by separating sourcing (`DiagnosticSource`) from rendering adapters, and add contract tests verifying alternative pipelines can replace the default.

### interfaces/

* **Scope:** Protocols, abstract base classes, and dependency-inversion contracts shared across modules.
* **Initial targets:**
  * Protocols in `annotations.py`, `checks/licenses.py`, `tools/base.py`, `tooling/command_options.py`, `config_loader.py`, etc.
  * Organize by domain: `interfaces/analysis.py`, `interfaces/tooling.py`, `interfaces/config.py`, etc., re-exported in `interfaces/__init__.py` for ease of consumption.
* **Benefits:**
  * Break circular imports by having implementations depend on interfaces.
  * Clarify extension points for external integrations or plugins.
* **SOLID guardrails:** Keep each protocol file focused (analysis, catalog, cli, etc.), add usage guidelines documenting invariants, and ensure dependency inversion by having composition roots (CLI app, orchestrator bootstrap) be the only locations importing concrete implementations.
* **Entry point integration:** Formalise plugin loading via Python entry points (`pyqa.catalog.plugins`, `pyqa.cli.plugins`, etc.) that provide interface-compliant factories discoverable at runtime.

### cli/commands/

* **Scope:** Consolidate Typer entrypoints, option models, and orchestration helpers into per-command packages aligned with the patterns in `src/pyqa/cli/CLI_MODULE.md` and `src/pyqa/cli/SOLID_CLI.md`.
* **Candidate moves:**
  * Group `_lint_*` modules under `cli/commands/lint/` (e.g., `models.py`, `services.py`, `runtime.py`, `progress.py`).
  * Move `cli/quality.py`, `cli/config_cmd.py`, `cli/clean.py`, `cli/security.py`, and `cli/tool_info.py` into sibling packages with shared base classes in `cli/core/`.
  * Extract wrapper launch logic (`cli/_cli_launcher.py`, shell entry shims) into `cli/launcher/` per `src/pyqa/cli/WRAPPER.md`, exposing a small `CliLauncher` interface that commands depend upon.
* **Interfaces:** Define `CliCommand`/`CliService` protocols in `interfaces/cli.py` so orchestration code targets abstractions rather than module-level functions.
* **Docs impact:** Update CLI docs to reference the new package layout and ensure Typer app registration uses the shared decorators consistently.
* **SOLID guardrails:** Each command package must own a single orchestration entry and depend only on command-specific services; enforce DIP by injecting services via constructors and add smoke tests with stub services to guarantee substitution.
* **Entry point integration:** Support CLI extensions via entry points that register additional commands through the shared `CliCommand` interface.

### config/

* **Scope:** Centralise configuration models, loading logic, shared defaults, and validation helpers.
* **Candidate moves:**
  * Relocate `config.py` to `config/models.py` and expose typed settings via `config/__init__.py`.
  * Split `config_loader.py` into `config/loaders/toml_loader.py` (parsing), `config/loaders/cache.py` (TOML cache), and `config/loaders/sources.py` (search order, overrides).
  * Move `config_loader_sections.py` into `config/sections/` to keep mutators per domain (discovery, execution, reporting) and pair them with schema docs.
  * Gather ancillary helpers (`config_utils.py`, filter defaults in `constants.py`, shared knobs from `tooling/catalog/docs/SHARED_KNOBS.md`) under `config/defaults/`.
* **Interfaces:** Provide `ConfigSource`, `ConfigResolver`, and `ConfigMutator` protocols in `interfaces/config.py` so CLI/builders inject behaviour cleanly.
* **Integration notes:** Align with `TOOL_RESTRUCTURE_PLAN.md` by ensuring catalog-derived options feed straight into the config defaults package.
* **SOLID guardrails:** Define clear layering diagrams (loaders → mutators → models) and unit tests using dummy sources to confirm modules remain closed for modification; prohibit direct catalog or CLI imports to keep dependencies inverted.

### orchestration/

* **Scope:** House the execution pipeline, action scheduling, worker coordination, and lifecycle hooks currently spread across `execution/`.
* **Candidate moves:**
  * Move `execution/orchestrator.py` to `orchestration/pipeline.py`, `execution/action_executor.py` to `orchestration/executor.py`, `execution/tool_selection.py` to `orchestration/planning.py`, and `execution/worker.py` to `orchestration/workers.py`.
  * Keep runtime state builders (`execution/runtime.py`) in `orchestration/runtime/`, depending only on interfaces and new cache/diagnostics packages.
  * Relocate phase constants (currently embedded in CLI literals) into `orchestration/phases.py` so catalog metadata can drive execution order per `TOOL_RESTRUCTURE_PLAN.md`.
* **Interfaces:** Surface `ExecutionPipeline`, `ActionExecutor`, and `RunHooks` contracts in `interfaces/orchestration.py` to decouple CLI and quality commands from implementation choices.
* **Future tie-ins:** Provide seams for Tree-sitter fixers and spaCy post-processors described in `SPACY_TREESITTER.md` to plug into pre/post phases.
* **SOLID guardrails:** Publish lifecycle hooks (`before_phase`, `after_phase`) and require orchestrator components to rely on interface injection; add integration tests with mock pipelines to prove any compliant executor can be swapped without breaking callers.

### catalog/

* **Scope:** Unify catalog data loading, strategy dispatch, and runtime tool metadata under a single package informed by `TOOL_RESTRUCTURE_PLAN.md` and `tooling/TOOLING.md`.
* **Candidate moves:**
  * Relocate `tooling/loader.py`, `tooling/catalog/*`, and `tooling/schema/*` to `catalog/loader/` and `catalog/data/` while keeping JSON assets colocated.
  * Move `tools/catalog_metadata.py`, `tools/builtin_registry.py`, `tools/settings.py`, and `tools/base.py` into `catalog/runtime/` so orchestrator consumers import from one cohesive namespace.
  * Merge `tooling/command_options.py`, `tooling/project_scanner.py`, and strategy factories into `catalog/strategies/`, exposing only documented entry points.
  * Eliminate dependencies on pyqa-specific runtime code so the package can be released as an independent tooling specification.
* **Interfaces:** Define `ToolDefinition`, `StrategyFactory`, and `CatalogSnapshot` protocols in `interfaces/catalog.py`; implementations stay inside `catalog/runtime`.
* **Docs impact:** Update `TOOL_RESTRUCTURE_PLAN.md`, `tooling/TOOLING.md`, and `tooling/catalog/strategies/STRATEGIES.md` to reflect the new module paths and clarify authoring steps.
* **SOLID guardrails:** Enforce SRP by keeping JSON I/O, validation, and runtime materialisation in distinct submodules; add schema contract tests for extension strategies; ensure runtime code consumes catalog data solely through interfaces to preserve DIP.
* **Entry point integration:** Provide `catalog/plugins.py` that resolves registered tool/strategy packs via entry points so external contributors can extend the catalog without modifying core modules.
* **Public API polish:** Ensure exported dataclasses and helper objects provide rich dunder methods (`__repr__`, `__eq__`, optional `__hash__`, `to_dict`) and exhaustive docstrings to support unknown third-party consumers.

### tooling\_spec/

* **Scope:** Publishable package that bundles catalog schemas, metadata models, and strategy descriptors for reuse by external orchestrators (e.g., golangci-lint, biome, playwright-specific linters).
* **Deliverables:**
  * Assemble schemas, fragments, loader APIs, and example catalogs into a zero-pyqa-dependency distribution (wheel + sdist).
  * Provide semantic-versioned releases with changelog, schema diffs, and migration notes.
  * Ship detailed documentation (API reference, cookbook, JSON schema guide, plugin authoring manual) and sample integrations in multiple languages.
* **Interfaces:** Re-export `ToolDefinition`, `StrategyDefinition`, `CatalogSnapshot`, and related dataclasses with comprehensive dunders and conversion helpers (`to_dict`, `from_dict`).
* **Community enablement:** Document entry point groups for third-party plugins, establish compatibility policy (schemaVersion ↔ package version), and curate reference tooling definitions contributed by external maintainers.
* **SOLID guardrails:** Keep the package free of pyqa imports, enforce strict typing, and add integration tests verifying round-trip serialization between JSON and Python models.

### reporting/

* **Scope:** Separate diagnostic transformations, advice generation, and emitter/rendering logic so consumers can cherry-pick functionality.
* **Candidate moves:**
  * Group `reporting/advice*.py` and `reporting/highlighting.py` into `reporting/advice/` that depends on the new `diagnostics` API rather than raw models.
  * Move `reporting/emitters.py`, `reporting/formatters.py`, and `reporting/output_modes.py` into `reporting/output/` with shared templates/utilities.
  * Expose CLI-agnostic rendering helpers (Markdown, SARIF, JSON) via `reporting/presenters/`, leaving CLI-specific slices inside `cli/commands` packages.
* **Interfaces:** Establish `DiagnosticPresenter` and `AdviceProvider` protocols in `interfaces/reporting.py` to keep orchestrator vs CLI dependencies isolated.
* **Integration notes:** Coordinate with the diagnostics reorg so dedupe/filter steps happen before rendering; align documentation in `diagnostics/core` and CLI guides.
* **SOLID guardrails:** Require presenters to depend only on diagnostics interfaces, add snapshot tests with alternative presenters to guarantee substitutability, and document allowed dependencies to prevent CLI-specific logic from leaking in.
* **Logging alignment:** Shift shared logging formatters/adapters into `core/logging/` (or `reporting/logging/`) so CLI and orchestrator reuse the same structured logging utilities.

### environments/

* **Scope:** Consolidate environment preparation, runtime installation, and workspace probing currently scattered across `tool_env/`, `environments.py`, `installs.py`, and `workspace.py`.
* **Candidate moves:**
  * Create `environments/models.py` and relocate `tool_env/models.py`, `tool_env/versioning.py`, and cache layout helpers into `environments/state/`.
  * Move installer orchestration (`tool_env/preparer.py`, `installs.py`) into `environments/installers/`, exposing catalog-friendly installers for reuse.
  * Fold workspace detection (`workspace.py`), filesystem guards, and process utilities into `environments/workspace.py` or a sibling `infrastructure/` package shared by CLI wrappers.
* **Interfaces:** Provide `EnvironmentPreparer`, `RuntimeResolver`, and `WorkspaceLocator` protocols in `interfaces/environment.py` to support alternative implementations (e.g., remote execution).
* **Docs impact:** Update any references in `README.md` and wrapper docs to the new module paths and runtime caching expectations.
* **SOLID guardrails:** Maintain strict layering (installers may call filesystem/process utilities but never CLI), create fake preparers for tests, and assert via lint checks that `environments` imports only `interfaces` and `core` helpers.

### discovery/

* **Scope:** Offer a cohesive API for repository discovery, file selection, and planner logic used by catalog strategies and CLI commands.
* **Candidate moves:**
  * Move `tooling/project_scanner.py` into `discovery/planners.py`, aligning with existing `discovery/base.py`, `discovery/filesystem.py`, and `discovery/git.py`.
  * Extract shared exclusion/target resolution helpers into `discovery/rules.py`, reusing catalog metadata rather than duplicating option handling.
  * Ensure `discovery/utils.py` focuses on composable primitives that strategies (`command_project_scanner`, etc.) can call.
* **Interfaces:** Introduce `DiscoveryStrategy`, `TargetPlanner`, and `ExcludePolicy` protocols in `interfaces/discovery.py`.
* **Future alignment:** Prepare for Tree-sitter aware discovery (language heuristics, shebang parsing) referenced in `SPACY_TREESITTER.md` and CLI shebang plans.
* **SOLID guardrails:** Document contract tests for planners (input config → target plan), and require new discovery behaviours to register via strategy tables instead of editing orchestration code.

### compliance/

* **Scope:** Group policy-driven checks (`quality.py`, `banned.py`, `checks/`, `security.py`) into a coherent package independent of CLI wiring.
* **Candidate moves:**
  * Move `quality.py`, `security.py`, `banned.py`, and `checks/` into `compliance/` with submodules for `policies`, `auditors`, and `remediators` (e.g., `checks/license_fixer.py`).
  * Expose reusable services (license policy evaluation, security scan orchestration) separate from CLI wrappers so they can be reused by automated workflows.
  * Ensure configuration hooks (strictness, sensitivity from `tooling/catalog/docs/SHARED_KNOBS.md`) route through the new `config/` package.
* **Interfaces:** Provide `ComplianceCheck`, `PolicyEvaluator`, and `RemediationService` protocols in `interfaces/compliance.py`.
* **Docs impact:** Update CLI documentation and README references to point at the new package; ensure tests reference services instead of CLI modules directly.
* **SOLID guardrails:** Keep compliance modules focused on policy evaluation; stub external services in tests to ensure LSP, and require DIP by wiring implementations through composition roots (CLI, CI entrypoints).

### core/

* **Scope:** Host cross-cutting foundations (`models.py`, `metrics.py`, `severity.py`, `serialization.py`, `console.py`, `logging.py`, `process_utils.py`) to clarify layering boundaries.
* **Candidate moves:**
  * Create `core/models/` for `models.py`, splitting large dataclasses into thematic modules (diagnostics, runs, reports) consumed by higher layers.
  * Move `metrics.py` and `severity.py` into `core/metrics/`, and `serialization.py` into `core/serialization/` with explicit dependencies on `diagnostics` and `catalog` interfaces only.
  * Gather shared runtime utilities (`console.py`, `logging.py`, `process_utils.py`, `paths.py`) under `core/runtime/` to enforce consistency across CLI and orchestration usage.
* **Interfaces:** Define light-weight contracts (`ConsoleFactory`, `LoggerFactory`, `Serializer`) in `interfaces/core.py` so features can stub or replace implementations in tests.
* **SOLID guardrails:** Publish dependency rules (core may depend on stdlib and third-party foundations but nothing domain-specific), add architectural tests verifying no higher-level module imports core internals directly, and document constructor injection patterns for consoles/loggers.
* **Dependency injection:** Introduce a lightweight service container (`core/runtime/di.py`) to register default factories (console, logging, cache) and enable composition roots to override bindings.
* **Optional dependencies:** Gate rich console/emoji/uv integrations behind feature flags so library consumers can opt-out while maintaining the same interfaces.

## Migration Plan (High Level)

1. Introduce new packages with `__init__.py` files and placeholder exports to avoid import errors during incremental moves.
2. Move caching code first; update imports in `execution/orchestrator.py`, `execution/cache_context.py`, and configuration loaders.
3. Refactor spaCy and tree-sitter logic into dedicated sub-packages, adjusting tests and dependency injection patterns.
4. Consolidate diagnostic flows; ensure orchestrator uses the new APIs and delete legacy imports immediately to surface gaps (no transitional aliases).
5. Extract protocols and type hints into `interfaces/`; replace direct Protocol definitions in feature modules with imports from the new package.
6. Remove transitional re-exports after validating no external consumers rely on legacy paths.

## Cross-Cutting Considerations

* Update `__all__` exports and public API docs to reflect new module paths.
* Revise import ordering and dependency direction: high-level modules should depend on `interfaces` and feature packages, not vice versa.
* Evaluate packaging metadata (`pyproject.toml`, `__init__.py` exports) for new modules.
* Ensure type-checking configuration (`mypy.ini`, `pyrightconfig.json`) includes new packages.
* Add unit / integration tests around moved code to confirm behavior unchanged; consider introducing contract tests for interfaces.
* Communicate module moves via release notes / migration guide; no deprecation period or compatibility aliases will be provided.
* Establish packaging, documentation, and release automation for the standalone tooling spec (version bumps, changelog, schema diffs).

## Decisions

* **Backwards compatibility:** No stub modules or transitional aliases will be provided; new package paths take effect immediately.
* **Plugin loading:** Entry point-based plugin hooks will be implemented as part of the interfaces effort.
* **External consumers:** No third-party packages depend on current internals, so no migration messaging or semantic-version grace period is required.
* **Ownership:** Packages remain community-maintained with no team-level ownership assignments.
* **Tooling spec:** The catalog/tooling\_spec packages will be released as an independent project with semver guarantees and first-class documentation for the broader lint tooling ecosystem.
