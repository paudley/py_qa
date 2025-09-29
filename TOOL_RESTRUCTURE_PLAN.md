# Tool Module Restructuring Plan

## Completion Status

- Shared `command_option_map` strategy now drives every catalog action (Python
  helpers have been removed entirely); bespoke strategy modules were deleted
  to force pure catalog control.
- All tool JSON definitions have been updated to rely on option maps, but
  supporting helper utilities (`_require_string_sequence`, `_load_attribute`,
  `_build_field_spec`, catalog option transforms) still live outside the
  consolidated `strategies.py` module and need reinstatement after the module
  purge.
- `uv run pytest` is green again after shoring up catalog defaults: restored
  python-version flag parity for pylint/mypy/pyright, fixed pyupgrade flag
  duplication and double file appends, reintroduced cpplint recursive flag
  wiring, and made golangci-lint's `--enable-all` opt-out via setting.
- Catalog JSON now mirrors the legacy CLI surface for these tools; continue
  auditing remaining actions to ensure helper parity before deleting any
  residual shims.
- Pruned the obsolete `CommandBuilder` subclasses from
  `pyqa.tools.builtin_commands_python` and `pyqa.tools.builtin_commands_misc`,
  leaving only the shared helper functions consumed by the catalog strategies.
- Bandit now sources its default severity and confidence levels directly from
  catalog metadata (`defaultFrom`), reducing the bespoke fallback logic in
  command builders.
- Catalog defaults now cover TypeScript strict mode and lint warning budgets,
  wiring shared strictness/severity knobs directly into `tsc`, `stylelint`, and
  `eslint` without Python-side ensures.
- Mypy strict mode moved entirely into catalog metadata; default runs are
  "standard", with strict flags only emitted when strictness is explicitly
  requested (CLI `--strict` or sensitivity maximum).

## Guiding Principles

- **Single Responsibility (SRP):** Each artifact (JSON spec, loader, validation, runtime adapter) owns one well-defined concern.
- **Open/Closed (OCP):** Adding or modifying tool definitions should require editing data, not Python code.
- **Liskov Substitution (LSP):** Tool consumers operate against stable interfaces; any compliant tool schema instance can be injected without breaking callers.
- **Interface Segregation (ISP):** Separate read-only views (e.g., CLI summaries, runtime adapters) from authoring/validation utilities so consumers depend only on what they use.
- **Dependency Inversion (DIP):** High-level orchestration depends on abstractions (`ToolRegistry`, `ToolDefinition` protocol) while concrete parsers/loaders depend on JSON modules.

## Constraints & Guardrails

- Tests and production code must import modules identically; avoid modifying
  `sys.path` or other interpreter-level import hooks.
- Execute all verification commands with `uv run …` to ensure the resolved
  environment matches production expectations.
- Focus implementation changes within `src/`; Python code under `tooling/`
  remains off-limits for runtime helpers.
- Defer compatibility shims—complete catalog migrations first, then backfill
  tests and adapters once new wiring is stable.

## Code Requirements

- All code must be strongly typed and avoid the use of Any, object, or optional Nones.
- All functions regardless of size must be documented using the Google Documenation Style
- Helper functions should be robust and comprehensive. They should be designed so that other functions can use them and be general where possible.

## Target Architecture Overview

1. **Data-first Tool Catalog**

   - Authoritative catalog stored as JSON files grouped by language/utility under `tooling/catalog/{language|utility}`.
   - JSON Schema (`tooling/schema/tool_definition.schema.json`) enforces structure.
   - Each JSON captures:
     - Metadata: name, description, language tags, default-enabled.
     - Executables: commands (lint/fix/info), arguments, environment, timeout defaults.
     - Parsers: fully-qualified parser ID and configuration hooks.
     - Suppressions: default test suppressions, general suppressions, cross-tool duplicates.
     - Configuration options: rich metadata for CLI/JSON config (type, default, CLI flag mapping).
     - Runtime requirements: binaries, version strategies (pinned/default range), download URLs, optional installation scripts.
     - Diagnostics post-processing: dedupe hints, severity mappings.
     - Execution ordering: `phase` field (e.g., `lint`, `format`, `analysis`), optional `before`/`after` lists for intra-phase ordering; alphabetical fallback within phase.

