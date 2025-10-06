<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Exit Status Semantics

This document explains how PyQA interprets tool exit codes, how the runtime
separates *tool failures* from *diagnostic failures*, and how catalog authors can
model non-standard exit behaviour. The goal is to avoid conflating a tool that
crashed with a tool that completed successfully but reported issues.

## Terminology

* **Success** – The tool completed its work and returned an exit status that we
  treat as operational success. This includes traditional `0` codes and any
  codes explicitly listed in the catalog as success values.
* **Diagnostic failure** – The tool executed normally and produced diagnostics.
  These diagnostics should surface to the user and flip the CLI exit status, but
  they do **not** indicate a broken orchestration.
* **Tool failure** – The tool did not complete its work (e.g. crashed, was
  misconfigured, or exited with an unexpected status). These failures should be
  surfaced prominently even when diagnostics are present.
* **Unknown** – Exit codes that do not fall into any of the above buckets. We
  conservatively treat these as tool failures when they are non-zero and no
  diagnostics were produced.

These categories map directly to `ToolExitCategory` instances stored on every
`ToolOutcome`.

## Classification Flow

When a tool action finishes, `ActionExecutor` evaluates the exit status using the
following order:

1. **Explicit catalog codes** – `ActionExitCodes.tool_failure`, `.success`, and
   `.diagnostic` take precedence when provided.
2. **Diagnostics present** – Any non-zero exit code combined with diagnostics is
   treated as a diagnostic failure (the tool ran and found issues).
3. **Known heuristics** – We special-case long-standing conventions for
   `pylint`, `tombi`, and fix/format actions that exit with `1` after applying
   changes.
4. **Ignored exit codes** – Actions that set `ignore_exit` can still treat
   certain exit codes as success when no diagnostics were produced.
5. **Fallback** – Remaining non-zero exit codes without diagnostics are treated
   as unknown/tool failures.

The evaluation returns both the adjusted return code (typically `0` for success)
and the resulting `ToolExitCategory`.

## Tool vs. Diagnostic Failures

*Tool failures* map to `ToolExitCategory.TOOL_FAILURE` and always trigger
warnings in the logs. They also cause `ToolOutcome.indicates_failure()` and
`RunResult.has_failures()` to return `True`, regardless of whether diagnostics
were produced.

*Diagnostic failures* map to `ToolExitCategory.DIAGNOSTIC`. They preserve the
original non-zero exit code so that downstream consumers can emit the correct
status, but the run is not marked as a crash. The CLI converts these outcomes
into user-facing diagnostics and still exits with `1` when any diagnostic is
present.

## Fix and Format Actions

Many formatters exit with `1` after mutating files without reporting diagnostics.
Action definitions that set `isFix: true` automatically treat a lone exit code of
`1` as success. Catalog authors can override or expand this behaviour by listing
additional success codes in `exitCodes.success`.

## Catalog Configuration

The tool catalog exposes an `exitCodes` object on every action:

```json
"exitCodes": {
  "success": [0, 1],
  "diagnostic": [3],
  "toolFailure": [2]
}
```

* `success` – Exit codes that should be treated as operational success. The
  orchestrator rewrites these to `0` before recording the outcome.
* `diagnostic` – Exit codes that indicate diagnostics were raised. They keep
  their original value in the outcome so callers can convey that the tool found
  issues.
* `toolFailure` – Exit codes that signal an operational failure even when
  diagnostics are present.

All three collections are optional; omitting them falls back to the heuristics
above. See `tooling/schema/tool_definition.schema.json` for the full structure
and additional guidance.

## Serialization and Caching

`ToolOutcome.exit_category` is persisted alongside every cached outcome. When we
load results from cache, the executor re-evaluates the exit code and updates the
category to ensure that improvements to the classification logic apply to cached
runs as well.

## Observing Results

* `RunResult.has_failures()` returns `True` when any outcome reports
  `ToolExitCategory.TOOL_FAILURE` or when a non-zero exit code is not accompanied
  by diagnostics.
* `RunResult.has_diagnostics()` returns `True` when any outcome contains
  diagnostics, regardless of exit category.
* The lint CLI marks runs as failed (exit code `1`) whenever diagnostics are
  present, even if every tool executed successfully.

## Operational Guidance

* Add catalog success codes for fix/format tools that exit with non-zero codes
  after modifying files.
* Reserve tool failure codes for situations where the tool genuinely cannot run
  (missing configuration, crashes, parser errors, etc.).
* Avoid relying on return codes alone; always consult `exit_category` to drive
  control flow.

## Summary

By distinguishing operational failures from diagnostic output we avoid
incorrectly flagging successful runs as broken. The new exit-code schema gives
catalog authors fine-grained control, while `ToolExitCategory` ensures a single
source of truth for downstream consumers.
