<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Phase 13 – Generic Dunder Guidance

## Objective

Extend pyqa's linting stack to provide a configurable, tree-sitter–powered analyser that recommends or enforces dunder-method implementations for classes behaving like value types. The goal is to generalise beyond internal helpers while retaining the ability to enforce pyqa-specific contracts.

## Key Deliverables

1. **Tree-sitter Heuristics**

   * Parse Python class definitions to detect common value-type patterns (dataclasses, slots-based containers, enums, tuple-like wrappers).
   * For each detected pattern, recommend or enforce useful dunder methods:
     * `__len__`, `__iter__`, `__contains__` for iterable containers.
     * `__bool__` for presence checks.
     * `__eq__`, `__hash__`, `__repr__`, `__str__` for identity/value semantics.
     * `__slots__`/dataclass field coverage to ensure memory/layout control where appropriate.
   * Allow configuration of recommended combinations (e.g., equality implies hashing, iterability implies length).

2. **Configuration & Suppression Support**

   * Expose configuration via `pyproject.toml` (e.g., class glob pattern → required dunders, optional allow/deny lists).
   * Integrate with the `SuppressionRegistry` so lint findings honour `suppression_valid:` comments (e.g., `suppression_valid: lint=generic-value-types reason...`).

3. **CLI & Documentation**

   * Introduce a new lint flag (`--check-value-types-general`) referencing the generic analyser while keeping `pyqa-value-types` for internal contracts.
   * Document heuristics, recommended dunder pairings, configuration schema, and suppression formats in lint CLI docs.

## Risks & Mitigations

* **False positives**: start with opt-in configuration and provide suppression support; ship conservative defaults.
* **Performance**: reuse existing tree-sitter integration with incremental parsing to limit overhead.
* **Introspection scope**: begin with Python; design interfaces so other languages can plug in their own heuristics later.

## Timeline

Estimated one sprint with the following milestones:

1. Prototype heuristics + config schema.
2. Integrate suppression and CLI exposure.
3. Author documentation and add regression tests.

## Implementation Summary

* Added `generic-value-types` internal linter (`src/pyqa/linting/generic_value_types.py`) that parses Python sources via Tree-sitter and emits diagnostics for missing dunders. Heuristics capture dataclass and slots-based value semantics, iterable traits (`__iter__`, ABC inheritance), and mapping/sequence inheritance to drive recommendations.
* Introduced `GenericValueTypesConfig` with rule/implication models in `pyqa.config`. Rules support globbed class patterns, trait filters, required/recommended method lists, and per-rule allow lists. Implications wire trigger → requirement relationships with selectable severity (`error` vs `warning`). Defaults enforce conservative combinations (`__iter__` → `__len__` + `__contains__`, `__len__` → `__bool__`, `__eq__` → `__hash__` alongside display helpers).
* Updated CLI (`--check-value-types-general`) and the lint registry so the new linter can be toggled independently of the pyqa-specific value-type checks. Normal mode enables it automatically alongside other internal linters.
* Configuration is exposed under `[tool.pyqa.generic_value_types]`; TOML arrays hydrate `rules` and `implications` with the same schema used in tests. All findings honour `suppression_valid` justifications through the shared `SuppressionRegistry`.
* Authored regression coverage (`tests/linting/test_generic_value_types.py`) validating diagnostics, suppression semantics, and overall wiring. Tests skip gracefully when Tree-sitter bindings are absent.

## Configuration Primer

```toml
[tool.pyqa.generic_value_types]
enabled = true

[[tool.pyqa.generic_value_types.rules]]
pattern = "acme.*.Payload"
traits = ["iterable", "value"]
require = ["__len__", "__contains__"]
recommend = ["__repr__"]
allow_missing = ["__contains__"]

[[tool.pyqa.generic_value_types.implications]]
trigger = "method:__len__"
require = ["__bool__"]
severity = "warning"
```

Recognised traits include `dataclass`, `dataclass-frozen`, `slots`, `enum`, `iterable`, `sequence`, `mapping`, `value`, `iter`, `len`, `bool`, `contains`, `eq`, `hash`, `repr`, `str`.

## CLI Usage

```bash
pyqa lint --check-value-types-general path/to/package
```

Diagnostics emit as `generic-value-types:missing-required` (error) or `generic-value-types:missing-recommended` (warning), enabling downstream filtering.

## Future Enhancements

* **Numeric protocols** – Extend trait detection to recognise arithmetic dunders (`__add__`, `__sub__`, `__mul__`, `__truediv__`, `__neg__`) and surface recommendations for complementary methods (`__radd__`, `__iadd__`, `__hash__` parity when equality remains value-based). Heuristics can leverage Tree-sitter method discovery plus ABC inheritance (e.g., `numbers.Number`) to mark classes as numeric-like. Config additions would introduce `numeric` and `arithmetic` traits so rules can require `__float__`, `__int__`, or reversible operations when projects opt in.
* **Trait bundles** – Offer optional config macros (e.g., `bundle = "numeric"`) translating to a curated list of recommended dunders. Bundles simplify adoption while preserving fine-grained overrides for advanced teams.
