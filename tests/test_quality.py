# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the repository quality checker and CLI."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.cli.core.utils import filter_pyqa_lint_paths
from pyqa.compliance.quality import (
    QualityChecker,
    QualityCheckerOptions,
    check_commit_message,
)
from pyqa.core.config.loader import ConfigLoader
from pyqa.linting.quality import evaluate_quality_checks, run_pyqa_python_hygiene_linter, run_python_hygiene_linter
from pyqa.linting.suppressions import SuppressionRegistry
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


def _build_hygiene_state(root: Path, files: list[Path]) -> SimpleNamespace:
    return SimpleNamespace(
        root=root,
        options=SimpleNamespace(
            target_options=SimpleNamespace(
                root=root,
                paths=list(files),
                dirs=[],
                exclude=[],
                paths_from_stdin=False,
            ),
        ),
        meta=SimpleNamespace(show_valid_suppressions=False),
        logger=None,
        suppressions=SuppressionRegistry(root),
    )


def _build_hygiene_state(root: Path, files: list[Path]) -> SimpleNamespace:
    return SimpleNamespace(
        root=root,
        options=SimpleNamespace(
            target_options=SimpleNamespace(
                root=root,
                paths=list(files),
                dirs=[],
                exclude=[],
                paths_from_stdin=False,
            ),
        ),
        meta=SimpleNamespace(show_valid_suppressions=False),
        logger=None,
    )


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
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=[target],
            checks={"license"},
        ),
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
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=[target],
            checks={"license"},
        ),
    )
    result = checker.run()

    assert result.exit_code() == 0


def test_quality_checker_fix_mode_adds_headers(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "script.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    checker = QualityChecker(
        root=tmp_path,
        quality=config.quality,
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=[target],
            checks={"license"},
        ),
    )
    result = checker.run(fix=True)

    assert result.exit_code() == 0
    content = target.read_text(encoding="utf-8")
    assert content.splitlines()[0] == "# SPDX-License-Identifier: MIT"
    current_year = datetime.now().year
    if current_year == 2025:
        expected_notice = "# Copyright (c) 2025 Blackcat Informatics® Inc."
    else:
        expected_notice = f"# Copyright (c) 2025-{current_year} Blackcat Informatics® Inc."
    assert expected_notice in content


def test_quality_checker_fix_mode_conflicting_license(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "example.js"
    target.write_text(
        """// SPDX-License-Identifier: Apache-2.0
console.log('test');
""",
        encoding="utf-8",
    )

    config = _load_quality_config(tmp_path)
    checker = QualityChecker(
        root=tmp_path,
        quality=config.quality,
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=[target],
            checks={"license"},
        ),
    )
    result = checker.run(fix=True)

    assert result.exit_code() == 1
    assert any("Apache-2.0" in issue.message for issue in result.errors)
    content = target.read_text(encoding="utf-8")
    assert "Apache-2.0" in content


def test_schema_check_reports_outdated_file(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    schema_file = tmp_path / "ref_docs" / "tool-schema.json"
    schema_file.write_text("{}\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    checker = QualityChecker(
        root=tmp_path,
        quality=config.quality,
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=[],
            checks={"schema"},
        ),
    )
    result = checker.run()

    assert result.errors
    assert any("Schema documentation out of date" in issue.message for issue in result.errors)


def test_python_hygiene_warns_on_main_guard(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "pkg" / "module.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "if __name__ == '__main__':\n    print('debug')\n",
        encoding="utf-8",
    )

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    state = _build_hygiene_state(tmp_path, [target])
    report = run_python_hygiene_linter(state, emit_to_logger=False, config=config)

    messages = "\n".join(d.message for d in report.outcome.diagnostics)
    assert "__main__" in messages


