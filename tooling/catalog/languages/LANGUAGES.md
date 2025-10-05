<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Tool Definition Catalog Guide

Each directory under `tooling/catalog/languages/` groups tool definitions by
language or ecosystem (e.g. `python/`, `shell/`, `docker/`). Every JSON file
represents a single tool and adheres to `tool_definition.schema.json`.

## High-Level Structure

```json
{
  "schemaVersion": "1.0.0",
  "name": "ruff",
  "description": "Python linting via Ruff.",
  "languages": ["python"],
  "phase": "lint",
  "extends": ["python_defaults"],
  "runtime": { … },
  "actions": [ … ],
  "fileExtensions": [".py"],
  "documentation": { … }
}
```

### Common Sections

* **Metadata** – `name`, `description`, `languages`, `phase`, and optional
  `tags`, `before`, `after`. Use `extends` to merge shared fragments from
  `tooling/catalog/_shared/`.
* **Runtime** – Describes how the tool is executed (`type`, packages, binary
  downloads, installer configuration). This section is merged across fragments
  and validated by the schema.
* **Actions** – Array of executable actions (`lint`, `fix`, `format`, …). Each
  action references a strategy via the `command.strategy` field, optionally a
  parser, and exposes metadata such as `appendFiles`, `ignoreExit`, and
  `timeoutSeconds`.
* **Documentation** – Pointers to text/markdown files in `tooling/catalog/docs`
  surfaced by the CLI (`pyqa tool-info`).

### Actions and Strategies

Actions use strategies defined in `tooling/catalog/strategies`:

* `command_download_binary` – for tools that run a downloaded binary. Supply a
  `download` spec, optional `base`, and `options` section mapping settings to
  CLI flags.
* `command_project_scanner` – for project-based tools that derive targets from
  discovery metadata (Bandit, shfmt, tombi). Configure exclude/target plans and
  option mappings to match the tool’s CLI.
* Other strategies (`command_golangci_lint`, `command_pylint`, etc.) remain
  specialised but still take configuration via the `config` object.

Parsers are likewise strategy references (`parser_json_diagnostics`,
`parser_json`, `parser_text`). The schema keeps parser configuration flexible
while ensuring each strategy receives the correct payload.

### Shared Fragments

Files in `tooling/catalog/_shared` can be referenced via `extends`. They are
merged depth-first into the tool definition before validation. Use fragments to
store:

* Common suppressions or diagnostic mappings.
* Shared runtime information (e.g. Go or npm runtime blocks).
* Default options or documentation shared by multiple tools.

### Authoring Workflow

1. Copy an existing tool definition as a starting point or create a new file in
   the appropriate language directory.
2. Update metadata, runtime, and actions. Prefer referencing generic strategies
   to avoid code changes.
3. If new configuration keys are required, document them in the relevant schema
   and strategy docs.
4. Regenerate the catalog checksum (`ToolCatalogLoader.compute_checksum()`).
5. Run `uv run pytest tests/test_tooling_loader.py tests/test_tool_catalog_registry.py`
   to validate and materialise the tool.

### Conventions

* Use `schemaVersion: 1.0.0` for all files.
* Keep filenames aligned with the tool name (`ruff.json`, `bandit.json`).
* Store documentation fragments in `tooling/catalog/docs/` and reference them
  from the `documentation` block.
* When adding binary downloads, ensure the `targets` list covers supported
  platforms and includes `chmod`/`archive` information if needed.

By keeping tool definitions declarative and validated, adding a new tool or
updating existing behaviour becomes a matter of editing JSON rather than Python
code.
