# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Filesystem scanning utilities for the tooling catalog."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CatalogScanner:
    """Locate catalog documents on disk."""

    catalog_root: Path

    def tool_documents(self) -> tuple[Path, ...]:
        """Return sorted tool definition document paths."""
        docs_root = self.catalog_root / "docs"
        strategies_root = self.catalog_root / "strategies"
        paths: list[Path] = []
        for json_path in self.catalog_root.rglob("*.json"):
            if strategies_root in json_path.parents:
                continue
            if docs_root in json_path.parents:
                continue
            if json_path.name.startswith("_"):
                continue
            if json_path.name == "cache.json":
                continue
            paths.append(json_path)
        return tuple(sorted(paths))

    def strategy_documents(self) -> tuple[Path, ...]:
        """Return sorted strategy definition document paths."""
        strategies_root = self.catalog_root / "strategies"
        if not strategies_root.exists():
            return ()
        paths = [path for path in strategies_root.rglob("*.json") if not path.name.startswith("_")]
        return tuple(sorted(paths))

    def fragment_documents(self) -> tuple[Path, ...]:
        """Return sorted catalog fragment document paths."""
        strategies_root = self.catalog_root / "strategies"
        fragments: list[Path] = []
        for json_path in self.catalog_root.rglob("*.json"):
            if strategies_root in json_path.parents:
                continue
            if (self.catalog_root / "docs") in json_path.parents:
                continue
            if not json_path.name.startswith("_"):
                continue
            fragments.append(json_path)
        return tuple(sorted(fragments))

    def documentation_files(self) -> tuple[Path, ...]:
        """Return supporting documentation file paths."""
        docs_root = self.catalog_root / "docs"
        if not docs_root.exists():
            return ()
        return tuple(sorted(path for path in docs_root.rglob("*") if path.is_file()))

    def catalog_files(self) -> tuple[Path, ...]:
        """Return all catalog file paths contributing to checksums."""
        paths: list[Path] = []
        paths.extend(self.tool_documents())
        paths.extend(self.fragment_documents())
        paths.extend(self.strategy_documents())
        paths.extend(self.documentation_files())
        return tuple(sorted(_dedupe(paths)))


def _dedupe(paths: Iterable[Path]) -> Sequence[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


__all__ = ["CatalogScanner"]
