# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for filesystem and git discovery strategies."""

import subprocess
from pathlib import Path

from pyqa.config import FileDiscoveryConfig
from pyqa.discovery.filesystem import FilesystemDiscovery
from pyqa.discovery.git import GitDiscovery


def test_filesystem_discovery_respects_excludes(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / "app").mkdir()
    included = project_root / "app" / "main.py"
    included.write_text("print('hello')\n", encoding="utf-8")

    node_modules = project_root / "node_modules"
    node_modules.mkdir()
    (node_modules / "ignored.js").write_text("console.log('ignore');\n", encoding="utf-8")

    excluded_dir = project_root / "app" / "generated"
    excluded_dir.mkdir()
    (excluded_dir / "machine.py").write_text("# generated\n", encoding="utf-8")

    cfg = FileDiscoveryConfig(
        roots=[Path()],
        excludes=[Path("app/generated")],
    )

    discovery = FilesystemDiscovery()
    files = list(discovery.discover(cfg, project_root))

    assert included.resolve() in files
    assert not any(path.name == "ignored.js" for path in files)
    assert not any(path.name == "machine.py" for path in files)


def test_filesystem_discovery_skips_embedded_pyqa_lint(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / "app").mkdir()
    keep = project_root / "app" / "keep.py"
    keep.write_text("print('keep')\n", encoding="utf-8")

    vendor_pyqa_lint = project_root / "vendor" / "pyqa_lint"
    vendor_pyqa_lint.mkdir(parents=True)
    ignored = vendor_pyqa_lint / "ignored.py"
    ignored.write_text("print('ignore')\n", encoding="utf-8")

    cfg = FileDiscoveryConfig(roots=[Path()])
    discovery = FilesystemDiscovery()
    files = list(discovery.discover(cfg, project_root))

    assert keep.resolve() in files
    assert ignored.resolve() not in files


def test_filesystem_discovery_includes_pyqa_lint_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "pyqa_lint"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text('[project]\nname = "pyqa_lint"\n', encoding="utf-8")
    tracked = workspace / "tracked.py"
    tracked.write_text("print('tracked')\n", encoding="utf-8")

    cfg = FileDiscoveryConfig(roots=[Path()])
    discovery = FilesystemDiscovery()
    files = list(discovery.discover(cfg, workspace))

    assert tracked.resolve() in files


def test_filesystem_discovery_respects_limit_to(tmp_path: Path) -> None:
    project_root = tmp_path
    target_dir = project_root / "target"
    other_dir = project_root / "other"
    target_dir.mkdir()
    other_dir.mkdir()

    inside = target_dir / "inside.py"
    inside.write_text("print('inside')\n", encoding="utf-8")

    outside = other_dir / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")

    cfg = FileDiscoveryConfig(
        roots=[Path("target")],
        limit_to=[Path("target")],
    )

    discovery = FilesystemDiscovery()
    files = list(discovery.discover(cfg, project_root))

    assert inside.resolve() in files
    assert outside.resolve() not in files


def test_git_discovery_limit_to_filters_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target_dir = repo / "pkg"
    other_dir = repo / "docs"
    target_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)

    inside = target_dir / "module.py"
    outside = other_dir / "notes.md"
    inside.write_text("print('v1')\n", encoding="utf-8")
    outside.write_text("outside v1\n", encoding="utf-8")

    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["git", "config", "user.name", "PyQATest"],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "config", "user.email", "pyqa@example.com"],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    inside.write_text("print('v2')\n", encoding="utf-8")
    outside.write_text("outside v2\n", encoding="utf-8")

    cfg = FileDiscoveryConfig(
        roots=[Path()],
        limit_to=[Path("pkg")],
        changed_only=True,
        include_untracked=True,
    )

    discovery = GitDiscovery()
    files = list(discovery.discover(cfg, repo))

    assert inside.resolve() in files
    assert all(repo_path.is_relative_to(target_dir) for repo_path in files)
    assert outside.resolve() not in files
