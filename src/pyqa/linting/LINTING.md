<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Linting

## Overview

This document describes the pyqa.linting module.

## Patterns

* Suppression handling recognises the `suppression_valid:` comment marker; when
  present with a four-word justification, the suppressions linter accepts the
  directive (surfacing it only when `--show-valid-suppressions` is supplied).
* Hygiene enforcement now ships with a pyqa-specific variant that flags
  `SystemExit`/`os._exit` calls outside CLI entry points and stray
  `print`/`pprint` usage in production modules.

## DI Seams

Document dependency inversion touchpoints and service registration expectations.

## Extension Points

Outline supported extension seams and guidance for contributors.
