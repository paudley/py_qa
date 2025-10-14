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
* Lint suppressions are discouraged; only the documented set (dynamic cache helpers, subprocess hardening, protocol annotations, controlled CLI imports, and download safety checks) remain approved. Any new suppression must include an inline justification and prior review.
* Prefer `functools.partial` (or companion helpers), the relevant utilities from `itertools` (including `starproduct` on Python ≥3.13), and high-level helpers from `operator`/`contextlib` before rolling custom closures or resource wrappers.

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

## Phase 13 – Generic Dunder Guidance (1 sprint)

* ✅ **Tree-sitter heuristics complete** – `generic-value-types` linter analyses classes for dataclass/slots/iterable traits and reports missing dunders with configurable severity using Tree-sitter.
* ✅ **Suppression integration** – findings honour `suppression_valid` directives through the shared suppression registry.
* ✅ **CLI exposure & docs** – `--check-value-types-general` flag enabled, configuration schema documented, and Phase 13 guide expanded with usage examples.

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

## Phase 7 – SOLID Hardening & Backlog Cleanup (1 sprint)

1. **Analysis restructuring**
   * Move `AnnotationEngine` heuristics into `analysis/spacy` and
     `analysis/treesitter` subpackages, wiring `TreeSitterContextResolver` through
     protocols defined in `interfaces/analysis.py`.
   * Update orchestrator and reporting flows to depend on the `AnnotationProvider`
     interface so spaCy/Tree-sitter integrations can be swapped or faked in
     tests.
2. **Core + DI conformance**
   * Relocate remaining foundational modules (`models.py`, `logging.py`,
     `process_utils.py`, `metrics.py`, `serialization.py`) into the `core/`
     hierarchy, exposing narrow factories that higher layers resolve via the
     service container.
   * Refine `core/runtime/di.py` registrations so they import interfaces (not
     concrete packages), and register implementation factories inside their own
     packages to restore dependency inversion.
3. **Repository hygiene**
   * Purge tooling caches (`.ruff_cache`, `.mypy_cache`, other artifacts) from
     package directories and add safeguards to prevent them from re-entering the
     tree.
   * Audit remaining modules against the `REORG_MODULES.md` layout, capturing any
     stragglers in follow-up tickets if they cannot move in this phase.
4. **Verification**
   * Extend architectural tests to cover the new interfaces and layering rules
     (e.g., orchestrator must resolve analyzers via interfaces, `core/` may not
     depend on feature packages).
   * Add regression tests for the analyzer injection seam to prove alternative
     implementations can be wired without touching orchestration code.
5. **CLI surface packages**
   * Promote `clean.py` into a dedicated `clean/` package (`plan.py`, `runner.py`,
     `cli.py`) that exports a narrow API for workspace cleanup.
   * Extract hook orchestration into a standalone `hooks/` package (`registry.py`,
     `runner.py`, `models.py`) and update service registration via interfaces.
6. **Root module decomposition roadmap**
   * **Responsibility audit (SRP):** catalogue every remaining top-level module
     (`environments.py`, `console.py`, `config_loader.py`, `update.py`, etc.) and
     record its primary responsibility in `docs/reorg/PHASE7A.md` before moving
     code. Use the audit to assign each responsibility into the future `core/`,
     `cli/`, `runtime/`, or `platform/` families.
   * **Interfaces first (ISP/DIP):** expand `src/pyqa/interfaces` with the
     protocols the refactors will rely on—`EnvironmentInspector` and
     `VirtualEnvDetector` for environment work, `ConsoleManager`/`AnsiFormatter`
     for terminal IO, `Installer`/`RuntimeBootstrapper` for tooling installs, and
     a `ConfigLoader` contract for configuration wiring. Update current consumers
     to depend on these interfaces ahead of file moves to keep churn incremental.
   * **Subpackage creation:**
     * `core/environment/` for `environments.py` and the `tool_env/` runtime
       helpers (split into `detectors.py`, `runtimes/`, `versioning.py`).
     * `core/config/` hosting the new loader/sections/util modules that replace
       `config_loader.py`, `config_loader_sections.py`, and `config/utils.py`.
     * `runtime/console/` for console and logging bootstrap glue now under
       `console.py`, `hooks.py`, and related helpers.
     * `runtime/installers/` for `installs.py`, installer helpers in
       `tool_env`, and `update.py` orchestration.
     * `platform/languages/` for language/paths heuristics currently under
       `languages.py`, `paths.py`, and parser glue.
   * **Incremental migration:** for each subpackage create the empty package and
     architectural guardrail, move code with `git mv`, update imports, run
     focused pytest targets, then delete the legacy module and refresh docs to
     avoid large, risky commits.
   * **LSP/DIP enforcement:** add new contract tests that exercise implementations
     through the freshly introduced interfaces (e.g., CLI tests using fake
     `EnvironmentInspector`), and extend `core/runtime/di.py` registrations to
     resolve only interface names while concrete packages self-register.