1. **Strategy Catalog**

   - Secondary JSON catalog (`tooling/catalog/strategies`) enumerates reusable execution/parsing components.
   - Each strategy entry defines an identifier, type (command runner, parser, formatter, post-processor), implementation import path, and expected configuration keys.
   - JSON Schema (`tooling/schema/strategy.schema.json`) validates entries to guarantee callable availability and config structure.
   - Tool definitions reference strategies by ID; no tool-specific wiring remains in Python.

1. **Loader & Validation Layer**

   - `tooling/loader.py` reads catalog, validates against JSON Schema via `jsonschema`.
   - Normalizes paths, expands inheritance (allow shared fragments in `_common.json`).
   - Produces immutable `ToolDefinition` dataclasses.

1. **Registry Revamp**

   - `pyqa.tools.registry.ToolRegistry` loads definitions exclusively through loader.
   - Registry caching keyed by catalog checksum.
   - Applies ordering rules derived from `phase` + `before`/`after` metadata (topological sort, alphabetical fallback).
   - Provides query APIs (`tools_for_language`, `tool_by_name`) returning structured definitions.

1. **Adapters / Facades**

   - Loader instantiates strategy objects by resolving implementation paths declared in the strategy catalog.
   - Command builders, parser adapters, and environment preparers become thin wrappers that dispatch through strategy interfaces.
   - New strategies can be introduced by adding catalog entries without touching orchestrator code.

1. **Configuration Integration**

   - CLI/config builder reads tool option metadata from catalog (no hard-coded options in Python).
   - Quality/suppression defaults pulled from catalog at build time.
   - Duplicate-detection hints centralized in catalog.

1. **Testing/Docs Automation**

   - JSON Schema tests: validate catalog + ensure coverage of required fields.
   - Snapshot tests for generated `ToolDefinition` objects.
   - Regenerate tool schema docs from catalog metadata.

## Work Breakdown Structure

1. **Foundational Schema Work**

   - Draft `tool_definition.schema.json` with modular references (commands, suppressions, options).
   - Add CI step to validate catalog against schema.

1. **Catalog Authoring**

   - Migrate existing tool information into language/utility JSON files.
   - Introduce `_shared` fragments for common npm/python/go runtime requirements.
   - Ensure every tool’s suppressions/duplicate hints move from Python to JSON.

1. **Strategy Catalog Implementation**

   - Define `strategy_definition.schema.json` with enumerated types.
   - Implement loader for strategy catalog, including import-path validation and friendly diagnostics.
   - Seed catalog with existing shared strategies (e.g., npm runner, Python JSON parser, typer command glue).

1. **Loader Implementation**

   - Build `ToolDefinition` dataclasses + factories.
   - Implement loader with caching, deep-merge of shared fragments, and schema validation.
   - Provide diagnostics for missing executables/parse adapters.

1. **Registry & Runtime Integration**

   - Refactor `pyqa.tools.registry` to consume loader.
   - Replace bespoke command classes with generic strategy dispatch resolved from catalog.
   - Adjust environment installers to use runtime metadata from catalog.

1. **Configuration & Reporting Alignment**

   - Remove hard-coded tool settings from `Config`/`config_loader`; replace with catalog-driven population.
   - Update advice/dedup modules to read cross-tool duplicate mappings from catalog.

1. **Test & Doc Refresh**

   - Add tests for loader + registry; update existing tool tests to assert catalog-driven behavior.
   - Regenerate tool schema documentation from catalog (extend `pyqa config export-tools`).
   - Document authoring workflow in `docs/tooling/TOOL_CATALOG_GUIDE.md`.

1. **Catalog Parity Verification**

   - Audit every legacy tool and confirm an equivalent catalog definition exists with identical commands, runtime defaults, suppressions, and installers.
   - Migrate any remaining Python-only metadata (version constants, runtime arguments, environment preparation) into JSON fragments or strategy config.
   - Run the full pytest suite and integration smoke checks with catalog-backed registry enabled to prove parity.

1. **Legacy Registry Retirement**

   - Flip the default configuration to use catalog-backed tools, removing feature-flag fallbacks.
   - Delete legacy registry helpers, command classes, and constants; ensure CLI/docs/tests reference only catalog-driven behaviour.
   - Provide migration notes for downstream consumers, highlighting any removed imports or renamed APIs.

