# Tool Selection Strategy

This document explains how the lint launcher decides which tools run during a
`pyqa lint` invocation. The goal is simple: **run every tool that can provide
signal for the current workspace** unless the user has opted out explicitly.

We divide tools into three broad families:

1. **External tools** – everything materialised from the catalog
   (black, ruff, pylint, mypy, …).
2. **Internal linters** – phase‑8 implementations that live inside
   `pyqa.linting` (docstrings, suppressions, types, closures, signatures,
   cache, value-types, quality). They are repo-agnostic and can run anywhere.
3. **Internal pyqa linters** – phase‑9 checks (interface enforcement, DI
   validation, module docs, etc.). They rely on pyqa’s layout, so we only run
   them automatically inside the pyqa repo or when the user passes
   `--pyqa-rules` explicitly.

## Vocabulary

- Tools:  A tool can be an external executable ("ruff") or an internal block of
  python logic ("docstrings").   Tools my lint (produce diagnostics), format or
  autofix code, or even generate artifacts for downstream tools.  Critically,
  all tools act on files in the workspace.  Tools must have a short name ("ruff",
  "docstrings", etc.), a description, targetted languages or file patterns and a
  set of actions (fix, format, etc.).

- Workspace:  A set of files that is grouped together by a shared language or
  structure.  PyQa supports many different types of workspace configurations
  including:
    - mono repo with a single language
	- mono repo with multiple languages in dedicated subdirs
	- a mix of both the above
	- a random directory with a single file in it
	- etc.


## Canonical selection algorithm

Given a prepared lint state, tool selection proceeds as follows:

1. Build the registry – external tools from the catalog plus internal tool
   adapters. All the tools should be present in the registry.
2. Determine modifiers from the CLI:
   - Exclusive options (these tell pyqa exactly what to do and only what to do):
      - `--only`/`--select` style filters (currently `execution.only`). `--only`
        is absolute: it defines the exact tool IDs to execute, regardless of
        category or workspace detection. Anything not named is excluded.
   - Additive options (these options potentially add additional tools to the
     selection):
      - `--languages` or inferred languages from the workspace (used for ordering).
      - `--check-*` meta flags and `--pyqa-rules`.

   - Scaling options (these modify the arguments to some tools and activate some
     others that might be deselected by default):
	  - `--sensitivity` which takes a level and will, in general, produce less
	    diagnostics at lower settings and more diagnostics at higher ones.
   - Profile options (these enable other flags and settings to create a profile
     of preselected options):
	  - `-n/--normal` preset (implies ``check_*`` toggles, sets
        `sensitivity=maximum`, and flips `pyqa_rules=True`).
3. Internal linter activation
   - Internal linters (docstrings/suppressions/…) are activated by default at
     `sensitivity >= strict`. The normal preset (`-n`) bumps sensitivity to
     `maximum`, which is why those linters appear automatically when you run
     `./lint -n`.
   - When sensitivity is below `strict` the internal set stays disabled unless
     the user opts in via `--check-*` flags.
   - Internal pyqa linters activate automatically when the workspace is the
     pyqa repo or the user supplies `--pyqa-rules`.
   - After activation, the `--only` filter (if present) still prunes the final
     list back to the explicitly named tools.
4. External tool activation
   - When `--only` is present, skip eligibility heuristics entirely and honour
     exactly the requested tool IDs.
   - Otherwise include every tool in the registry that matches the current
     workspace:
       * The registry knows each tool’s `languages`, `file_extensions`, and
         `config_files`. We consider a tool eligible when any of the following
         is true:
           - the workspace contains files with matching extensions,
           - the workspace declares matching languages (via CLI or detection),
           - required config files exist.
       * Tools tagged `auto_install=False` still run; that tag controls installer
         behaviour, not selection.
   - Configuration overrides (`execution.enable`, `execution.disable`) can add or
     drop tools in the future (future work once Phase 9 linters land).
5. Ordering
   - After the eligible set is determined, `ToolSelector.order_tools` arranges
     tools by phase and declared dependencies.

### Tool catalogue snapshot

