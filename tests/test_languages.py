# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for language detection heuristics."""

# pylint: disable=missing-function-docstring

from pathlib import Path

from pyqa.languages import detect_languages


def test_detect_languages_by_extension(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    py_file = src / "main.py"
    ts_file = src / "app.ts"
    py_file.write_text("print('hi')\n", encoding="utf-8")
    ts_file.write_text("console.log('hi')\n", encoding="utf-8")

    languages = detect_languages(tmp_path, [py_file, ts_file])

    assert "python" in languages
    assert "javascript" in languages


def test_detect_languages_by_marker(tmp_path: Path) -> None:
    marker = tmp_path / "package.json"
    marker.write_text("{}", encoding="utf-8")

    languages = detect_languages(tmp_path, [])

    assert languages == {"javascript"}