1. **Strategy Simplification**

   - Refactor remaining `_FooCommand` classes into reusable strategy helpers or data-driven templates.
   - Capture default flag sets and environment variables in catalog metadata so Python code only applies parameterised transforms.
   - Generalise installer strategies (e.g. binary downloads, cargo installs) to eliminate bespoke helper functions.

1. **Metadata Consumers**

   - Extend catalog metadata helpers to expose runtime info, option schemas, and installer requirements.
   - Update CLI/export commands to rely on these helpers instead of bespoke JSON loading.

1. **Documentation & Automation**

   - Generate reference docs (tool list, installer table, runtime matrix) directly from the catalog.
   - Add tests ensuring catalog tool coverage aligns with CLI/doctor/tool-info suites.
   - Provide contributor guidance for adding new strategies and installer types.

## Migration Strategy

1. **Parallel Loader Prototype**: Build loader reading existing Python definitions to JSON to verify schema.
1. **Incremental Catalog Migration**: Move tools language by language, keeping legacy Python definitions until parity achieved.
1. **Feature Flag**: Add config flag to toggle catalog-backed registry; default off until complete.
1. **Parity Gate**: Confirm every tool (100% coverage) is defined in the catalog with matching behaviour by running the full test matrix using catalog-backed registry exclusively.
1. **Cutover**: Switch registry to catalog by default, remove the feature flag, and excise legacy registry initialization paths.
1. **Cleanup**: Delete old `builtin_commands_*` definitions, drop version constants (e.g. `HADOLINT_VERSION_DEFAULT`), update docs/CLI help, and remove deprecated suppressions.

## Risk Mitigation

- **Schema Drift**: version the schema; embed `schemaVersion` in each JSON file.
- **Performance**: cache loader output keyed by hash of catalog directory.
- **Backwards Compatibility**: maintain legacy option names via `aliases` array in JSON until consumers migrate.
- **Extensibility**: allow experimental tool definitions under `tooling/catalog/experimental` gated by feature flag.

## Success Criteria

- All tool metadata (commands, suppressions, options) lives in JSON catalog validated by schema.
- Registry/CLI build pipelines consume catalog without Python edits for new tools.
- Tests & docs reflect catalog-driven approach; quality checks pass with no “Unknown tool” warnings.
- Legacy registry code paths are removed; all runtime behaviour (including installers and defaults) resolves from catalog metadata with no loss of tool coverage.

## Current Focus & Next Steps

1. **Finish Option Map Migration**
   - Every tool now references `command_option_map`; focus shifts to policing
     helper coverage and closing parity gaps.
   - Restore shared helpers required by the consolidated strategy module
     (`_load_attribute`, `_build_field_spec`, `_require_string_sequence`,
     parser normalisers) so catalog option wiring can execute.
   - Reconcile behavioural regressions highlighted by the failing tests
     (pylint defaults/plugins, prettier/sqlfluff path handling, remark output
     paths, etc.) before removing the temporary skips.

2. **Externalise Defaults & Diagnostics**
   - Relocate hard-coded defaults from `Config.ensure(...)` and
     `_resolve_default_reference` into catalog fragments or `defaultFrom`
     aliases.
   - Surface pylint suppression/diagnostic tweaks in catalog metadata or
     dedicated post-processing strategies.
   - Capture python-version derived flags (pyupgrade, target tags) as reusable
     strategy transforms configurable via JSON.

3. **Testing & CLI Wiring**
   - Once migrations stabilise, update tests to exercise catalog lookups rather
     than importing legacy builders directly.
   - Ensure CLI entry points initialise registries explicitly with the catalog
     data path (no implicit side effects in `pyqa/__init__`).
  - Execute `uv run pytest` to re-baseline the suite after the new wiring is in
     place and address any fixture updates in a dedicated pass.

## Additional Opportunities

- Provide a generic `command_static` strategy in the catalog to cover gofmt,
  cargo fmt/clippy, mdformat, etc., instead of dedicated one-off wrappers.
- Surface pylint plugin auto-discovery as catalog metadata/strategy config so
  optional plugin enablement can be edited without touching Python.
