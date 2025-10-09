# Phase 12 – Interface Realignment & SOLID Enforcement

## Guiding Principles

* Interfaces define protocols, dataclasses, and literals only. They **never**
  wrap, re-export, or invoke concrete logic.
* Concrete implementations live in their domain packages (runtime,
  orchestration, reporting, installers) and are exposed via dependency
  injection or explicit factory wiring.
* The Dependency Inversion, Interface Segregation, and Open/Closed principles
  guide every module refactor; Single Responsibility is enforced by handling
  one domain per change set.
* Backwards-compatibility shims (re-exporting old import paths or keeping alias
  helpers) are banned; consumers must adopt the new interfaces directly.

## Module-by-Module Tasks

### Interfaces Package (`src/pyqa/interfaces`)

* Delete wrapper modules that currently return real implementations
  (`analysis_bootstrap`, `analysis_services`, `installers_dev`,
  `installers_update`, `reporting`, any orchestration helpers) and replace
  them with pure protocol/datastructure definitions.
* Introduce refined protocols where needed:
  * `interfaces/orchestration_selection.py` – owns all selection dataclasses
    and helper builders.
  * `interfaces/core.py` – exposes protocols for `ConsoleFactory`,
    `ConsoleManager`, `LoggerFactory`, etc; no direct Rich references.
  * `interfaces/analysis.py` – provides `AnnotationProvider`, `ContextResolver`,
    `FunctionScaleEstimator`, `MessageSpan`, `HighlightKind`, plus
    `NullAnnotationProvider/NullContextResolver` dataclasses (pure data, no
    external imports).
* Update `__init__.py` to remain empty (no exports) with explanatory docstring.

### Runtime & DI Modules

* `runtime/console/manager.py`: move Rich-dependent console creation here;
  export factories via DI registration; interfaces reference only protocols.
* `core/runtime/di.py`: ensure services register interface-appropriate factories
  (e.g. `console_factory`) without reaching back into interfaces.
* `runtime/installers` modules: keep concrete install helpers here; CLI imports
  through DI or dedicated service lookups rather than wrappers.

### Orchestration

* `orchestration/tool_selection.py`: consume the interface dataclasses and
  helper builders; ensure phase ordering constants derive from interfaces.
* `orchestration/orchestrator.py`: resolve annotation/context services through
  DI and protocols (no imports from interfaces that wrap implementations).
* Remove `cli/core/orchestration.py`; orchestrator pipeline construction lives
  either in orchestration runtime or a new adapter under interfaces (protocol
  only) with concrete helper remaining in orchestration.

### CLI Commands

* `cli/commands/install/command.py`: import installers via runtime module or DI;
  avoid interface wrappers.
* `cli/commands/update/command.py`: consume `runtime.installers.update` directly
  or through a DI-resolved strategy registry; interface module only defines
  the contracts.
* `cli/commands/lint/runtime.py`: resolve `register_analysis_services` and
  orchestrator pipelines via DI/service lookup.
* `cli/commands/lint/reporting.py`, `lint/progress.py`, `lint/fetch.py`,
  `lint/command.py`: depend on `interfaces.core.ConsoleManager` and
  `interfaces.orchestration_selection` for hooks/selection data; all concrete
  modules resolved via DI.

### Reporting Modules

* Switch reporting presenters/emitters/highlighting/advice builders to import
  `NullAnnotationProvider`, `MessageSpan`, etc., from `interfaces.analysis`.
* Ensure annotation service lookups use DI or factories located in
  `analysis/services.py`, not interfaces.
* Update progress/reporting renders to get console managers from DI/resolution
  rather than `pyqa.runtime.console` re-exports.

### Analysis & Linting

* `linting/docstrings.py`: reference spaCy/Tree-sitter helpers through domain
  modules (`analysis.spacy.loader`, `analysis.treesitter.*`). If an interface is
  required, define protocol only; keep loader logic in analysis modules.
* `analysis/annotations/engine.py`: rely on `interfaces.analysis.MessageSpan`
  dataclass and adjust imports accordingly.
* Expand Phase 9 linters/tests to ensure any new interfaces remain protocol-only.

### Docs & Tests

* Update module documentation (`MODULE.md` per package) describing the new
  interface seams and removal of wrappers.
* Refresh `SELECTION.md` and `docs/reorg` narrative to reference the enforced
  rules (no re-exports, no wrappers, SOLID compliance).
* Extend lint/pytest coverage: run `./lint -n --only pyqa-interfaces`, the full
  lint preset, and targeted suites (`tests/test_lint_cli.py`,
  `tests/test_orchestrator.py`, reporting tests) after every refactor batch.

## Validation Checklist

1. Interfaces contain only protocols/datataclasses; no concrete logic or
   re-export wrappers remain.
2. All consumers import from either interfaces (for contracts) or domain
   modules (for implementations) without violating DIP.
3. `pyqa-interfaces` linter passes cleanly.
4. CLI lint/reporting/install commands run through DI-resolved services.
5. Documentation and tests reflect the new architecture and guardrails.
