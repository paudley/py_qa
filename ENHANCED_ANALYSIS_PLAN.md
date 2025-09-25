# Tree-sitter & spaCy Enhancements

## Goals
- Extend cross-tool deduplication by comparing semantic fingerprints of diagnostics.
- Enrich PR summaries with inline symbol highlighting.
- Generate smart suppression hints hooking into existing diagnostics.
- Provide change-focused triage by correlating diagnostics with recent diffs.
- Surface a refactor navigator derived from structural metrics and NLP themes.

## Proposed Steps
1. Audit existing annotation outputs and dedupe pipeline integration points.
2. Prototype message fingerprinting leveraging `AnnotationEngine` spans plus normalized code context.
3. Update reporting emitters to inject highlighted spans and advice metadata into Markdown outputs.
4. Build suppression hint suggestions using shared heuristics and annotate them in diagnostics.
5. Implement change-impact scoring by diffing AST spans against Git metadata.
6. Assemble refactor navigator using Tree-sitter metrics and spaCy classification of lint themes.
7. Expand tests to cover fingerprints, new reporting artifacts, suppression hint logic, and navigator output.

## Open Questions
- How to cache AST parses to avoid repeated disk reads in change-impact analysis?
- What thresholds should trigger suppression hints vs. advice?
- Should refactor navigator output integrate into CLI or stay as documentation/report artifact?

