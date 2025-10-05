<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Shared Catalog Fragments

The `_shared` directory contains reusable JSON fragments that can be merged into
multiple tool definitions. Fragments help avoid duplication by capturing
runtime defaults, suppressions, or any common blocks that should apply across
many tools.

## Naming & Loading

* Filenames must start with an underscore (`_python_defaults.json`).
* Fragments follow the same schema as tool definitions (`tool_definition.schema.json`).
* Tools reference fragments via the `extends` array. Entries are merged
  depth-first in the order they appear.

Example:

```json
{
  "extends": ["python_defaults"],
  "runtime": { "type": "python", "package": "mypackage" }
}
```

## Existing Fragments

| Fragment                | Purpose                                                   |
| ----------------------- | --------------------------------------------------------- |
| `_python_defaults.json` | Shared diagnostics/suppression defaults for Python tools. |
| `_go_runtime.json`      | Reusable Go runtime block for Go-based utilities.         |
| `_npm_runtime.json`     | Reusable npm runtime block for JavaScript-based tools.    |

## Guidelines for New Fragments

1. Keep fragment scope focused (e.g., runtime defaults for a single ecosystem,
   shared suppressions for a suite of tools).
2. Avoid tool-specific configuration—those belong in individual tool files.
3. Validate fragments with `uv run pytest tests/test_tooling_loader.py` to catch
   schema issues.
4. Update this document when adding or renaming fragments to keep the catalog
   discoverable.

Fragments are merged prior to schema validation, so any conflicting fields will
be overwritten by the tool definition itself. Use this behaviour to provide
sensible defaults while still allowing individual tools to fine-tune settings.