* **Docs & tooling:** once moves complete, refresh `REORG_MODULES.md`, developer
  documentation, and dependency-graph artefacts so the new layout is
  discoverable.

7. **Interface gap audit (2025-02-??)**
   * Replace direct `AnnotationEngine` construction in orchestrator and CLI/reporting surfaces with interface-driven factories registered via DI (`src/pyqa/orchestration/orchestrator.py:18`, `src/pyqa/orchestration/orchestrator.py:303`, `src/pyqa/cli/commands/lint/reporting.py:13`, `src/pyqa/cli/commands/lint/reporting.py:47`).
   * Inject diagnostic annotation providers instead of relying on module-level singletons inside diagnostics and reporting presenters (`src/pyqa/diagnostics/core.py:22`, `src/pyqa/diagnostics/core.py:48`, `src/pyqa/reporting/presenters/formatters.py:14`, `src/pyqa/reporting/presenters/formatters.py:135`, `src/pyqa/reporting/output/highlighting.py:14`, `src/pyqa/reporting/output/highlighting.py:18`, `src/pyqa/reporting/presenters/emitters.py:25`, `src/pyqa/reporting/presenters/emitters.py:770`).
   * Expand analysis interfaces to cover change-impact, suppression, and navigator passes so orchestration no longer imports concrete functions (`src/pyqa/orchestration/orchestrator.py:18`).
   * Promote function-scale estimation to the DI container and update consumers to request the interface rather than instantiating services inline (`src/pyqa/analysis/navigator.py:137`, `src/pyqa/reporting/advice/builder.py:84`, `src/pyqa/reporting/advice/builder.py:665`).
   * Introduce a `ContextResolver` provider seam for modules that still instantiate `TreeSitterContextResolver` directly (`src/pyqa/analysis/change_impact.py:32`, `src/pyqa/analysis/annotations/engine.py:120`, `src/pyqa/analysis/treesitter/resolver.py:676`, `src/pyqa/cli/commands/doctor/command.py:310`).

## Phase 8 – Code Quality Compliance Sweep (multi-sprint)

Following the SOLID-focused refactors, we must bring the codebase into alignment with the reinforced coding rules, splitting the initiative into targeted sub-phases.

### Phase 8.0 – Internal Linter Orchestration

1. **Unify internal linter infrastructure**
   * Introduce an `InternalToolDefinition` registry that maps the existing internal linters (docstrings, suppressions, strict typing, closures, signatures, cache usage, and the quality/license enforcement) onto the standard `Tool` execution pipeline.
   * Provide an adapter layer that converts each internal runner into a `ToolAction` producing `ToolOutcome` objects, avoiding direct logging and aligning with the diagnostics pipeline.
2. **Orchestrator integration**
   * Extend the orchestrator plan/build steps so internal linters are scheduled alongside external tools when selected (via `--only`, meta flags, or presets). Ensure cache semantics and disable/enable flags work consistently.
   * Update progress handling (`ExecutionProgressController`) so totals/descriptions include internal tools and the live status reflects their execution.
3. **CLI/config wiring**
   * Map CLI flags (`--check-*`, `--normal`) to internal tool selection through the registry; set `LintOptions.provided` markers for reporting.
   * Document the selection semantics in CLI help and developer docs.
