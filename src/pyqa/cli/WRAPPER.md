<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# CLI Wrapper Alignment Plan

## Objectives

* Provide a single, reliable mechanism for launching pyqa CLI commands (`lint`,
  `check-quality`, `update`, etc.)
* Preserve SOLID principles: keep the launcher focused, expose clear seams for
  interpreter selection, and allow future extension.
* Ensure users experience consistent behaviour regardless of environment.

## Functional Requirements

1. **Exit Codes**

   * The wrapper must propagate the underlying command’s exit code to the shell
     without modification.
   * Failures in interpreter discovery or fallback mechanisms must yield
     non-zero exit codes with helpful diagnostics.

2. **Output Cleanliness**

   * Avoid printing internal status messages (“falling back…”, uv internals)
     unless running in verbose/debug mode.
   * All normal output must come from the CLI command itself.

3. **Interpreter Selection**

   * Respect an override environment variable (`PYQA_PYTHON`) when provided.
   * Otherwise, probe the current interpreter: if it meets version requirements (≥3.12), finds `pyqa.cli.app` importable, and the resolved module path lives under the repository `src` directory, reuse it directly.
   * If the probe fails (missing deps, wrong version, import outside the repo), fall back to `uv --project … run python -m pyqa.cli.app …`.
   * When no viable interpreter is discovered, exit with an informative message.

4. **Repository Code Preference**

   * Ensure the repository’s `src/` directory is at the front of
     `PYTHONPATH` so local code always wins over globally installed packages.
   * Do not rely on system `pyqa` installations.

5. **Environment Agnosticism**

   * Wrappers must function even when the user’s environment lacks pyqa’s
     dependencies; they bootstrap via `uv`, downloading the binary into a
     cache (e.g. `.lint-cache/uv`) when not already available, and executing
     `uv --project <root> run python -m pyqa.cli.app <command>` transparently.
   * When running outside the repo, fail fast with a clear message.

6. **Consistent Entry Point**

   * All CLI scripts should share the same launcher function to minimise
     divergence.
   * Support legacy entry points (e.g. `--install` shim for `lint`) via minimal
     wrapper logic.

## Implementation Plan

1. **Launcher Module**

   * Implement a `pyqa/cli/_cli_launcher.py` module that:
     * Normalises `PYTHONPATH` to preferring the repo’s `src` directory.
     * Probes the active interpreter (`sys.executable` or `PYQA_PYTHON`) for compatibility (version ≥3.12, imports `pyqa.cli.app` from the repo).
     * When the probe succeeds, execute `python -m pyqa.cli.app <command>` directly.
     * When the probe fails, download `uv` on demand (e.g. into `.lint-cache/uv`) if missing, then run `uv --project <root> run python -m pyqa.cli.app <command>` silently.
       * Suppress extraneous `uv` output unless in verbose mode.
       * Pass through exit codes.

2. **Wrapper Scripts**

   * Convert each CLI script to a thin Python file that imports and invokes
     `launch(<command>, args)`.

3. **Diagnostics & Logging**

   * Provide optional `PYQA_WRAPPER_VERBOSE=1` mode that prints interpreter
     selection details, detected site-packages, in-process vs. spawned execution
     decisions, and the exact `uv` command when fallbacks occur.
   * Default behaviour should be silent unless errors occur.
   * Example usage:
     * `PYQA_WRAPPER_VERBOSE=1 ./lint --help`

4. **Dependency Remediation**

   * When the selected interpreter is not the currently running executable, the
     launcher spawns it with an internal sentinel (`PYQA_LAUNCHER_EXPECT_DEPENDENCIES`)
     so the child can report missing packages without crashing the shell.
   * If the child interpreter exits with the sentinel or a dedicated exit code,
     we immediately rerun `uv --project … run --locked …` to install or repair the
     environment before executing the CLI again.
   * When the initial probe rejects the interpreter outright (wrong version,
     import outside the repo), the wrapper jumps straight to `uv --locked …`.

5. **Testing**

   * Add wrapper tests covering scenarios:
     * Local dependencies installed (`pyqa.cli` importable).
     * Local dependencies missing, fallback via `uv`.
     * Missing `uv` binary.
     * Non-existent `.venv` or `PYQA_PYTHON` path.
   * Verify exit codes in each scenario.

6. **Documentation**

   * Update `cli/CLI_MODULE.md` with wrapper behaviour, environment variables,
     and troubleshooting steps.
   * Reference `WRAPPER.md` from developer docs for quick context.

## Anti-Goals

* Do not rely on shell-specific features (Bash arrays, etc.) in the new
  launcher; keep logic in Python for portability.
* Avoid printing generic status text in normal operation.

## Next Steps

* Build the new launcher module according to this plan.
* Migrate one wrapper (e.g. `lint`) to verify behaviour before updating the rest.
* Once stable, apply the pattern across all CLI entry points and remove
  redundant logic.

## Scenario Coverage

* Fresh checkout with only system Python (<3.12): fallback to downloading `uv`
  and running `uv --project … run python -m pyqa.cli.app …` so dependencies are
  installed automatically.
* Fully synced environment, Python ≥3.12, running outside the repo (most common):
  launcher first attempts the repo virtualenv (`.venv/bin/python`); if not suitable,
  it reuses the active interpreter only when imports resolve to the repo; otherwise
  it falls back to `uv` to avoid mixing unrelated packages.
* User runs inside an unrelated virtualenv: probe detects imports outside the
  repo, so we fall back to `uv` to avoid contamination.
* User sets `PYQA_PYTHON`: launcher obeys it; if the interpreter fails the
  compatibility probe, we emit a clear error so they fix the path.
* `uv` missing: wrapper downloads `uv` into `.lint-cache/uv` and executes it,
  ensuring consistent behaviour without manual installs.
* Incomplete `.venv` (e.g., only `uv` installed): the probe succeeds, but the
  child interpreter emits the dependency sentinel which triggers an automatic
  `uv --locked …` run to hydrate packages before rerunning the command.

### Scenario Observations (2025-02-27)

| Scenario                                  | Command (illustrative)                                                       | Outcome                                                                                            |
| ----------------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Explicit override below minimum version   | `PYQA_PYTHON=/tmp/python311_stub PYQA_UV=/tmp/fake_uv.sh ./lint --help`      | Probe reports `(3, 11)`, launcher switches to uv fallback without touching the repo interpreter.   |
| Interpreter resolves modules outside repo | `PYQA_PYTHON=/tmp/python_outside_stub PYQA_UV=/tmp/fake_uv.sh ./lint --help` | Probe emits `outside`, launcher delegates to uv fallback to avoid stale environments.              |
| uv override missing                       | `PYQA_PYTHON=/tmp/python_outside_stub PYQA_UV=/does/not/exist ./lint --help` | Launcher aborts with `PYQA_UV executable not found` and exits non-zero, preventing silent failure. |

> **Note:** The wrapper BDD tests synthesise these stub interpreters and uv scripts in a
> temporary directory. Re-create lightweight Python/bash stubs when manually exercising
> the scenarios.
