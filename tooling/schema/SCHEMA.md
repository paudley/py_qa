<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Catalog Schema Overview

The files in `tooling/schema/` define the JSON Schema documents that validate
all catalog entries before they are loaded into the registry. The schemas are
consumed by `ToolCatalogLoader` during test and runtime validation and can also
be used directly with any JSON Schema tooling when authoring new catalog
content.

## Files

| File                              | Purpose                                                                                             |
| --------------------------------- | --------------------------------------------------------------------------------------------------- |
| `tool_definition.schema.json`     | Validates tool definitions located under `tooling/catalog/languages/…` as well as shared fragments. |
| `strategy_definition.schema.json` | Validates reusable strategy definitions stored under `tooling/catalog/strategies/`.                 |

Both schemas are draft 2020-12 JSON Schema documents and share a `schemaVersion`
field that is currently pinned to `1.0.0`.

## Tool Definition Schema

Tool definitions describe a single linter/formatter/utility and are grouped by
language (or utility class) inside `tooling/catalog/languages`. The schema
captures the following high level areas:

* **Metadata** – tool name, description, language tags, default enablement,
  automatic fix behaviour (`automatically_fix`), and phase ordering (`phase`,
  `before`, `after`).
* **Runtime** – describes how the tool is executed. This can represent Python
  packages, npm packages, Go modules, standalone binaries, etc. Runtime
  sections optionally include an `install` block that references an installer
  strategy (such as `installer_download_artifact`).
* **Actions** – every executable entry point a tool exposes (e.g. `lint`, `fix`,
  `check`). Each action references a command strategy, an optional parser, and
  metadata such as appended files, exit-code handling, and timeouts. The new
  `exitCodes` block lets authors categorise exit statuses into success,
  diagnostic, and tool-failure buckets so the orchestrator can distinguish
  between operational failures and tools that merely reported issues.
* **Diagnostics** – severity mapping and dedupe hints used by the orchestrator
  to normalise diagnostics from the tool.
* **Suppressions** – default suppressions for tests/general usage along with
  duplicate tool hints.
* **Options & Documentation** – strongly typed option metadata exposed through
  CLI/config APIs and paths to documentation fragments rendered by the CLI.

### Strategy-specific Command Validation

The schema now contains command-specific validation for the new generic
strategies:

* `command_download_binary` – ensures `download` targets, optional base
  arguments, option mappings (including `joinWith`, `default`, `literalValues`),
  and optional `targets` selector are correctly typed.
* `command_project_scanner` – validates project-aware scanners that utilise
  exclude plans, target planning, and option mappings.

Installer configuration is similarly constrained for
`installer_download_artifact` so that download specs are validated uniformly.

### Download Specifications

Reusable download metadata is defined through `DownloadSpec` and
`DownloadTarget` schemas. These structures are referenced by the command and
installer schemas and guarantee that authoring catalog entries for binary tools
is consistent (supporting `os`/`arch` targeting, optional archives, filenames,
and chmod instructions).

## Strategy Definition Schema

Strategy definitions live under `tooling/catalog/strategies` and provide the
registry with reusable command/parser/post-processing behaviour. Each strategy
entry includes:

* `id`, `type`, and `implementation` – these must match the callable exported
  from `pyqa.catalog.strategies`.
* `config` – a description of the configuration keys that tool JSON files may
  supply when referencing the strategy. While the schema keeps this section
  deliberately open (to avoid duplicating every possible field), it ensures at
  minimum that types are declared and that required keys are called out.

## Validation Workflow

1. `ToolCatalogLoader` loads strategy definitions first and validates every JSON
   document against `strategy_definition.schema.json`.
2. Tool definitions and fragments are loaded next, validated against
   `tool_definition.schema.json`, and merged with `_shared` fragments.
3. A snapshot containing the checksum and validated data structures is produced
   for use by the registry.

Authors can run `uv run pytest tests/test_tooling_loader.py` to exercise schema
validation locally, or use external JSON Schema tooling with these documents to
validate changes before submitting PRs.
