<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Config Models Package

## Overview

The `pyqa.config.models` package exposes typed configuration surfaces by
assembling building blocks from `pyqa.config.model_defs` and
`pyqa.config.models.sections`.

## Patterns

* `model_defs` hosts reusable primitives (enums, sentinels, container logic)
  while `sections` contains focused Pydantic models for individual config
  concerns.
* The package re-exports the canonical API so existing imports continue to
  function as the decomposition progresses.

## DI Seams

* `models.sections.execution` coordinates with runtime DI to determine default
  worker counts.
* The `Config` container depends on catalog metadata for dedupe preferences and
  tool overrides.

## Extension Points

* Introduce new configuration sections under `models/sections/` and register
  them with `Config`.
* Extend value-type guidance by adding implications or rules within
  `model_defs.value_types` while re-exporting through this package.
