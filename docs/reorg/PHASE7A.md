<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Phase 7A – Root Module Responsibility Audit

| Module                           | Primary Responsibility                                 | Target Package               |
| -------------------------------- | ------------------------------------------------------ | ---------------------------- |
| `pyqa/environments.py`           | Environment detection and configuration heuristics     | `pyqa.core.environment`      |
| `pyqa/tool_env/*`                | Tool runtime preparation and environment bootstrapping | `pyqa.core.environment`      |
| `pyqa/console.py`                | Console/terminal IO helpers                            | `pyqa.runtime.console`       |
| `pyqa/hooks.py`                  | Hook registration and execution                        | `pyqa.hooks`                 |
| `pyqa/installs.py`               | Installer orchestration                                | `pyqa.runtime.installers`    |
| `pyqa/update.py`                 | CLI update orchestration                               | `pyqa.runtime.installers`    |
| `pyqa/config_loader.py`          | Configuration loading orchestrator                     | `pyqa.core.config`           |
| `pyqa/config_loader_sections.py` | Config section merging logic                           | `pyqa.core.config.sections`  |
| `pyqa/config/utils.py`           | Config utilities/helpers                               | `pyqa.core.config.utils`     |
| `pyqa/constants.py`              | Global constants and defaults                          | `pyqa.core.config.constants` |
| `pyqa/languages.py`              | Language heuristics                                    | `pyqa.platform.languages`    |
| `pyqa/paths.py`                  | Path normalization utilities                           | `pyqa.platform.paths`        |
| `pyqa/clean.py`                  | Workspace cleanup CLI                                  | `pyqa.clean`                 |
| `pyqa/severity.py`               | Severity models and helpers                            | `pyqa.core.severity`         |
| `pyqa/update.py`                 | CLI update workflow                                    | `pyqa.runtime.installers`    |
| `pyqa/workspace.py`              | Workspace detection utilities                          | `pyqa.platform.workspace`    |
