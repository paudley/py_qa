<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Strategy Catalog Guide

The files in this directory define reusable strategies that tools reference in
`tooling/catalog/languages/…`. Strategies keep behaviour declarative by mapping
catalog configuration to factories exported from `pyqa.catalog.strategies`.

Each strategy file is a JSON document with the following top-level structure:

```json
{
  "schemaVersion": "1.0.0",
  "id": "command_download_binary",
  "type": "command",
  "description": "Optional human readable summary.",
  "implementation": "pyqa.catalog.strategies.command_download_binary",
  "config": {}
}
```

* `schemaVersion` – schema version of the strategy catalog (currently `1.0.0`).
* `id` – globally unique identifier referenced by tool definitions.
* `type` – one of `command`, `parser`, `formatter`, `postProcessor`, or
  `installer`.
* `implementation` – fully qualified Python import path pointing at the factory
  in `pyqa.catalog.strategies`.
* `config` – description of the configuration keys a tool may supply when using
  the strategy. Keys include `type`, `required`, and optional `description` to
  aid catalog authors.

## Common Strategies

### `command_download_binary`

Downloads a platform-specific binary and builds an argument list using option
mappings and optional target selection. Key config values supported by the
strategy/schema:

* `version` (string, optional) – override the version passed to the download helper.
* `download` (object, required) – describes available assets (`name`,
  `cacheSubdir`, `targets`).
* `base` (array) – static arguments; use `${binary}` to inject the downloaded
  binary path.
* `binaryPlaceholder` (string) – change the token replaced by the binary path.
* `options` (array) – option mappings that translate tool settings into flags.
  Supported mapping fields: `setting`, `type` (`value`, `path`, `args`, `flag`,
  `repeatFlag`), `flag`, `negateFlag`, `joinWith`, `literalValues`, `default`.
* `targets` (object) – optional file selection rules (`suffixes`, `contains`,
  `pathMustInclude`, `fallbackDirectory`, `defaultToRoot`).

### `command_project_scanner`

Captures scanners that derive targets from project metadata (discovery roots,
explicit files, user provided paths) and need exclude handling.

* `base` (array, required) – command prefix.
* `options` (array) – same option mapping structure as above.
* `exclude` – configuration for exclusion lists (settings names, whether to
  include discovery excludes, CLI flag/separator).
* `targets` – planning for target arguments (settings, fallback directories,
  optional prefix, and whether to include discovery roots/explicit files).

### `parser_json_diagnostics`

Maps JSON payloads to `RawDiagnostic` objects via declarative path configuration:
`path`, `inputFormat`, and `mappings` (each mapping may use `path`, `value`,
`map`, `default`).

### `installer_download_artifact`

Ensures a downloaded artifact exists in the cache before tool execution.
Configuration mirrors `command_download_binary`’s `download` block and accepts
optional `version`/`contextLabel` overrides.

## Adding a New Strategy

1. Implement the corresponding factory in `pyqa.catalog.strategies` and export it
   via `__all__`.
2. Create a JSON descriptor in this directory using the structure above.
3. Describe any configuration keys in the `config` object to help authors and to
   support validation tooling.
4. Update `tooling/schema/strategy_definition.schema.json` if new concepts are
   introduced that should be enforced globally.
5. Add tests that exercise the new strategy (e.g. under `tests/`), referencing it
   through the catalog to ensure end-to-end coverage.

## Tips for Catalog Authors

* Strategy files are validated during test runs; schema violations will fail
  early before the registry loads.
* Keep descriptions up to date—CLI commands such as `pyqa tool-info` surface
  strategy-derived metadata when debugging catalog issues.
* Treat strategy configuration as the public contract: once multiple tools rely
  on a field it should be documented here and in `SCHEMA.md` to avoid regressions.
