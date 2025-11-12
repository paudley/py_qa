<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Compliance Quality Components

## Overview

`pyqa.compliance.quality_components` centralises reusable quality-check building
blocks that were previously embedded in `quality.py`. It now exposes the shared
`QualityCheckResult`, the execution `QualityContext`, and protocol interfaces
consumed by individual check implementations.

## Patterns

The package favours composition via lightweight data classes and `Protocol`
contracts. Concrete checks, such as the Python hygiene scanner, live alongside
these primitives in dedicated modules (`hygiene.py`), keeping interfaces and
behaviours decoupled.

## DI Seams

Consumers obtain the shared types through `pyqa.compliance.quality_components`
and inject their own implementations where required. Helpers within the package
are pure and side-effect free, making them straightforward to wire into the
existing dependency-injection container.

## Extension Points

New quality checks can depend on the exported `QualityCheck` protocol and reuse
`QualityCheckResult` to report findings. Additional helpers should reside in the
package so they can be shared between compliance tooling and CLI integrations.
