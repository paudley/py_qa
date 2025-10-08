<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Phase 9 – DI & Interface Enforcement

## Objectives

* Encode dependency-inversion and interface-first rules as executable quality
  gates so regressions are blocked automatically.
* Ensure all runtime modules depend on declared interfaces rather than concrete
  implementations except at composition roots.
* Detect direct instantiation of banned classes (e.g., `TreeSitterContextResolver`)
  outside their owning packages and surface actionable diagnostics.

## Guiding Constraints

* Checks must run as part of `./lint -n` and the CI job that mirrors it.
* Rules should favour static analysis (AST/graph) but may fall back to targeted
  runtime inspection when a static approach is impractical.
* Violations must reference the architectural principle they break and recommend
  the appropriate interface/registration seam.
* `pyqa.interfaces` remains the single source of truth for allowable protocols.
* Composition roots (`core/runtime/di.py`, package-level `bootstrap.py`) are the
  only modules permitted to import concrete implementations alongside
  interfaces.
* Large modules should remain single-purpose; size/complexity thresholds trigger
  review unless the module is explicitly allow-listed.

## Deliverables

1. **Interface Compliance Linter** – new internal linter enforcing direct imports
   from `pyqa.interfaces.*` for orchestration/reporting/platform modules.
2. **DI Construction Guard** – lint that flags manual construction of service
   implementations outside approved factories.
3. **Composition Root Audit** – architectural test asserting only approved
   modules register services.
4. **Documentation Updates** – extend `SOLID_CLI.md` and a new `docs/reorg/PHASE9.md`
   (this file) detailing rules and remediation steps.
5. **Module Pattern Docs** – require an uppercase snake-case `{MODULE}.md`
   companion inside every package directory (e.g., `CLI.md`,
   `CONSOLE_MODELS.md`) capturing usage patterns, DI seams, and extension notes.
6. **CI Wiring** – add enforcement to the lint pipeline and publish how to opt-in
   locally (`lint --select interfaces` style meta flag).

## Workstreams

These linters operate only when the pyqa repository is detected (e.g., project
root contains `pyproject.toml` with the pyqa package) or when the CLI receives
the explicit `--pyqa-rules` toggle. Each internal linter will carry a
`pyqa_scoped = True` marker in its definition so the launcher can opt-in/out
cleanly.

### 9A – Inventory & Rule Specification

* Catalogue composition roots and permitted concrete import locations.
* Enumerate banned constructors/imports (e.g., `TreeSitterContextResolver`,
  `AnnotationEngine`, `ServiceContainer.register` outside bootstrap modules).
* Define preferred interfaces for each domain (analysis, cache, orchestration,
  reporting, compliance, hooks, platform).

### 9B – Static Analysis Hooks

* Build an AST-based linter (`pyqa_interface_linter`) that detects module-level
  violations:
  * Imports from feature modules (`pyqa.analysis`, `pyqa.reporting`, etc.) when
    the corresponding abstraction lives under `pyqa.interfaces.*`, excluding the
    sanctioned composition packages.
  * Module-level references to concrete implementations (e.g., creating
    `TreeSitterContextResolver` or `AnnotationEngine`) outside the owning
    package bootstrap module.
  * Module definitions that introduce closure factories where a module-level
    helper (`functools.partial`, shared utility) should be used.
  * Module exports that omit Google-style docstrings for public callables,
    focusing first on high-value modules (CLI, orchestration, reporting).
  * Constant modules that fail to annotate literals with `Literal`, `Enum`, or
    `Final` as dictated by the coding rules.
  * Modules exceeding predefined LOC/complexity thresholds without an explicit
    allowlist entry, supporting Single Responsibility Principle monitoring.
* Integrate each visitor with `lint` via new internal linter registrations and
  expose targeted meta flags (e.g., `--check-interfaces`, `--check-docstrings`).
* Introduce a `pyqa_module_doc_linter` that enforces the presence of module
  documentation files (`{MODULE}.md`) and validates required sections (overview,
  DI seams, extension points) for each package directory.

### 9C – Constructor & DI Enforcement

* Implement a `pyqa_di_factory_linter` that evaluates modules for DI
  compliance:
  * Only DI composition modules (`core/runtime/di.py`, package `bootstrap.py`)
    may instantiate service implementations or call `ServiceContainer.register`.
  * Detect module-level service wiring that bypasses approved bootstrap helpers
    or mutates service containers directly.
  * Flag procedural dispatch (e.g., `if tool_name == ...`) outside strategy
    modules to reinforce Open/Closed Principle conventions.

### 9D – Architectural Graph Checks

* Extend `tests/architecture/test_dependency_graph.py` to assert module-level
  boundaries:
  * No `src/pyqa/**` module imports `pyqa.analysis.*` unless it resides in the
    `analysis` package or its bootstrap module.
  * CLI, reporting, and orchestration modules only depend on interface modules.
  * Modules designated as value-object namespaces implement the required dunder
    set without relying on ad-hoc suppressions.
  * Protocol implementations registered in DI pass substitution smoke tests to
    safeguard Liskov Substitution compliance.
* Re-run dependency graph generation and update artefacts.

### 9E – CI & Developer Experience

* Wire new linters into `INTERNAL_LINTERS` with meta toggles (`--check-di`,
  `--check-interfaces`, `--check-docstrings`, `--check-immutables`,
  `--check-module-docs`), setting
  `pyqa_scoped = True` so they activate only when the pyqa repo is detected or
  `--pyqa-rules` is passed explicitly.
* Document failure messaging and add guidance to `docs/orchestration/ARCHITECTURE.md`.
* Provide a lightweight `make check-di` alias or CLI recipe for local validation.

### 9F – Rollout & Backfill

* Run the new lint suite, fix existing violations, and capture tricky cases,
  maintaining a repository allowlist where temporary exceptions are required.
* Backfill tests ensuring DI enforcement catches regressions (e.g., fixture
  creating a dummy file with a banned import).
* Update release notes to highlight the new guardrails.

## Success Criteria

* `./lint -n` fails when concrete analysis or orchestration implementations are
  imported outside designated packages.
* All service registrations take place via interfaces-first modules.
* Public-facing modules maintain required docstrings and value types expose the
  mandated dunder methods without suppressions.
* Every package directory ships a `{MODULE}.md` document describing patterns,
  DI touchpoints, and supported extension seams.
* CI and developer docs clearly explain how to interpret and remediate DI
  enforcement failures.
