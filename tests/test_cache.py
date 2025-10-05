# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the result cache helpers."""

from pathlib import Path

from pyqa.cache.result_store import CacheRequest, ResultCache
from pyqa.metrics import compute_file_metrics, normalise_path_key
from pyqa.models import Diagnostic, ToolOutcome
from pyqa.severity import Severity


def make_outcome() -> ToolOutcome:
    return ToolOutcome(
        tool="demo",
        action="lint",
        returncode=0,
        stdout="ok",
        stderr="",
        diagnostics=[
            Diagnostic(
                file="src/app.py",
                line=1,
                column=1,
                severity=Severity.WARNING,
                message="demo",
                tool="demo",
                code="X001",
            ),
        ],
    )


def test_result_cache_roundtrip(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".cache"
    cache = ResultCache(cache_dir)
    source = tmp_path / "src.py"
    source.write_text("print('hi')\n", encoding="utf-8")

    outcome = make_outcome()
    cmd = ["demo", str(source)]

    request = CacheRequest(
        tool="demo",
        action="lint",
        command=tuple(cmd),
        files=(source,),
        token="token",
    )

    metrics = {normalise_path_key(source): compute_file_metrics(source)}

    cache.store(
        request,
        outcome=outcome,
        file_metrics=metrics,
    )

    loaded = cache.load(request)

    assert loaded is not None
    assert loaded.outcome.tool == outcome.tool
    assert loaded.outcome.diagnostics[0].severity == Severity.WARNING
    key = normalise_path_key(source)
    assert key in loaded.file_metrics
    assert loaded.file_metrics[key].line_count == 1


def test_result_cache_miss_on_modified_file(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".cache"
    cache = ResultCache(cache_dir)
    source = tmp_path / "src.py"
    source.write_text("print('hi')\n", encoding="utf-8")

    outcome = make_outcome()
    cmd = ["demo", str(source)]

    metrics = {normalise_path_key(source): compute_file_metrics(source)}

    request = CacheRequest(
        tool="demo",
        action="lint",
        command=tuple(cmd),
        files=(source,),
        token="token",
    )

    cache.store(
        request,
        outcome=outcome,
        file_metrics=metrics,
    )

    # Modify file to invalidate cache
    source.write_text("print('bye')\n", encoding="utf-8")

    assert cache.load(request) is None
