<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Linting Interfaces

## Overview

`pyqa.interfaces.linting` defines the public contracts for lint runners, lint
state providers, and reporting hooks. The package only exports Protocols,
TypedDict definitions, and simple dataclasses so implementations can be swapped
without violating SOLID boundaries.

## Patterns

* **Metadata** – `LintMetadata` captures rule identifiers, severity, and source
  hints used to annotate runtime results.
* **Options** – `LintingOptions` describes the normalized options that concrete
  runners must accept. Parsers or CLIs convert user input into this structure.
* **State lifecycle** – `LintState` exposes a strict interface for tracking
  discovered files and diagnostics. Implementations must be side-effect free
  outside the provided methods.

## Usage Guidance

* Runtime modules must depend on the interfaces via dependency injection rather
  than importing concrete implementations.
* New fields on the TypedDict or dataclasses should be introduced under feature
  flags to preserve forwards compatibility for plugin authors.
* Entry points must validate that implementations honor `typing.Protocol`
  contracts at startup to surface incompatibilities eagerly.

## DI Seams

* Use `PreparedLintState` as the boundary between orchestration and linters;
  concrete runners should accept it via constructor injection or function
  parameters rather than instantiating it directly.
* Advice builders and reporters should depend on the normalized
  `LintState`/`LintMetadata` Protocols, enabling dependency injection to swap in
  test doubles without touching filesystem state.
* When lint runners need logging, metrics, or cache providers, accept those
  interfaces as optional constructor arguments so the DI container can wire the
  appropriate runtime implementations.

## Extension Points

* Additional linters register via the linting registry by exporting implementations
  that satisfy `LintRunner`/`LintState` Protocols; orchestration discoverers pull
  them through entry points.
* Metadata enrichers (advice, docstring reporters, etc.) should only consume the
  view Protocols defined here so they remain compatible with future runtime
  reshuffles.
* Contributor tooling can add new TypedDict fields or dataclasses behind feature
  flags, but they must document the changes in this file to guide plugin authors.
