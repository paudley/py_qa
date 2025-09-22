# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Banned word checking utilities for commit messages and text checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_BANNED_TERMS = {
    "password123",
    "secret_key",
    "api_key_here",
    "TODO: remove before commit",
    "FIXME: security",
    "hardcoded password",
    "temp password",
    "dummy password",
    "fuck",
    "shit",
    "damn",
    "quick hack",
    "don't know why this works",
    "no idea",
    "cargo cult",
    "spaghetti code",
    "brain dead",
    "stupid fix",
    "skip ci",
    "skip tests",
    "disable tests",
    "commented out tests",
    "dumb",
    "retarded",
    "idiotic",
    "moronic",
    "copied from stackoverflow",
    "stolen from",
    "console.log",
    "print debugging",
    "binding.pry",
    "pdb.set_trace()",
}


@dataclass
class BannedWordChecker:
    """Check text against repository and user-specific banned word lists."""

    root: Path
    personal_list: Path | None = None
    repo_list: Path | None = None
    default_terms: Iterable[str] = field(default_factory=lambda: DEFAULT_BANNED_TERMS)

    def load_terms(self) -> list[str]:
        terms: set[str] = set()
        for source in (
            self.personal_list or Path.home() / ".banned-words",
            self.repo_list or self.root / ".banned-words",
        ):
            terms.update(_read_terms(source))
        terms.update(term.strip() for term in self.default_terms if term.strip())
        return sorted(terms, key=lambda s: s.lower())

    def scan(self, lines: Sequence[str]) -> list[str]:
        terms = self.load_terms()
        matches: list[str] = []
        joined = "\n".join(lines)
        lower_text = joined.lower()
        for term in terms:
            if term.lower() in lower_text:
                matches.append(term)
        return matches


def _read_terms(path: Path) -> set[str]:
    if not path.exists():
        return set()
    items: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        term = raw.strip()
        if not term or term.startswith("#"):
            continue
        items.add(term)
    return items
