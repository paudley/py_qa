from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

from pyqa.tool_env import CommandPreparer, PreparedCommand, desired_version
from pyqa.tools.base import Tool


def _make_tool(
    *,
    name: str,
    runtime: str,
    package: str | None = None,
    min_version: str | None = None,
    version_command: Sequence[str] | None = None,
) -> Tool:
    return Tool(
        name=name,
        actions=(),
        runtime=runtime,
        package=package,
        min_version=min_version,
        version_command=tuple(version_command) if version_command else None,
    )


def test_desired_version_prefers_package_spec() -> None:
    tool = _make_tool(
        name="eslint",
        runtime="npm",
        package="eslint@9.13.0",
        min_version="9.0.0",
    )
    assert desired_version(tool) == "9.13.0"

    scoped = _make_tool(
        name="gts",
        runtime="npm",
        package="@google/gts@5.3.1",
    )
    assert desired_version(scoped) == "5.3.1"

    fallback = _make_tool(name="ruff", runtime="python", min_version="0.6.9")
    assert desired_version(fallback) == "0.6.9"

    unknown = _make_tool(name="foo", runtime="binary")
    assert desired_version(unknown) is None


def test_npm_runtime_falls_back_to_local_when_system_version_too_low(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _make_tool(
        name="eslint",
        runtime="npm",
        package="eslint@9.13.0",
        min_version="9.13.0",
        version_command=("eslint", "--version"),
    )

    # System executable is available but reports an older version.
    monkeypatch.setattr("pyqa.tool_env.shutil.which", lambda _: "/usr/bin/eslint")

    preparer = CommandPreparer()

    def fake_capture(command: Sequence[str], *, env=None) -> str | None:  # noqa: ANN001
        return "9.12.0"

    monkeypatch.setattr(preparer._versions, "capture", fake_capture)  # type: ignore[attr-defined]

    prefix = tmp_path / "cache"
    bin_dir = prefix / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    executable = bin_dir / "eslint"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)

    def fake_install(self, tool_obj: Tool):  # noqa: ANN001
        return prefix, "9.13.0"

    monkeypatch.setattr("pyqa.tool_env.NpmRuntime._ensure_local_package", fake_install)

    result = preparer.prepare(
        tool=tool,
        base_cmd=("eslint", "--format", "json"),
        root=tmp_path,
        cache_dir=tmp_path,
        system_preferred=True,
        use_local_override=False,
    )

    assert isinstance(result, PreparedCommand)
    assert result.source == "local"
    assert Path(result.cmd[0]) == executable
    assert result.env["NPM_CONFIG_PREFIX"] == str(prefix)
    assert result.version == "9.13.0"


def test_npm_runtime_prefers_system_when_version_sufficient(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _make_tool(
        name="eslint",
        runtime="npm",
        package="eslint@9.13.0",
        min_version="9.13.0",
        version_command=("eslint", "--version"),
    )

    monkeypatch.setattr("pyqa.tool_env.shutil.which", lambda _: "/usr/bin/eslint")

    preparer = CommandPreparer()

    def fake_capture(command: Sequence[str], *, env=None) -> str | None:  # noqa: ANN001
        return "9.13.1"

    monkeypatch.setattr(preparer._versions, "capture", fake_capture)  # type: ignore[attr-defined]

    def fail_install(self, tool_obj: Tool):  # noqa: ANN001
        raise AssertionError("Local install should not be attempted")

    monkeypatch.setattr("pyqa.tool_env.NpmRuntime._ensure_local_package", fail_install)

    result = preparer.prepare(
        tool=tool,
        base_cmd=("eslint", "--format", "json"),
        root=tmp_path,
        cache_dir=tmp_path,
        system_preferred=True,
        use_local_override=False,
    )

    assert result.source == "system"
    assert result.cmd[0] == "eslint"
    assert result.env == {}
    assert result.version == "9.13.1"
