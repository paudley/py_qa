# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

# pyqa Tooling Specification

`pyqa-tooling-spec` packages the catalog models, loader, and JSON schemas used
by `pyqa` so that external tooling can consume the specification without
depending on the rest of the runtime. The distribution includes:

* immutable model definitions for tools, strategies, documentation, options,
  and fragments (`tooling_spec.catalog.model_*`),
* a schema-aware loader capable of materialising catalog snapshots from disk,
  complete with entry-point based plugin support, and
* the canonical strategy/tool schema documents under `schema/catalog_schema/`.

## Quick start

```python
from pathlib import Path

from tooling_spec.catalog import ToolCatalogLoader

catalog_root = Path("tooling/catalog")
schema_root = Path("tooling/schema")
snapshot = ToolCatalogLoader(catalog_root, schema_root=schema_root).load_snapshot()

for tool in snapshot.tools:
    print(tool.name, tool.to_dict()["actions"])
```

Plugins can extend the catalog by exposing callables via the
`pyqa.catalog.plugins` entry-point group. Each factory receives a
`CatalogPluginContext` instance and returns a `CatalogContribution` enumerating
additional tools, strategies, or fragments.

Refer to `CHANGELOG.md` for release notes and migration guidance.
