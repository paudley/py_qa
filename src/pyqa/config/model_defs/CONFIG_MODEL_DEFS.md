<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Config Model Definitions

## Overview

The `pyqa.config.model_defs` package centralises reusable building blocks for
configuration modelling, including enumerations, sentinels, the primary
configuration container, and supporting value-type schemas.

## Patterns

* Values flow from narrow type definitions (`enums`, `sentinels`) into richer
  Pydantic surfaces assembled under `config_container`.
* Section-specific models live under `pyqa.config.models.sections` and are
  composed by the `Config` container to honour SOLID separation of concerns.

## DI Seams

* The `Config` container expects catalog metadata via
  `pyqa.catalog.metadata.catalog_duplicate_preference` and interacts with tool
  settings for dedupe and mypy synchronisation.
* Sensitivity presets are the main injection point for adjusting shared knobs
  without mutating individual section models.

## Extension Points

* Introduce new configuration sections by adding a Pydantic model under
  `pyqa.config.models.sections` and extending the `Config` container with the
  corresponding Field.
* Extend sensitivity behaviour by defining additional `SensitivityPreset`
  entries keyed by `SensitivityLevel`.