- **External** (catalog-sourced): black, isort, prettier, ruff-format, shfmt,
  actionlint, bandit, cargo-clippy, cargo-fmt, checkmake, cpplint,
  dockerfilelint, dotenv-linter, eslint, gofmt, golangci-lint, gts, hadolint,
  luacheck, lualint, mdformat, perlcritic, perltidy, phplint, pylint,
  pyupgrade, remark-lint, ruff, selene, speccy, sqlfluff, stylelint, tombi,
  tsc, yamllint, kube-linter, mypy, pyright (38 tools in total).
- **Internal** (phase‑8, repo-agnostic): docstrings, suppressions, types,
  closures, signatures, cache, value-types, quality.
- **Internal pyqa** (phase‑9, repo-aware): interface enforcement, DI
  construction guards, module documentation linter, etc. (coming online during
  Phase 9 execution).

### Internal-pyqa linter catalogue

These carry `pyqa_scoped = True` in their metadata so the launcher can toggle
them based on workspace detection or the `--pyqa-rules` flag.

- `pyqa_interface_linter` – enforces imports through `pyqa.interfaces.*`,
  flags concrete dependencies outside approved composition roots, validates
  module size/complexity guardrails, and checks value-object conventions.
- `pyqa_di_factory_linter` – guards service construction, ensuring DI wiring
  happens only in sanctioned factories/bootstrap modules and that procedural
  dispatch patterns stay inside the strategy layer.
- `pyqa_module_doc_linter` – requires each package directory to ship an
  uppercase `{MODULE}.md` guide describing patterns, DI seams, and
  extension points.
- `pyqa_composition_root_audit` – verifies registration boundaries and
  cross-package imports against the architectural dependency graph.
- `pyqa_constructor_ban_linter` – detects direct instantiation of banned
  implementations (e.g., analysis engines, context resolvers) outside their
  owning modules.

## Example scenarios

### 1. `./lint -n` in the pyqa repository

- Normal preset forces `sensitivity=maximum` (>= `strict`) and enables internal
  pyqa rules.
- External tools: every catalog tool whose files/configs are present (black,
  ruff, pylint, mypy, pyright, etc.).
- Internal linters: docstrings, suppressions, types, closures, signatures,
  cache, value-types, quality.
- Internal pyqa linters: Phase 9 suite (interfaces, DI, module docs, …).

### 2. `./lint` in a customer repo with only Python files

- External tools: all Python-eligible catalog tools.
- Internal linters: run because the default sensitivity is `strict`; if the
  project config lowers sensitivity they need explicit `--check-*` opt-ins.
- Internal pyqa linters: skipped unless `--pyqa-rules` is supplied.

### 3. `./lint --check-closures --pyqa-rules` in a mixed JS/Python repo

- External tools: Python + JavaScript toolchain (black, ruff, eslint,
  prettier, …).
- Internal linters: closures (explicit flag) plus the remaining phase‑8 linters
  while sensitivity stays at `strict` or above.
- Internal pyqa linters: enabled because `--pyqa-rules` was requested.

### 4. `./lint --only ruff --only mypy`

- External tools: ruff + mypy (explicit filter).
- Internal linters: excluded unless they are also named via `--only`.
- Internal pyqa linters: excluded unless `--only` lists them explicitly.

### 5. `./lint --sensitivity permissive`

- External tools: all catalog tools matching the workspace (permissive affects
  diagnostics, not the set of external tools).
- Internal linters: disabled by default because `permissive < strict`. Enable
  them explicitly via `--check-docstrings`, `--check-types`, etc., if needed.
- Internal pyqa linters: run only when `--pyqa-rules` is supplied or the
  workspace is pyqa.

### 6. `./lint --pyqa-rules` in a non-pyqa repo

- External tools: full catalog for the detected languages.
- Internal linters: enabled when the chosen sensitivity is `strict` or higher.
- Internal pyqa linters: forced on because the CLI flag was passed, even though
  we are outside the pyqa repo.

### 7. `./lint -n --only pylint`

- External tools: only pylint (filtered via `--only`).
- Internal linters: excluded because `--only` limits execution to `pylint`.
- Internal pyqa linters: excluded unless `pylint` is joined by their IDs in the
  `--only` list.

## Future work

- Replace `default_enabled` usage with the eligibility logic above.
- Wire in config toggles (`execution.enable`, `execution.disable`) to adjust the
  eligible set without repeating `--only` on the CLI.
- Expose the categorisation in `pyqa tool-info` so users can inspect families.
