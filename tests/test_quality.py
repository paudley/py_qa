# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the repository quality checker and CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.cli.utils import filter_py_qa_paths
from pyqa.config_loader import ConfigLoader
from pyqa.quality import QualityChecker, check_commit_message
from pyqa.tools.settings import tool_setting_schema_as_dict


def _write_repo_layout(root: Path) -> None:
    (root / "ref_docs").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.0.1"
license = { file = "LICENSE" }
authors = [{ name = "Blackcat Informatics® Inc." }]

[tool.pyqa.license]
spdx = "MIT"
year = "2025"
copyright = "Blackcat Informatics® Inc."
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text(
        """MIT License

Copyright (c) 2025 Blackcat Informatics® Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
""",
        encoding="utf-8",
    )
    expected_schema = json.dumps(tool_setting_schema_as_dict(), indent=2, sort_keys=True) + "\n"
    (root / "ref_docs" / "tool-schema.json").write_text(
        expected_schema,
        encoding="utf-8",
    )


def _load_quality_config(root: Path):
    loader = ConfigLoader.for_root(root)
    return loader.load()


def test_quality_checker_missing_spdx(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "src.py"
    target.write_text(
        "print('hello world')\n",
        encoding="utf-8",
    )

    config = _load_quality_config(tmp_path)
    checker = QualityChecker(
        root=tmp_path,
        quality=config.quality,
        license_overrides=config.license,
        files=[target],
        checks={"license"},
    )
    result = checker.run()

    assert result.errors
    assert any("Missing SPDX" in issue.message for issue in result.errors)


def test_quality_checker_accepts_valid_header(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "src.py"
    target.write_text(
        """# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
print('ok')
""",
        encoding="utf-8",
    )

    config = _load_quality_config(tmp_path)
    checker = QualityChecker(
        root=tmp_path,
        quality=config.quality,
        license_overrides=config.license,
        files=[target],
        checks={"license"},
    )
    result = checker.run()

    assert result.exit_code() == 0


def test_schema_check_reports_outdated_file(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    schema_file = tmp_path / "ref_docs" / "tool-schema.json"
    schema_file.write_text("{}\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    checker = QualityChecker(
        root=tmp_path,
        quality=config.quality,
        license_overrides=config.license,
        files=[],
        checks={"schema"},
    )
    result = checker.run()

    assert result.errors
    assert any("Schema documentation out of date" in issue.message for issue in result.errors)


def test_commit_message_validation(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    message = tmp_path / "commit.msg"
    message.write_text("fix: add feature\n\nDetails line\n", encoding="utf-8")

    result = check_commit_message(tmp_path, message)
    assert result.exit_code() == 0

    bad = tmp_path / "bad.msg"
    bad.write_text("Update stuff\n", encoding="utf-8")
    failure = check_commit_message(tmp_path, bad)
    assert failure.exit_code() == 1
    assert any("Conventional" in issue.message for issue in failure.errors)


def test_cli_reports_license_error(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "src.py"
    target.write_text("print('oops')\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "check-quality",
            str(target),
            "--root",
            str(tmp_path),
            "--no-schema",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 1
    assert "Missing SPDX" in result.stdout


def test_check_quality_ignores_py_qa_directory(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    py_qa_dir = tmp_path / "py_qa"
    py_qa_dir.mkdir()
    (py_qa_dir / "sample.py").write_text("print('hi')\n", encoding="utf-8")

    runner = CliRunner()
    kept, ignored = filter_py_qa_paths([py_qa_dir / "sample.py"], tmp_path)
    assert not kept
    assert ignored
    result = runner.invoke(
        app,
        [
            "check-quality",
            "--root",
            str(tmp_path),
            "--no-schema",
            "--no-emoji",
            str(py_qa_dir / "sample.py"),
        ],
    )

    output = result.stdout + result.stderr
    assert result.exit_code == 0
    assert "'py_qa' directories are skipped" in output
    assert "No files to check." in output
    assert "Missing SPDX" not in output
