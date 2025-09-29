# Catalog Tooling Overview

PyQA resolves every tool definition through a data-first catalog. The Python
code under `src/pyqa/tooling/` and `src/pyqa/tools/` provides the plumbing that
turns catalog JSON into executable actions used by the orchestrator. This file
summarises the moving pieces and is intended for contributors extending the
catalog or strategy layer.

## Key Modules

| Path                                 | Purpose                                                                                                                                                                                                                    |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/pyqa/tooling/loader.py`         | Loads strategy definitions, shared fragments, and tool definitions while validating them against the schemas in `tooling/schema/`. Produces `CatalogSnapshot` instances keyed by a checksum of the catalog contents.       |
| `src/pyqa/tooling/strategies.py`     | Houses all strategy factories referenced by the catalog (command builders, parser adapters, installers, etc.). Strategies are intentionally generic so that new behaviour can be expressed in JSON without editing Python. |
| `src/pyqa/tools/builtin_registry.py` | Materialises catalog definitions into runtime `Tool` objects, caching snapshots for reuse and wiring strategies into tool actions.                                                                                         |
| `src/pyqa/tools/catalog_metadata.py` | Convenience layer that exposes catalog information (options, suppressions, docs) to the rest of the CLI and config surfaces.                                                                                               |

## Catalog Lifecycle

1. **Validation & Snapshotting** – `ToolCatalogLoader` walks the catalog directories, validates JSON against the schemas, merges `_shared` fragments, and computes a checksum stored in `tooling/catalog/cache.json`.
2. **Materialisation** – `register_catalog_tools` converts validated definitions into `Tool` instances by instantiating referenced strategies (commands, parsers, installers).
3. **Execution** – The orchestrator (`src/pyqa/execution/orchestrator.py`) uses the registry to fetch tools for a run, executes actions in phase order, and feeds stdout/stderr into the configured parsers.

## Strategies

Strategies are JSON-defined references to Python factories. They keep runtime
code small and focused:

- **Command Strategies** build argument lists from catalog configuration and
  tool settings. Examples include `command_download_binary` for standalone
  binaries and `command_project_scanner` for language-aware scanners that need
  exclude/target planning.
- **Parser Strategies** encapsulate stdout/stderr parsing. `parser_json` wraps a
  transform callable, while `parser_json_diagnostics` maps JSON payloads onto
  `RawDiagnostic` objects declaratively.
- **Installer Strategies** run once per tool to ensure a runtime is available
  (e.g., downloading a binary release).

All strategies live under `tooling/catalog/strategies` and are validated by the
strategy schema before use.

## Shared Fragments

Files in `tooling/catalog/_shared/` act as reusable snippets (e.g. Python
defaults, runtime descriptors). Tool definitions can `extends` any fragment to
reduce duplication. Fragment data is merged before schema validation, so shared
content must also conform to `tool_definition.schema.json`.

## Cache and Checksums

`tooling/catalog/cache.json` stores the catalog checksum alongside a list of
files used to compute it. The loader compares this checksum to determine if the
catalog needs to be reloaded, speeding up repeated runs. Always regenerate the
checksum (using `ToolCatalogLoader.compute_checksum()`) whenever catalog files
change.

## Testing & Validation

- **Unit tests** – `tests/test_tooling_loader.py`, `tests/test_tool_catalog_registry.py`, and strategy-specific tests exercise the loader and strategy layer against the real catalog.
- **Author workflow** – After editing catalog JSON or strategies, run `uv run pytest` for the relevant tests and update the checksum. Schema validation failures will surface immediately during test collection.
- **Quick check** – Run `./lint --validate-schema` (or `uv run pyqa lint --validate-schema`) to load the catalog, report tool/strategy counts, and confirm the checksum without running the full test suite.

## Authoring Checklist

1. Update or add JSON under `tooling/catalog/…`.
2. Ensure any new configuration keys are documented in the schemas (`tool_definition` or `strategy_definition`).
3. Regenerate `tooling/catalog/cache.json` via `ToolCatalogLoader.compute_checksum()`.
4. Run `uv run pytest tests/test_tooling_loader.py tests/test_tool_catalog_registry.py` (or the full suite) before opening a PR.

Keeping these steps in sync ensures the catalog remains source-of-truth and the
Python runtime layer stays minimal.