4. **Testing**
   * Add integration tests covering mixed internal/external runs, internal-only runs, and `--normal` presets to confirm orchestrator scheduling, progress rendering, and consolidated output.
   * Provide regression coverage ensuring internal tools contribute to RunResult diagnostics and stats without extra log noise.
5. **Operational parity checklist**
   * Ensure every internal linter shares the standard diagnostics pipeline: normalized workspace-relative paths, suppression handling, deduplicated highlights, and stats aggregation identical to external tools.
   * Remove pre-run console spam by routing docstring/license findings through the orchestrator result printer and progress controller rather than direct logging.
   * Honour global directory/file exclusions (`.lintignore`, default skip sets) and ensure progress bars tick per tool with accurate counts for internal-only and mixed runs.
   * Guarantee `./lint -n` enables the full suite of new internal passes by default so consolidated runs exercise the entire policy surface.
   * Update documentation and developer notes to reflect the parity expectations so future internal tools follow the same contract without bespoke glue code.

### Phase 8A – Documentation & Commentary

1. **Docstring coverage audit**
   * Record every module/function lacking a Google-style docstring; prioritise high-touch areas (`src/pyqa/core/runtime/process.py`, `src/pyqa/cli/launcher/__init__.py`, `src/pyqa/orchestration/orchestrator.py`, `src/pyqa/reporting/output/modes.py`).
2. **Documentation rollout**
   * Add concise Google-style docstrings and rationale comments where logic is non-trivial (e.g., `_build_cli_invocation_code`, `_handle_cached_outcome`).
3. **Automation**
   * Build a hybrid docstring linter that combines Tree-sitter structural analysis with spaCy quality checks (section completeness, language heuristics); expose it via `pyqa lint --check-docstrings` and wire into CI before documentation updates land. Ensure the implementation hooks align with the broader roadmap in `SPACY_TREESITTER.md`, so later duplicate-comment detection can reuse the same pipeline.
   * Lessons learned: each linter must emit a fully populated `ToolOutcome` and integrate directly through the orchestrator so progress, suppression, and highlighting work uniformly. Regression coverage now exercises these paths via `tests/test_lint_cli.py::test_activate_internal_linters_meta_sets_only` and `tests/test_lint_cli.py::test_ensure_internal_tools_registered`, ensuring meta flags map to tool selection without duplicate warnings.

### Phase 8B – Lint Suppression Rationalisation

1. **Catalogue verification**
   * Confirm the existing approved suppressions (cache helpers, subprocess wrappers, protocol headers, CLI imports, download safeguards) match the allowed list in the guidelines.
2. **Refactor opportunity scan**
   * For each approved suppression, investigate whether refactoring can eliminate it (e.g., attach cache helpers via Protocol typing).
3. **Policy enforcement**
   * Implement a suppression-whitelist linter, surfaced as `pyqa lint --check-suppressions`, to flag any inline directive outside the sanctioned list and require a justification block.

### Phase 8C – Strict Typing & Interface Refinement

1. **Reduce `Any` usage**
   * Focus on high-traffic modules: `src/pyqa/core/runtime/di.py`, `src/pyqa/cache/in_memory.py`, `src/pyqa/interfaces/*`, `src/pyqa/reporting/*`.
2. **Protocol enhancements**
   * Introduce typed payload classes or generics for service containers, cache keys, CLI pipelines.
3. **Static analysis**
   * Deliver a typing linter (`pyqa lint --check-types-strict`) that scans annotations for `Any`/`object` and flags unapproved usages before tightening type checkers.

### Phase 8D – Callable Composition & Helpers

1. **Replace bespoke closures**
   * Identify closure-heavy helpers (`cli/launcher`, orchestration preparation hooks, reporting adapters) and refactor to `functools.partial`, `itertools` (e.g., `chain`, `batched`, `starproduct`), `operator` call adapters, or `contextlib` utilities instead of bespoke logic.
