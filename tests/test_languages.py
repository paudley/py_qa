# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for language detection heuristics."""

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


def test_detect_github_actions_marker(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)

    languages = detect_languages(tmp_path, [])

    assert "github-actions" in languages


def test_detect_cpp_language(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    cpp_file = src / "module.cpp"
    cpp_file.write_text("int main() { return 0; }\n", encoding="utf-8")

    languages = detect_languages(tmp_path, [cpp_file])

    assert "cpp" in languages


def test_detect_toml_language(tmp_path: Path) -> None:
    config = tmp_path / "pyproject.toml"
    config.write_text("[tool]", encoding="utf-8")

    languages = detect_languages(tmp_path, [config])

    assert "toml" in languages
