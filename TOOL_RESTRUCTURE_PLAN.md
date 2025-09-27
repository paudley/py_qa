# Tool Module Restructuring Plan

## Guiding Principles
- **Single Responsibility (SRP):** Each artifact (JSON spec, loader, validation, runtime adapter) owns one well-defined concern.
- **Open/Closed (OCP):** Adding or modifying tool definitions should require editing data, not Python code.
- **Liskov Substitution (LSP):** Tool consumers operate against stable interfaces; any compliant tool schema instance can be injected without breaking callers.
- **Interface Segregation (ISP):** Separate read-only views (e.g., CLI summaries, runtime adapters) from authoring/validation utilities so consumers depend only on what they use.
- **Dependency Inversion (DIP):** High-level orchestration depends on abstractions (`ToolRegistry`, `ToolDefinition` protocol) while concrete parsers/loaders depend on JSON modules.

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

2. **Strategy Catalog**
   - Secondary JSON catalog (`tooling/catalog/strategies`) enumerates reusable execution/parsing components.
   - Each strategy entry defines an identifier, type (command runner, parser, formatter, post-processor), implementation import path, and expected configuration keys.
   - JSON Schema (`tooling/schema/strategy.schema.json`) validates entries to guarantee callable availability and config structure.
   - Tool definitions reference strategies by ID; no tool-specific wiring remains in Python.

3. **Loader & Validation Layer**
   - `tooling/loader.py` reads catalog, validates against JSON Schema via `jsonschema`.
   - Normalizes paths, expands inheritance (allow shared fragments in `_common.json`).
   - Produces immutable `ToolDefinition` dataclasses.

4. **Registry Revamp**
   - `pyqa.tools.registry.ToolRegistry` loads definitions exclusively through loader.
   - Registry caching keyed by catalog checksum.
   - Applies ordering rules derived from `phase` + `before`/`after` metadata (topological sort, alphabetical fallback).
   - Provides query APIs (`tools_for_language`, `tool_by_name`) returning structured definitions.

5. **Adapters / Facades**
   - Loader instantiates strategy objects by resolving implementation paths declared in the strategy catalog.
   - Command builders, parser adapters, and environment preparers become thin wrappers that dispatch through strategy interfaces.
   - New strategies can be introduced by adding catalog entries without touching orchestrator code.

6. **Configuration Integration**
   - CLI/config builder reads tool option metadata from catalog (no hard-coded options in Python).
   - Quality/suppression defaults pulled from catalog at build time.
   - Duplicate-detection hints centralized in catalog.

7. **Testing/Docs Automation**
   - JSON Schema tests: validate catalog + ensure coverage of required fields.
   - Snapshot tests for generated `ToolDefinition` objects.
   - Regenerate tool schema docs from catalog metadata.

## Work Breakdown Structure
1. **Foundational Schema Work**
   - Draft `tool_definition.schema.json` with modular references (commands, suppressions, options).
   - Add CI step to validate catalog against schema.

2. **Catalog Authoring**
   - Migrate existing tool information into language/utility JSON files.
   - Introduce `_shared` fragments for common npm/python/go runtime requirements.
   - Ensure every tool’s suppressions/duplicate hints move from Python to JSON.

3. **Strategy Catalog Implementation**
   - Define `strategy_definition.schema.json` with enumerated types.
   - Implement loader for strategy catalog, including import-path validation and friendly diagnostics.
   - Seed catalog with existing shared strategies (e.g., npm runner, Python JSON parser, typer command glue).

4. **Loader Implementation**
   - Build `ToolDefinition` dataclasses + factories.
   - Implement loader with caching, deep-merge of shared fragments, and schema validation.
   - Provide diagnostics for missing executables/parse adapters.

5. **Registry & Runtime Integration**
   - Refactor `pyqa.tools.registry` to consume loader.
   - Replace bespoke command classes with generic strategy dispatch resolved from catalog.
   - Adjust environment installers to use runtime metadata from catalog.

6. **Configuration & Reporting Alignment**
   - Remove hard-coded tool settings from `Config`/`config_loader`; replace with catalog-driven population.
   - Update advice/dedup modules to read cross-tool duplicate mappings from catalog.

7. **Test & Doc Refresh**
   - Add tests for loader + registry; update existing tool tests to assert catalog-driven behavior.
   - Regenerate tool schema documentation from catalog (extend `pyqa config export-tools`).
   - Document authoring workflow in `docs/tooling/TOOL_CATALOG_GUIDE.md`.

## Migration Strategy
1. **Parallel Loader Prototype**: Build loader reading existing Python definitions to JSON to verify schema.
2. **Incremental Catalog Migration**: Move tools language by language, keeping legacy Python definitions until parity achieved.
3. **Feature Flag**: Add config flag to toggle catalog-backed registry; default off until complete.
4. **Cutover**: Once catalog covers all tools and tests pass, switch registry to catalog by default and remove legacy code.
5. **Cleanup**: Delete old `builtin_commands_*` definitions, update docs, remove deprecated suppressions.

## Risk Mitigation
- **Schema Drift**: version the schema; embed `schemaVersion` in each JSON file.
- **Performance**: cache loader output keyed by hash of catalog directory.
- **Backwards Compatibility**: maintain legacy option names via `aliases` array in JSON until consumers migrate.
- **Extensibility**: allow experimental tool definitions under `tooling/catalog/experimental` gated by feature flag.

## Success Criteria
- All tool metadata (commands, suppressions, options) lives in JSON catalog validated by schema.
- Registry/CLI build pipelines consume catalog without Python edits for new tools.
- Tests & docs reflect catalog-driven approach; quality checks pass with no “Unknown tool” warnings.
