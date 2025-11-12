# SPDX-License-Identifier: MIT
"""Safety checks for repository artefacts."""

from __future__ import annotations

from pathlib import Path


def test_repo_artifacts_do_not_expose_absolute_root_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1].resolve()
    root_variants = {str(repo_root), repo_root.as_posix()}
    targets = [repo_root / "tooling" / "catalog" / "docs", repo_root / "reorg" / "artifacts"]

    for target in targets:
        if not target.exists():
            continue
        for path in target.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for variant in root_variants:
                assert variant not in text, f"Absolute repo path leaked in {path}"
