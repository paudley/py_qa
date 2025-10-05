# pyqa Module Reorganization Plan

## Objectives
- Structure packages around single responsibilities to reinforce SOLID boundaries.
- Isolate third-party integrations (spaCy, tree-sitter) so they can evolve independently.
- Consolidate caching and diagnostic flows to simplify import graphs and make dependencies explicit.
- Introduce a dedicated interfaces layer that defines stable protocols and abstractions consumed by higher-level modules.

## Proposed Package Layout

### cache/
- **Scope:** Result caching, cache token computation, persistence of tool metadata, helpers for cache-aware orchestration.
- **Candidate moves:**
  - `execution/cache.py` → `cache/result_store.py` (consider splitting Request models vs persistence helpers).
  - `execution/cache_context.py` → `cache/context.py` (wrap cache_dir resolution + token building).
  - `tool_versions.py` → `cache/tool_versions.py` (used by execution cache context).
  - Cache-related helpers in `config_loader.py` / `config_loader_sections.py` (e.g., TOML cache) should be reviewed—either remain near config or migrate to `cache/config_sources.py` if shared.
  - `console.ConsoleManager` cache is orthogonal; recommend leaving under `console` unless we generalize small in-memory caches (see "Future considerations").
- **Interfaces:** expose narrow APIs (`CacheRepository`, `CacheTokenBuilder`) to decouple orchestrator from implementation details.

### analysis/
- **Scope:** Code analysis utilities and integrations beyond core lint orchestration. Provide sub-packages to isolate external dependencies.
- **Restructure:**
  - `analysis/` remains top-level home for generic analysis helpers (`change_impact.py`, `navigator.py`, `suppression.py`).
  - Create `analysis/spacy/` for spaCy-specific NLP logic.
    - Move `annotations.py` (rename to `analysis/spacy/annotations.py`) and align exports via `analysis/spacy/__init__.py`.
    - Ensure tests stub `spacy` via new import path.
  - Create `analysis/treesitter/` for tree-sitter integration.
    - Extract tree-sitter utilities from `context.py` into `analysis/treesitter/parsers.py` or similar.
    - Evaluate `context.py` to keep only generic workspace context; delegate parser loading through new module.

### diagnostics/
- **Scope:** Tool-agnostic diagnostic models, flows, filtering, and presentation-ready transformations.
- **Candidate moves:**
  - `diagnostics.py` → reorganized into `diagnostics/core.py` (data structures) and `diagnostics/formatters.py` if needed.
  - `execution/diagnostic_filter.py` (and related filtering logic) → `diagnostics/filtering.py`.
  - `tooling/json_diagnostics.py` (parsing aggregated diagnostics) → `diagnostics/json_import.py`.
  - Reporting glue currently under `reporting/` should depend on these new abstractions rather than reimplementing conversions.
- **Goals:** Provide a single entry point (e.g., `diagnostics.api`) that orchestrator, reporting, and CLI consumers use.

### interfaces/
- **Scope:** Protocols, abstract base classes, and dependency-inversion contracts shared across modules.
- **Initial targets:**
  - Protocols in `annotations.py`, `checks/licenses.py`, `tools/base.py`, `tooling/command_options.py`, `config_loader.py`, etc.
  - Organize by domain: `interfaces/analysis.py`, `interfaces/tooling.py`, `interfaces/config.py`, etc., re-exported in `interfaces/__init__.py` for ease of consumption.
- **Benefits:**
  - Break circular imports by having implementations depend on interfaces.
  - Clarify extension points for external integrations or plugins.

## Migration Plan (High Level)
1. Introduce new packages with `__init__.py` files and placeholder exports to avoid import errors during incremental moves.
2. Move caching code first; update imports in `execution/orchestrator.py`, `execution/cache_context.py`, and configuration loaders.
3. Refactor spaCy and tree-sitter logic into dedicated sub-packages, adjusting tests and dependency injection patterns.
4. Consolidate diagnostic flows; ensure orchestrator uses the new APIs while keeping backwards compatibility shims (temporary re-export modules) until all call sites migrate.
5. Extract protocols and type hints into `interfaces/`; replace direct Protocol definitions in feature modules with imports from the new package.
6. Remove transitional re-exports after validating no external consumers rely on legacy paths.

## Cross-Cutting Considerations
- Update `__all__` exports and public API docs to reflect new module paths.
- Revise import ordering and dependency direction: high-level modules should depend on `interfaces` and feature packages, not vice versa.
- Evaluate packaging metadata (`pyproject.toml`, `__init__.py` exports) for new modules.
- Ensure type-checking configuration (`mypy.ini`, `pyrightconfig.json`) includes new packages.
- Add unit / integration tests around moved code to confirm behavior unchanged; consider introducing contract tests for interfaces.
- Communicate module moves via release notes / migration guide; deprecate old import paths with warnings if external users are affected.

## Future Enhancements to Explore
- Central in-memory caching utilities (decorators, TTL caches) under `cache/in_memory.py` to replace ad-hoc `functools.cache` usage.
- Introduce dependency injection helpers (e.g., simple service container) to wire implementations to interfaces.
- Evaluate splitting `execution/orchestrator.py` into smaller orchestrator components once diagnostics and cache logic are extracted.
- Consider separating CLI-facing code from core library (e.g., move Typer command models under `cli/commands/`).
- Audit logging responsibilities; a dedicated `logging/` sub-package with structured logging adapters may reduce cross-module dependencies.

## Open Questions
- Should we maintain backwards-compatible import aliases (e.g., stub modules) for at least one release cycle?
- Do we want to formalize plugin loading via entry points as part of the interfaces effort?
- Are there third-party consumers relying on internal modules (`annotations`, `context`) that require migration messaging or semantic version bump?
- Which teams own each package after the reorg (documentation, code ownership updates)?

