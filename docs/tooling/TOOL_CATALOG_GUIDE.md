<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Tool Catalog Authoring Guide

The PyQA tool registry is now sourced from JSON metadata under `tooling/catalog`
and shipped as part of the standalone `tooling_spec` Python package (see
`src/tooling_spec/`). The runtime consumes those models via thin wrappers in
`pyqa.catalog` so external tooling can parse the same data without depending on
the CLI implementation. This guide summarises the shape of the catalog and how
the runtime consumes it.

## Structure

Each tool definition lives in `tooling/catalog/languages/<language>/<tool>.json`.
Common fragments are kept under `tooling/catalog/_shared/` and referenced via the
`extends` array. Strategy building blocks (command builders, parsers, installers,
post-processors) live in `tooling/catalog/strategies/` and are referenced by ID.
The schema for both collections resides in `tooling/schema/`.

## Key Fields

* `suppressions.tests` collects regex patterns automatically applied to test
  files. They are surfaced through `catalog_test_suppressions()` and feed
  directly into `flatten_test_suppressions()` for CLI defaults.
* `suppressions.general` holds regex patterns that are merged into
  `DEFAULT_TOOL_FILTERS`, allowing noisy diagnostics (such as `.github` files) to
  be filtered before normalisation.
* `suppressions.duplicates` lists other tools whose diagnostics should be
  considered duplicates of the current tool. These entries drive
  `catalog_duplicate_preference()` which in turn seeds `Config.dedupe.dedupe_prefer`.
* `diagnostics.dedupe.duplicateHints` provides a comma-separated list of rule
  codes that should trigger duplicate-advice messaging. They are exposed through
  `catalog_duplicate_hint_codes()` and consumed by
  `pyqa.reporting.advice.builder`.
* `tags` can annotate environment requirements such as `requires-cargo` or
  `requires-luarocks`; the runtime registry downgrades `defaultEnabled` to `false`
  automatically when the host system lacks the required tooling.
* `options` enumerates tool-specific configuration knobs. The loader exposes
  these as `OptionDefinition` objects for future config builders.
* `actions[].exitCodes` categorises exit statuses into success, diagnostic, and
  tool\_failure sets. This allows runtime code to surface tool crashes while
  treating ordinary diagnostics as expected failures.

## Runtime Integration

* **Registry caching** – `register_catalog_tools()` now consults a checksum-based
  cache so repeated invocations avoid re-parsing JSON when nothing changed.
* **Configuration defaults** – `config_builder` merges catalog suppressions into
  tool filter defaults, and `Config.apply_shared_defaults` incorporates catalog
  duplicate preferences.
* **Advice generation** – duplicate hint codes from the catalog replace the
  hard-coded lists previously shipped in `reporting.advice`.

## Validation & Testing

* `ToolCatalogLoader` validates definitions against
  `tooling/schema/tool_definition.schema.json` during test runs.
* `tests/test_catalog_metadata.py` exercises the metadata helpers to ensure
  suppressions, duplicates, and hint codes remain in sync with the catalog.
* `tests/test_tool_catalog_registry.py` loads the real catalog and verifies that
  materialised tools behave as expected.

## Updating the Catalog

1. Modify or add JSON documents under `tooling/catalog`. Reuse shared fragments
   where possible to minimise duplication.
2. Run `pytest tests/test_catalog_metadata.py` to confirm metadata helpers still
   behave correctly.
3. Update `tooling/catalog/cache.json` by computing the new checksum via
   `ToolCatalogLoader.compute_checksum()` (or the helper used in the tests).
4. Commit both the JSON changes and the updated checksum together to keep the
   cache coherent.

Authoring new tools should rarely require Python changes; ensure any bespoke
behaviour is captured as strategies within the catalog instead.
