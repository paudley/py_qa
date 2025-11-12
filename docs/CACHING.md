<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Caching Strategy Roadmap

This document describes how PyQA should evolve its caching story across both internal
and external tools. The recommendations are structured into **conservative**, **normal**,
and **aggressive** phases so that we can stage adoption while maintaining confidence in
result fidelity.

The design targets *language-agnostic* behaviour: tools may operate on Python, JavaScript,
C++, SQL, or multi-language workspaces. Any caching metadata we capture must therefore be
expressive enough to cover cross-language dependency graphs, generated artefacts, and
non-source resources (configuration files, schemas, fixtures, etc.).

## Goals

* Avoid re-running expensive tools when relevant inputs are unchanged.
* Give individual tools control over the granularity of cache invalidation.
* Preserve correctness even for tools that load additional dependencies transitively.
* Provide observability so teams understand why cache hits or misses occur.
* Keep the system language-agnostic and extensible.

***

## Conservative Phase

The conservative phase introduces the minimum metadata necessary to cache internal tools
safely without altering the behaviour of external tools. It focuses on opt-in controls
and explicit dependency reporting.

### 1. Cache Capability Flags

* Extend `Tool` metadata with a `cache_scope` descriptor. Candidate values:
  * `"disabled"`: default for all tools today.
  * `"per-file"`: tool is invoked once per file and only depends on that file.
  * `"per-invocation"`: tool processes the full target set (e.g., `pyqa-python-hygiene`).
* Internal runners must declare their scope explicitly before caching is enabled.

### 2. Dependency Manifests

* Update the internal linter interface so runners return the set of files they actually
  inspected. Use existing `file_metrics` plumbing to capture this data.
* If a tool cannot enumerate dependencies, the orchestrator keeps caching disabled to
  avoid false positives.

### 3. Stable Cache Tokens

* Reuse the existing cache token (execution options + tool versions) but append the
  tool’s declared `cache_scope` and any tool-specific toggles (e.g., suppression flags).
* This ensures cache entries are invalidated whenever behaviour-affecting flags change.

### 4. No Behaviour Change by Default

* External tools continue to use the current cache mechanism.
* Internal tools stay uncached unless they declare `cache_scope != "disabled"`.
* Provide a CLI flag (`--cache-internal`) to toggle internal caching globally for pilot
  teams.

***

## Normal Phase

The normal phase widens caching support by making dependency tracking richer and
leveraging content hashing to reduce spurious invalidations.

### 1. Dependency Graph Recording

* Introduce an optional hook allowing tools to declare *transitive* dependencies.
  * Example: a TypeScript analyzer can report the closure of imported `.ts` files.
  * The orchestrator stores these dependencies alongside the primary file list.
* Cached entries are invalidated when any recorded dependency changes.

### 2. Content Hash Checkpoints

* For `per-file` tools, capture a content hash (e.g., blake2) instead of relying solely on
  `mtime` and file size.
* This avoids unnecessary cache busting when editors rewrite files without actual
  content changes.

### 3. Internal Runner Cache Integration

* Allow `ActionExecutor._store_outcome_in_cache` to persist outcomes for internal runners
  when `cache_scope` is opt-in and a dependency manifest is available.
* Cache entries are keyed by tool name, action, cache token, and dependency hash, matching
  the behaviour of external tool caching.

### 4. Observability & Diagnostics

* Emit debug logs (guarded behind an env var such as `PYQA_CACHE_TRACE`) explaining cache
  hits/misses, dependency mismatches, and token changes.
* Surface aggregate metrics after runs so CI pipelines can validate cache effectiveness.

***

## Aggressive Phase

The aggressive phase introduces deeper invalidation logic and sharing mechanisms aimed at
large repositories and CI environments.

### 1. Dependency DAG & Incremental Invalidation

* Maintain a dependency graph (file → cached tool outputs). When a file changes,
  invalidate downstream cache entries automatically, enabling precise incremental rebuilds.
* Support language-specific plugins to populate the DAG (e.g., a Rust crate graph or a
  SQL schema dependency tree).

### 2. Dynamic Dependency Reporting

* Instrument tool execution so they can stream “dynamic dependency” events during runtime.
  * For Python, integrate with import hooks to record modules actually loaded.
  * For compiled languages, parse build logs or language server telemetry.
* Merge these dynamic dependencies with the static manifests to achieve high fidelity.

### 3. Shared Result Federation

* Persist cache entries to a project-local database (SQLite/LMDB) keyed by content hashes
  and environment fingerprint (tool version, platform, interpreter).
* Allow CI pipelines or developer workstations to share cache artefacts, with optional
  signing to ensure integrity.

### 4. Adaptive Caching Policies

* Track cache hit rates and execution time per tool to decide the appropriate caching
  strategy automatically:
  * Expensive tools may graduate from `per-invocation` to DAG-based caching.
  * Cheap tools can remain per-file or even uncached to simplify debugging.
* Provide CLI overrides so teams can pin a policy when necessary.

***

## Next Steps

1. Prototype the conservative changes for one internal tool (e.g., `pyqa-python-hygiene`)
   to test metadata requirements and cache behaviour.
2. Add tooling documentation and examples so repository owners can opt in gradually.
3. Instrument the cache layer with trace logging to validate the hypotheses before moving
   to the normal phase.

By staging adoption and demanding explicit dependency data, we ensure caching remains
correct across all supported languages while giving teams tangible performance wins as the
system matures.
