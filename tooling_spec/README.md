# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

# pyqa Tooling Specification

This package provides a distributable view of the pyqa tooling catalog – the
schemas, model definitions, and loader utilities that describe how tools are
configured. It is intended for future publication so external systems can
consume the catalog without depending on the full pyqa runtime.

The package currently delegates to the in-repository catalog implementation.
Subsequent milestones will inline the necessary modules and author dedicated
packaging metadata, changelog automation, and release workflows.
