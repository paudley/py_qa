# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Filesystem scanning utilities for the tooling catalog."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CATALOG_CACHE_FILENAME: Final[str] = "cache.json"


@dataclass(slots=True)
class CatalogScanner:
    """Scan the catalog directory tree for relevant JSON documents."""

    catalog_root: Path

    def tool_documents(self) -> tuple[Path, ...]:
        """Return sorted tool definition document paths.

        Returns:
            tuple[Path, ...]: Sorted tool definition file paths.
        """
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
            if json_path.name == CATALOG_CACHE_FILENAME:
                continue
            paths.append(json_path)
        return tuple(sorted(paths))

    def strategy_documents(self) -> tuple[Path, ...]:
        """Return sorted strategy definition document paths.

        Returns:
            tuple[Path, ...]: Strategy definition file paths.
        """
        strategies_root = self.catalog_root / "strategies"
        if not strategies_root.exists():
            return ()
        paths = [path for path in strategies_root.rglob("*.json") if not path.name.startswith("_")]
        return tuple(sorted(paths))

    def fragment_documents(self) -> tuple[Path, ...]:
        """Return sorted catalog fragment document paths.

        Returns:
            tuple[Path, ...]: Fragment document paths sorted lexicographically.
        """
        strategies_root = self.catalog_root / "strategies"
        docs_root = self.catalog_root / "docs"
        fragments: list[Path] = []
        for json_path in self.catalog_root.rglob("*.json"):
            if strategies_root in json_path.parents:
                continue
            if docs_root in json_path.parents:
                continue
            if not json_path.name.startswith("_"):
                continue
            fragments.append(json_path)
        return tuple(sorted(fragments))

    def documentation_files(self) -> tuple[Path, ...]:
        """Return supporting documentation file paths.

        Returns:
            tuple[Path, ...]: Documentation file paths sorted lexicographically.
        """
        docs_root = self.catalog_root / "docs"
        if not docs_root.exists():
            return ()
        return tuple(sorted(path for path in docs_root.rglob("*") if path.is_file()))

    def catalog_files(self) -> tuple[Path, ...]:
        """Return all catalog file paths contributing to checksums.

        Returns:
            tuple[Path, ...]: Aggregate of all catalog-related file paths.
        """
        paths: list[Path] = []
        paths.extend(self.tool_documents())
        paths.extend(self.fragment_documents())
        paths.extend(self.strategy_documents())
        paths.extend(self.documentation_files())
        return tuple(sorted(_dedupe(paths)))


def _dedupe(paths: Iterable[Path]) -> Sequence[Path]:
    """Return ``paths`` with duplicates removed while preserving order.

    Args:
        paths: Iterable of filesystem paths that may contain duplicates.

    Returns:
        Sequence[Path]: Ordered sequence containing the first instance of each path.
    """
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


__all__ = ["CatalogScanner"]
