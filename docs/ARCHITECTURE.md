<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Architecture & Module Layout

The REORG initiative is complete and the repository now reflects the final,
interface-first architecture. This document consolidates the guidance that used
to live in `REORG_MODULES.md`, `REORG_PLAN.md`, and `docs/reorg/*` so the
current layout can be referenced without bouncing between historical plans.

## Objectives

* Keep each package focused on a single responsibility with explicit inputs and
  outputs.
* Depend on interfaces/Protocols instead of concrete implementations so modules
  can evolve independently.
* Ship the runtime (`src/pyqa`) and tooling specification
  (`src/tooling_spec`) as peers so downstream tools can reuse the catalog
  models without importing orchestration code.
* Treat third-party dependencies (spaCy + `en_core_web_sm`, tree-sitter,
  Typer, Rich, etc.) as mandatory and fail fast when they are unavailable.

## Engineering Guardrails

* Prefer Google-style docstrings for every public function/method and keep them
  descriptive enough to act as documentation.
* Break apart complex functions (>5 arguments or deeply nested logic) into
  helpers or parameter dataclasses.
* Avoid `Any`, `object`, or `Optional[None]` types; reach for `Literal`,
  `Final`, `enum`, `Protocol`, and structured dataclasses instead.
* Hoist imports to module scope—conditional imports (including `TYPE_CHECKING`
  guards) are forbidden. When optional behaviour is needed, define the
  abstraction in `pyqa.interfaces.*` and inject an implementation.
* Lint suppressions are discouraged. The only allowed suppressions are the ones
  documented in this repo (dynamic cache helpers, subprocess hardening, protocol
  annotations, controlled CLI imports, download safety checks) and they must
  include a justification.
* Prefer standard-library helpers (`functools.partial`, `itertools`,
  `contextlib`, etc.) before adding new inline closures or wrappers.

## Package Responsibilities

### `pyqa.cache`

Provides cache providers, token builders, the execution cache context, and
helpers for persisting tool metadata. Cache implementations follow the
`CacheProvider`/`CacheRepository` interfaces defined under `pyqa.interfaces`.
See `docs/CACHING.md` for operational details.

### `pyqa.analysis`

Hosts higher-level analysis utilities, including the spaCy-powered advice
pipeline and tree-sitter integrations. Subpackages isolate external
dependencies (`analysis/spacy`, `analysis/treesitter`) while the top-level
module exposes pure-Python helpers (impact analysis, suppression utilities).

### `pyqa.diagnostics`

Owns the diagnostic data models, filtering pipeline, and rendering adapters that
feed reporting layers. Tool parsers, orchestrator adapters, and reporting
modules should rely on these shared helpers rather than reimplementing
transformations.

### `pyqa.interfaces`

The central location for dependency-inversion contracts. Domain-specific files
(`analysis.py`, `catalog.py`, `cli.py`, `config.py`, `reporting.py`, etc.)
contain Protocols, TypedDicts, and dataclasses—no concrete logic. All runtime
packages import their abstractions from here.

### `pyqa.cli`

Groups the Typer application, command packages, shared option builders, and the
CLI launcher. Commands live under `cli/commands/<name>/` with supporting services
in `cli/core/`. The CLI consumes injected services rather than importing runtime
implementations directly.

### `pyqa.config`

Contains the user-facing configuration models, loaders, overrides pipeline, and
helpers for CLI configuration discovery. Shared configuration interfaces live in
`pyqa.interfaces.config`.

### `pyqa.core` & `pyqa.orchestration`

`core` houses foundational runtime services (DI container, logging adapters,
serialization helpers, filesystem utilities). `orchestration` plans tool runs,
builds execution graphs, and interacts with the cache via interfaces.

### `pyqa.reporting`

Responsible for converting diagnostics into user-facing outputs (console,
Markdown/PR summaries, SARIF, JSON). Advice builders live in
`pyqa.reporting.advice` and only depend on the interfaces and analysis packages.

### `pyqa.tools`

Defines the Tool/ToolAction models, base Protocols for command builders and
parsers, and built-in tool registrations. Built-in tools live in
`pyqa/tools/builtin_*` and rely on the shared interfaces.

### `tooling_spec`

Exports the catalog schema, metadata types, and helper utilities that external
projects can import. Runtime modules consume the specification via typed façade
wrappers (`pyqa.catalog.*`). Keep spec changes backwards compatible and
documented under `docs/tooling/`.

## Entry Points & Extension Seams

The repository uses Python entry points to keep extensions pluggable:

* `pyqa.catalog.plugins` – catalog strategy and tool metadata providers.
* `pyqa.cli.plugins` – Typer applications that should be attached to the CLI.
* `pyqa.diagnostics.plugins` – supplementary diagnostic processors/adapters.

Plugin registries hydrate these entry points at start-up and validate each
implementation against the relevant Protocols.

## Documentation Map

* `docs/ARCHITECTURE.md` (this file) – current package layout and guardrails.
* `README.md` – high-level overview and quickstart instructions.
* `docs/CACHING.md` – cache architecture and troubleshooting.
* `docs/orchestration/` – deep dive into the orchestration pipeline and tool
  selection heuristics.
* `docs/tooling/` – catalog and strategy authoring guides.
* `SELECTION.md`, `SOLID_CLI.md`, `docs/orchestration/selection.md` – command
  and dependency-injection guidance.

## Historical Note

The previous `REORG_*` documents and `docs/reorg` phase notes have been removed
now that the work is complete. Any future architectural changes should update
this document and the relevant deep-dive docs directly instead of creating new
one-off plans.