def test_python_hygiene_warns_on_debug_import(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "package" / "util.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("import pdb\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    state = _build_hygiene_state(tmp_path, [target])
    report = run_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert any("Debug import" in diagnostic.message for diagnostic in report.outcome.diagnostics)


def test_python_hygiene_broad_exception_requires_comment(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "module.py"
    target.write_text(
        "try:\n    pass\nexcept Exception:\n    handle()\n",
        encoding="utf-8",
    )

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    state = _build_hygiene_state(tmp_path, [target])
    report = run_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert any("Exception" in diagnostic.message for diagnostic in report.outcome.diagnostics)


def test_python_hygiene_allows_justified_broad_exception(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "module.py"
    target.write_text(
        "try:\n    pass\nexcept Exception:  # handled centrally for transactional rollback safety\n    rollback()\n",
        encoding="utf-8",
    )

    config = _load_quality_config(tmp_path)
    state = _build_hygiene_state(tmp_path, [target])
    report = run_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert not any("Exception" in diagnostic.message for diagnostic in report.outcome.diagnostics)


def test_pyqa_python_hygiene_flags_system_exit(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "module.py"
    target.write_text("raise SystemExit(1)\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    state = _build_hygiene_state(tmp_path, [target])
    report = run_pyqa_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert any("system-exit" in diagnostic.code for diagnostic in report.outcome.diagnostics)


def test_pyqa_python_hygiene_skips_cli_system_exit(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "cli" / "commands" / "tool.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("raise SystemExit(0)\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    state = _build_hygiene_state(tmp_path, [target])
    report = run_pyqa_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert report.outcome.diagnostics == []


def test_pyqa_python_hygiene_flags_print(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "library.py"
    target.write_text("print('debug')\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    state = _build_hygiene_state(tmp_path, [target])
    report = run_pyqa_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert any("print" in diagnostic.message for diagnostic in report.outcome.diagnostics)


def test_pyqa_python_hygiene_allows_console_print(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "library.py"
    target.write_text(
        "from pyqa.core.logging.public import get_console_manager\n"
        "console = get_console_manager().get(color=True, emoji=True)\n"
        "console.print('debug')\n",
        encoding="utf-8",
    )

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    state = _build_hygiene_state(tmp_path, [target])
    report = run_pyqa_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert report.outcome.diagnostics == []


def test_pyqa_python_hygiene_allows_rich_print(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "library.py"
    target.write_text("import rich\nrich.print('debug')\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    state = _build_hygiene_state(tmp_path, [target])
    report = run_pyqa_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert report.outcome.diagnostics == []


def test_pyqa_python_hygiene_ignores_system_exit_literals(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "library.py"
    target.write_text(
        'message = "avoid raise SystemExit in modules"\n' "check = 'os._exit' in message\n",
        encoding="utf-8",
    )

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    state = _build_hygiene_state(tmp_path, [target])
    report = run_pyqa_python_hygiene_linter(state, emit_to_logger=False, config=config)

    assert report.outcome.diagnostics == []


def test_evaluate_quality_checks_pyqa_overrides(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "module.py"
    target.write_text("raise SystemExit(1)\nprint('debug')\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    request = QualityCheckRequest(
        root=tmp_path,
        config=config,
        checks=("python",),
        files=(target,),
        fix=False,
    )
    result = evaluate_quality_checks(request)
    codes = {issue.check for issue in result.issues}
    assert "python-hygiene:system-exit" in codes
    assert "python-hygiene:print" in codes


def test_evaluate_quality_checks_pyqa_overrides(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "module.py"
    target.write_text("raise SystemExit(1)\nprint('debug')\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    config.severity.sensitivity = "maximum"
    config.quality.enforce_in_lint = True
    result = run_pyqa_python_hygiene_linter(
        _build_hygiene_state(tmp_path, [target]),
        emit_to_logger=False,
        config=config,
    )
    codes = {diagnostic.code for diagnostic in result.outcome.diagnostics}
    assert "pyqa-python-hygiene:python-hygiene:system-exit" in codes
    assert any("print" in diagnostic.message for diagnostic in result.outcome.diagnostics)


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
            "--root",
            str(tmp_path),
            "--no-schema",
            "--no-emoji",
            str(target),
        ],
    )

    assert result.exit_code == 1
    assert "Missing SPDX" in result.stdout


def test_cli_fix_mode_updates_file(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    target = tmp_path / "main.py"
    target.write_text("print('cli')\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "check-quality",
            "--root",
            str(tmp_path),
            "--no-schema",
            "--no-emoji",
            "--fix",
            str(target),
        ],
    )

    assert result.exit_code == 0
    content = target.read_text(encoding="utf-8")
    assert content.startswith("# SPDX-License-Identifier: MIT\n")


def test_license_check_skips_json_and_txt(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    json_target = tmp_path / "data.json"
    json_target.write_text('{\n  "value": 42\n}\n', encoding="utf-8")
    text_target = tmp_path / "notes.txt"
    text_target.write_text("reminder\n", encoding="utf-8")

    config = _load_quality_config(tmp_path)
    checker = QualityChecker(
        root=tmp_path,
        quality=config.quality,
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=[json_target, text_target],
            checks={"license"},
        ),
    )
    result = checker.run()

    assert result.exit_code() == 0
    assert not result.issues


def test_check_quality_ignores_pyqa_lint_directory(tmp_path: Path) -> None:
    _write_repo_layout(tmp_path)
    pyqa_lint_dir = tmp_path / "pyqa_lint"
    pyqa_lint_dir.mkdir()
    (pyqa_lint_dir / "sample.py").write_text("print('hi')\n", encoding="utf-8")

    runner = CliRunner()
    kept, ignored = filter_pyqa_lint_paths([pyqa_lint_dir / "sample.py"], tmp_path)
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
            str(pyqa_lint_dir / "sample.py"),
        ],
    )

    output = result.stdout + result.stderr
    assert result.exit_code == 0
    assert "'pyqa_lint' directories are skipped" in output
    assert "No files to check." in output
    assert "Missing SPDX" not in output