2. **Guideline enforcement**
   * Add a callable-composition linter, invokable via `pyqa lint --check-closures`, that detects simple closure factories better served by `functools.partial`, `itertools` (with Python-version awareness for `starproduct`), or `operator` helpers.

### Phase 8E – Parameter Object Introduction

1. **Survey high-arity functions**
   * Target CLI entry points, reporting renderers, and orchestration helpers exceeding five parameters.
2. **Introduce dataclasses**
   * Define parameter objects (e.g., `HighlightOptions`, `NavigatorContext`, `FetchPlan`) to consolidate arguments.
3. **Update call sites & tests**
   * Precede refactors with a signature-width linter (`pyqa lint --check-signatures`) that reports functions surpassing the parameter threshold or relying on `**kwargs` without approved patterns.

### Phase 8F – Caching Consistency

1. **Inventory `functools.lru_cache` usage**
   * Replace occurrences listed in the audit (`catalog/metadata.py`, `discovery/rules.py`, `analysis/treesitter/resolver.py`, etc.) with adapters leveraging `pyqa.cache`.
2. **Decorator alignment**
   * Extend `pyqa.cache` with variants (e.g., `memoize_typed`) if needed to mirror missing functionality.
3. **Guardrail linter**
   * Implement a static check (`pyqa lint --check-cache-usage`) that rejects new `functools.lru_cache` imports/usages outside the caching package.

### Phase 8G – Verification & Tooling

1. **Automated checks**
   * Integrate the newly built linters (docstrings, suppressions, typing, closures, signature width, caching) into the CI pipeline and surface them collectively via `pyqa lint --strict`; ensure the closures linter recognises Python 3.13 features such as `itertools.starproduct` and warns when unavailable. The `./lint -n` entrypoint must invoke each checker so local presubmits match CI coverage.
   * Maintain regression coverage validating that internal linters append diagnostics to `RunResult` with accurate stats/diagnostic counts and no double-logged warnings when invoked both via meta flags and selection filters (`--check-docstrings`, `--only docstrings`); see `tests/test_lint_cli.py::test_append_quality_docstrings_meta` and `tests/test_lint_cli.py::test_append_quality_docstrings_filters`.
2. **Documentation update**
   * Refresh developer docs summarising the new compliance expectations and tooling support.
3. **Parity expectations**
   * Each in-house linter should mimic external behaviour: honour CLI/config exclusions, emit structured diagnostics (tool/action, severity, path), integrate with the existing stats/reporting pipeline, and record warnings whenever dependencies such as spaCy models or Tree-sitter grammars are missing.

### Phase 8H – Value-Type Ergonomics

1. **Navigator buckets**
   * Implement `__len__` (and, if beneficial, `__iter__`) on `NavigatorBucket` (`src/pyqa/analysis/navigator.py`) so hotspot collections integrate naturally with standard iteration utilities.
2. **Cleanup results**
   * Provide a truthy semantic (e.g., `__bool__` or `__len__`) for `CleanResult` (`src/pyqa/clean/runner.py`) to reflect whether anything was removed or skipped without inspecting internals.
3. **Service container conveniences**
   * Add `__contains__`/`__len__` helpers to `ServiceContainer` (`src/pyqa/core/runtime/di.py`) to simplify optional dependency checks and diagnostics.

Deliverable: Completion of Phase 8 means every coding-rule exception is justified, doc coverage is high, type annotations are strict, callable composition prefers the standard toolbox, and high-arity signatures are encapsulated.

### Phase 9 – DI & Interface Enforcement

*See `docs/reorg/PHASE9.md` for the detailed execution plan.*

1. Integrate pyqa-scoped internal linters (`pyqa-interfaces`, `pyqa-di`, `pyqa-module-docs`, etc.) and wire them into the lint pipeline with the `--pyqa-rules` opt-in.
2. Extend architectural tests to enforce module-level SOLID boundaries and DI composition rules.
3. Backfill package-level documentation (`{MODULE}.md`) capturing usage patterns, DI seams, and extension points across the repository.

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
| 7     | 1       | SOLID hardening, DI cleanup, analysis package split              |

