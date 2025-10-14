# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""BDD tests covering cache root resolution for tool environments."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from pytest_bdd import given, scenarios, then, when

from pyqa.core.environment.tool_env import CommandPreparer, cache_layout
from pyqa.tools.base import Tool

scenarios("tool_env/features/cache_layout.feature")


def _make_tool(name: str = "noop") -> Tool:
    return Tool(name=name, actions=(), runtime="binary")


@pytest.fixture
def workspace_state(tmp_path: Path) -> dict[str, object]:
    return {"tmp_root": tmp_path}


@given("a simulated py_qa repository root", target_fixture="workspace_state")
def given_pyqa_repo(workspace_state: dict[str, object]) -> dict[str, object]:
    tmp_root = workspace_state["tmp_root"]
    repo_root = Path(tmp_root) / "py_qa_repo"
    (repo_root / "src" / "pyqa").mkdir(parents=True)
    workspace_state.update(
        {
            "root": repo_root,
            "cache_dir": repo_root / ".lint-cache",
            "expected_root": repo_root,
            "forbidden_paths": [repo_root / "src" / "pyqa"],
        }
    )
    return workspace_state


@given("an external project workspace", target_fixture="workspace_state")
def given_external_project(workspace_state: dict[str, object]) -> dict[str, object]:
    tmp_root = workspace_state["tmp_root"]
    project_root = Path(tmp_root) / "host_project"
    submodule = project_root / "submodules" / "py_qa" / "src" / "pyqa"
    submodule.mkdir(parents=True)
    workspace_state.update(
        {
            "root": project_root,
            "cache_dir": project_root / ".lint-cache",
            "expected_root": project_root,
            "forbidden_paths": [submodule],
        }
    )
    return workspace_state


@given("a container mount workspace", target_fixture="workspace_state")
def given_container_mount(workspace_state: dict[str, object]) -> dict[str, object]:
    tmp_root = workspace_state["tmp_root"]
    mount_root = Path(tmp_root) / "container_mount"
    readonly = Path(tmp_root) / "readonly_src" / "pyqa"
    readonly.mkdir(parents=True)
    workspace_state.update(
        {
            "root": mount_root,
            "cache_dir": mount_root / ".lint-cache",
            "expected_root": mount_root,
            "forbidden_paths": [readonly],
        }
    )
    return workspace_state


@when("command preparation runs with the repository root")
@when("command preparation runs with the external project root")
@when("command preparation runs with the overridden root")
def when_prepare_with_root(workspace_state: dict[str, object]) -> None:
    _execute_preparer(workspace_state)


@when("command preparation runs from a repository subdirectory but with the repository root")
def when_prepare_from_subdir(workspace_state: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(workspace_state["root"])
    subdir = repo_root / "src" / "pyqa" / "cli"
    subdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(subdir)
    _execute_preparer(workspace_state)


@then("tool caches are created underneath the expected root")
def then_caches_under_expected_root(workspace_state: dict[str, object]) -> None:
    layout = workspace_state["layout"]
    cache_dir = Path(workspace_state["cache_dir"])
    expected_root = Path(workspace_state["expected_root"])

    assert layout.tools_root == cache_dir / "tools"
    assert layout.tools_root.is_dir()
    assert layout.tools_root.is_relative_to(expected_root)
    for directory in (
        layout.uv_dir,
        layout.node_cache_dir,
        layout.go.cache_dir,
        layout.rust.cache_dir,
        layout.perl.cache_dir,
    ):
        assert directory.is_dir()


@then("no tool cache directories exist under the forbidden paths")
def then_no_caches_under_forbidden(workspace_state: dict[str, object]) -> None:
    forbidden_paths = workspace_state.get("forbidden_paths", [])
    for path in forbidden_paths:
        forbidden = Path(path)
        if not forbidden.exists():
            continue
        matches = list(forbidden.rglob(".lint-cache"))
        assert not matches, f"unexpected cache directories under {forbidden}"


def _execute_preparer(workspace_state: dict[str, object]) -> None:
    root = Path(workspace_state["root"])
    cache_dir = Path(workspace_state["cache_dir"])
    tool = workspace_state.setdefault("tool", _make_tool())

    preparer = CommandPreparer()
    result = _legacy_prepare(
        preparer,
        tool=tool,
        base_cmd=(tool.name,),
        root=root,
        cache_dir=cache_dir,
        system_preferred=False,
        use_local_override=False,
    )
    workspace_state["result"] = result
    workspace_state["layout"] = cache_layout(cache_dir)


def _legacy_prepare(preparer: CommandPreparer, **kwargs: object):
    return preparer.prepare_from_mapping(cast(Mapping[str, object], kwargs))


def _legacy_prepare(preparer: CommandPreparer, **kwargs: object):
    return preparer.prepare_from_mapping(cast(Mapping[str, object], kwargs))
