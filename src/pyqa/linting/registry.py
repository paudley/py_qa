# SPDX-License-Identifier: MIT
"""Registry describing the internal linters available to the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from pyqa.cli.commands.lint.preparation import PreparedLintState

from .base import InternalLintReport, InternalLintRunner
from .cache_usage import run_cache_linter
from .closures import run_closure_linter
from .docstrings import run_docstring_linter
from .signatures import run_signature_linter
from .suppressions import run_suppression_linter
from .typing_strict import run_typing_linter


@dataclass(slots=True)
class InternalLinterDefinition:
    """Describe how a CLI meta flag maps to an internal linter."""

    name: str
    meta_attribute: str
    selection_tokens: tuple[str, ...]
    runner: InternalLintRunner
    description: str


INTERNAL_LINTERS: tuple[InternalLinterDefinition, ...] = (
    InternalLinterDefinition(
        name="docstrings",
        meta_attribute="check_docstrings",
        selection_tokens=("docstring", "docstrings"),
        runner=run_docstring_linter,
        description="Validate Google-style docstrings using Tree-sitter and spaCy.",
    ),
    InternalLinterDefinition(
        name="suppressions",
        meta_attribute="check_suppressions",
        selection_tokens=("suppressions", "lint-suppressions"),
        runner=run_suppression_linter,
        description="Report discouraged noqa/pylint/mypy suppression directives.",
    ),
    InternalLinterDefinition(
        name="types",
        meta_attribute="check_types_strict",
        selection_tokens=("types", "typing", "strict-types"),
        runner=run_typing_linter,
        description="Detect banned Any/object annotations in code paths.",
    ),
    InternalLinterDefinition(
        name="closures",
        meta_attribute="check_closures",
        selection_tokens=("closures", "partials"),
        runner=run_closure_linter,
        description="Discourage ad-hoc closure factories in favour of functools.partial or itertools helpers.",
    ),
    InternalLinterDefinition(
        name="signatures",
        meta_attribute="check_signatures",
        selection_tokens=("signatures", "parameters"),
        runner=run_signature_linter,
        description="Highlight functions whose signatures exceed the parameter threshold.",
    ),
    InternalLinterDefinition(
        name="cache",
        meta_attribute="check_cache_usage",
        selection_tokens=("cache", "lru_cache", "functools"),
        runner=run_cache_linter,
        description="Reject direct functools.lru_cache usage in favour of pyqa.cache utilities.",
    ),
)


def iter_internal_linters() -> Sequence[InternalLinterDefinition]:
    """Return the registered internal lint definitions."""

    return INTERNAL_LINTERS


__all__ = [
    "InternalLinterDefinition",
    "INTERNAL_LINTERS",
    "iter_internal_linters",
]