Total: roughly 14–15 sprints (~6.5 months) assuming two-week iterations and
parallel work streams where feasible.

### Phase 10 – Quality Tool Decomposition

*Elevate repository quality checks into first-class lint tools aligned with the
internal tooling model.*

1. **Schema enhancement** – extend the tool metadata schema with an optional
   `automatically_fix` flag and set it to `true` for all existing fix/format
   tools so behaviour remains declarative. ✅
2. **Retire monolithic quality linter** – remove `run_quality_linter` and the
   single "quality" entry from the internal registry. ✅
3. **Introduce dedicated internal tools** – surface the following checks with
   standalone `--check-*` toggles and `automatically_fix=false` ✅:
   * `license-header`
   * `copyright`
   * `python-hygiene`
   * `file-size`
   * `pyqa-schema-sync` (pyqa-scoped only)
4. **Pipeline integration** – register the new tools, expose them via
   `--explain-tools`, and ensure they activate at `sensitivity >= strict`
   without attempting automatic fixes during lint runs. ✅
5. **Quality CLI alignment** – refactor `check-quality` to dispatch through the
   new tool implementations while keeping `--fix` semantics for license and
   copyright remediation. ⬜️
6. **Documentation refresh** – update developer docs, Phase 9–10 narrative, and
   selection guidance to reflect the new tooling and the `automatically_fix`
   metadata. ✅

### Phase 11 – Suppression Justifications & Hygiene Hardening

1. **Suppression annotations** – extend the internal suppressions linter with
   a `suppression_valid:` marker, add CLI support for
   `--show-valid-suppressions`, and retrofit existing suppressions with
   full-sentence justifications.
2. **Hygiene upgrades** – expand the base `python-hygiene` tool to catch
   `__main__` blocks, blanket `except Exception:` handlers lacking inline
   rationale, and debugging imports (pdb/ipdb).
3. **PyQA hygiene overlay** – introduce a pyqa-scoped hygiene companion that
   flags `SystemExit`/`os._exit` usage outside entry points and stray
   `print`/`pprint` calls.
4. **Validation** – add targeted tests covering the new suppressions pathway
   and hygiene rules to prevent regressions.

### Phase 12 – Interface Realignment & SOLID Enforcement

1. **Audit & admit missteps (SRP)** – export `pyqa-interfaces` diagnostics,
   explicitly record current violations (direct concrete imports, accidental
   re-exports, interface modules containing implementation code) and assign
   ownership per domain so remediation tasks stay single-purpose.
2. **Purge concrete code from interfaces (DIP)** – remove interface modules that
   currently wrap or re-export implementations (`analysis_bootstrap`,
   `analysis_services`, `reporting`, `installers_dev`, `installers_update`,
   orchestrator hooks). Reinstate pure protocols/dataclasses inside
   `pyqa.interfaces.*` and relocate concrete helpers back to their runtime
   packages.
3. **Rebuild abstractions (ISP/LSP)** – create focused protocols for console
   access, orchestration selection, installers, and reporting adapters without
   embedding logic. Ensure interfaces expose only contracts while concrete
   modules register implementations via DI or factories.
4. **Refactor consumers (OCP)** – update CLI, orchestration, reporting, and
   runtime modules to depend on the rebuilt abstractions, add adapters where
   needed, reintroduce Google-style docstrings, and tighten typing using
   `Final`, `Literal`, and Protocol-based design.
5. **Documentation & validation (SOLID governance)** – refresh module docs and
   reorg narratives to describe the final interface boundaries, expand lint and
   pytest coverage, and run `./lint -n --only pyqa-interfaces` plus strict lint
   presets to guarantee the DIP-aligned architecture remains clean.

> **Backwards compatibility constraint:** The reorg does not preserve legacy
> import paths. Introducing backwards-compatibility shims or re-exports defeats
> the SOLID goals and is explicitly banned; all modules must consume the new
> interface seams directly.
> **Wrapper ban:** Interface modules may define protocols, data classes, and
> pure helper utilities only; wrapping or forwarding to concrete implementations
> (re-exports, adapter modules that call runtime code) is prohibited.
