# Tool Module Restructuring Plan

## Completion Status

- Catalog schemas, language definitions, and strategy manifests now cover every
  tool with checksum-backed caching reused across orchestrator entry points.
- Runtime helpers (`catalog_metadata`, `tools.settings`, CLI builders) source
  suppressions, duplicates, and option schemas exclusively from the catalog.
- Legacy command classes are partially retired, but bespoke strategy
  implementations still embed tool-specific logic (e.g. Ruff, pylint,
  golangci-lint). Further generalisation is tracked under next steps.
- Documentation (`docs/tooling/TOOL_CATALOG_GUIDE.md`, `ref_docs/tool-schema.json`)
  reflects the catalog workflow and exported metadata.
- Full `uv run pytest` passes with the catalog registry as the sole execution
  path, demonstrating complete parity with the previous implementation.
- Installer helpers are re-exported directly from `pyqa.tools.builtin_helpers`,
  eliminating redundant wrappers.
- Strategy-focused tests assert command factories directly without
  `ToolAction` scaffolding.
- `pyqa config export-tools --check` now validates schema freshness for CI.
- Catalog metadata helpers memoise tool options to avoid redundant resolution.
- Tool documentation lives under `tooling/catalog/docs` and surfaces through
  catalog-driven `documentation` metadata consumed by CLI help panels.
- Generic download strategies replace bespoke `ensure_*` helpers; catalog
  definitions describe platform assets for actionlint, hadolint, and lualint.
- Phase-aware ordering now lives in `ToolRegistry`, derived entirely from
  catalog metadata.

## Guiding Principles

- **Single Responsibility (SRP):** Each artifact (JSON spec, loader, validation, runtime adapter) owns one well-defined concern.
- **Open/Closed (OCP):** Adding or modifying tool definitions should require editing data, not Python code.
- **Liskov Substitution (LSP):** Tool consumers operate against stable interfaces; any compliant tool schema instance can be injected without breaking callers.
- **Interface Segregation (ISP):** Separate read-only views (e.g., CLI summaries, runtime adapters) from authoring/validation utilities so consumers depend only on what they use.
- **Dependency Inversion (DIP):** High-level orchestration depends on abstractions (`ToolRegistry`, `ToolDefinition` protocol) while concrete parsers/loaders depend on JSON modules.

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

1. **Generalise Command Options**
   - Replace tool-specific builders (Ruff, Black, ESLint, golangci-lint, etc.)
     with catalog-driven option mappings so CLI flag wiring lives in JSON.
   - Introduce reusable command-option strategies (value/path/flag mappings)
     that mirror the `command_download_binary` option table.

2. **Catalog Defaults & Diagnostics**
   - Move linter default thresholds currently seeded in `Config.ensure(...)`
     (line lengths, pylint complexity, bandit severities) into shared catalog
     fragments or runtime metadata.
   - Relocate special-case suppression logic (`pylint` R0801/W0613/W0212
     handling in `execution.orchestrator`) into catalog `diagnostics`
     post-processors or suppression lists.

3. **Retire Legacy Helpers**
   - Port `pyqa.tools.builtin_commands_python` behaviour into strategies or
     catalog metadata (pylint plugin discovery, pyupgrade flags) and remove the
     module once callers migrate.

## Additional Opportunities

- Provide a generic `command_static` strategy in the catalog to cover gofmt,
  cargo fmt/clippy, mdformat, etc., instead of dedicated one-off wrappers.
- Surface pylint plugin auto-discovery as catalog metadata/strategy config so
  optional plugin enablement can be edited without touching Python.
