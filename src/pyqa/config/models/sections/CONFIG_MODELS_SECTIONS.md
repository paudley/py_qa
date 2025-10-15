<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Config Model Sections

## Overview

The `pyqa.config.models.sections` package contains focused Pydantic models for
independent configuration domains (discovery, execution, severity, etc.).

## Patterns

* Each module defines a single Pydantic model (plus related defaults) to keep
  responsibilities narrow.
* Defaults live alongside the models they influence and are exported through
  this package's `__all__` for easy reuse.

## DI Seams

* `execution.default_parallel_jobs` computes worker counts based on the host
  CPU, allowing runtime DI or tests to override via patching when required.

## Extension Points

* Add new configuration sections by introducing a module in this package and
  re-exporting the model inside `__init__.py`.
* Shared defaults that apply to multiple tools should flow back into
  `model_defs.config_container` via the `SharedKnobSnapshot` helpers.
