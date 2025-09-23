from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest
import subprocess

from pyqa.tool_env import GO_BIN_DIR, RUST_BIN_DIR, CommandPreparer, PreparedCommand, desired_version
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


def test_go_runtime_installs_when_system_too_old(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _make_tool(
        name="kube-linter",
        runtime="go",
        package="golang.stackrox.io/kube-linter/cmd/kube-linter@v0.7.6",
        min_version="0.7.6",
        version_command=("kube-linter", "version"),
    )

    def fake_which(cmd: str) -> str | None:
        if cmd == "kube-linter":
            return "/usr/bin/kube-linter"
        if cmd == "go":
            return "/usr/bin/go"
        return None

    monkeypatch.setattr("pyqa.tool_env.shutil.which", fake_which)

    preparer = CommandPreparer()

    def fake_capture(command: Sequence[str], *, env=None) -> str | None:  # noqa: ANN001
        if command[0] == "kube-linter":
            return "0.7.5"
        return None

    monkeypatch.setattr(preparer._versions, "capture", fake_capture)  # type: ignore[attr-defined]

    fake_binary = tmp_path / "go" / "bin" / "kube-linter"
    fake_binary.parent.mkdir(parents=True, exist_ok=True)
    fake_binary.write_text("#!/bin/sh\nexit 0\n")
    fake_binary.chmod(0o755)

    def fake_install(self, tool_obj: Tool, binary_name: str) -> Path:  # noqa: ANN001
        return fake_binary

    monkeypatch.setattr("pyqa.tool_env.GoRuntime._ensure_local_tool", fake_install)

    result = preparer.prepare(
        tool=tool,
        base_cmd=("kube-linter", "lint"),
        root=tmp_path,
        cache_dir=tmp_path,
        system_preferred=True,
        use_local_override=False,
    )

    assert result.source == "local"
    assert result.cmd[0] == str(fake_binary)
    assert str(GO_BIN_DIR) in result.env.get("PATH", "")


def test_go_runtime_prefers_system_when_version_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _make_tool(
        name="kube-linter",
        runtime="go",
        package="golang.stackrox.io/kube-linter/cmd/kube-linter@v0.7.6",
        min_version="0.7.6",
        version_command=("kube-linter", "version"),
    )

    def fake_which(cmd: str) -> str | None:
        if cmd in {"kube-linter", "go"}:
            return f"/usr/bin/{cmd}"
        return None

    monkeypatch.setattr("pyqa.tool_env.shutil.which", fake_which)

    preparer = CommandPreparer()

    def fake_capture(command: Sequence[str], *, env=None) -> str | None:  # noqa: ANN001
        if command[0] == "kube-linter":
            return "0.7.6"
        return None

    monkeypatch.setattr(preparer._versions, "capture", fake_capture)  # type: ignore[attr-defined]

    def fail_install(self, tool_obj: Tool, binary_name: str) -> Path:  # noqa: ANN001
        raise AssertionError("Local go install should not occur")

    monkeypatch.setattr("pyqa.tool_env.GoRuntime._ensure_local_tool", fail_install)

    result = preparer.prepare(
        tool=tool,
        base_cmd=("kube-linter", "lint"),
        root=tmp_path,
        cache_dir=tmp_path,
        system_preferred=True,
        use_local_override=False,
    )

    assert result.source == "system"
    assert result.cmd[0] == "kube-linter"


def test_rust_runtime_installs_when_system_too_old(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _make_tool(
        name="dotenv-linter",
        runtime="rust",
        package="dotenv-linter",
        min_version="3.3.0",
        version_command=("dotenv-linter", "--version"),
    )

    rust_cache = tmp_path / "rust-cache"
    monkeypatch.setattr("pyqa.tool_env.RUST_CACHE_DIR", rust_cache)
    monkeypatch.setattr("pyqa.tool_env.RUST_BIN_DIR", rust_cache / "bin")
    monkeypatch.setattr("pyqa.tool_env.RUST_META_DIR", rust_cache / "meta")
    monkeypatch.setattr("pyqa.tool_env.RUST_WORK_DIR", rust_cache / "work")

    def fake_which(cmd: str) -> str | None:
        if cmd == "dotenv-linter":
            return "/usr/bin/dotenv-linter"
        if cmd == "cargo":
            return "/usr/bin/cargo"
        return None

    monkeypatch.setattr("pyqa.tool_env.shutil.which", fake_which)

    preparer = CommandPreparer()

    def fake_capture(command: Sequence[str], *, env=None) -> str | None:  # noqa: ANN001
        if command[0] == "dotenv-linter":
            return "2.9.0"
        return None

    monkeypatch.setattr(preparer._versions, "capture", fake_capture)  # type: ignore[attr-defined]

    fake_binary = tmp_path / "rust" / "bin" / "dotenv-linter"
    fake_binary.parent.mkdir(parents=True, exist_ok=True)
    fake_binary.write_text("#!/bin/sh\nexit 0\n")
    fake_binary.chmod(0o755)

    def fake_install(self, tool_obj: Tool, binary_name: str) -> Path:  # noqa: ANN001
        return fake_binary

    monkeypatch.setattr("pyqa.tool_env.RustRuntime._ensure_local_tool", fake_install)

    result = preparer.prepare(
        tool=tool,
        base_cmd=("dotenv-linter",),
        root=tmp_path,
        cache_dir=tmp_path,
        system_preferred=True,
        use_local_override=False,
    )

    assert result.source == "local"
    assert result.cmd[0] == str(fake_binary)
    assert str(RUST_BIN_DIR) not in result.env.get("PATH", "")


def test_rust_runtime_prefers_system_when_version_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _make_tool(
        name="dotenv-linter",
        runtime="rust",
        package="dotenv-linter",
        min_version="3.3.0",
        version_command=("dotenv-linter", "--version"),
    )

    rust_cache = tmp_path / "rust-cache"
    monkeypatch.setattr("pyqa.tool_env.RUST_CACHE_DIR", rust_cache)
    monkeypatch.setattr("pyqa.tool_env.RUST_BIN_DIR", rust_cache / "bin")
    monkeypatch.setattr("pyqa.tool_env.RUST_META_DIR", rust_cache / "meta")
    monkeypatch.setattr("pyqa.tool_env.RUST_WORK_DIR", rust_cache / "work")

    def fake_which(cmd: str) -> str | None:
        if cmd in {"dotenv-linter", "cargo"}:
            return f"/usr/bin/{cmd}"
        return None

    monkeypatch.setattr("pyqa.tool_env.shutil.which", fake_which)

    preparer = CommandPreparer()

    def fake_capture(command: Sequence[str], *, env=None) -> str | None:  # noqa: ANN001
        if command[0] == "dotenv-linter":
            return "3.3.1"
        return None

    monkeypatch.setattr(preparer._versions, "capture", fake_capture)  # type: ignore[attr-defined]

    def fail_install(self, tool_obj: Tool, binary_name: str) -> Path:  # noqa: ANN001
        raise AssertionError("Local rust install should not occur")

    monkeypatch.setattr("pyqa.tool_env.RustRuntime._ensure_local_tool", fail_install)

    result = preparer.prepare(
        tool=tool,
        base_cmd=("dotenv-linter",),
        root=tmp_path,
        cache_dir=tmp_path,
        system_preferred=True,
        use_local_override=False,
    )

    assert result.source == "system"
    assert result.cmd[0] == "dotenv-linter"


def test_rust_runtime_install_rustup_component(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _make_tool(
        name="cargo-clippy",
        runtime="rust",
        package="rustup:clippy",
        min_version="1.81.0",
        version_command=("cargo", "--version"),
    )

    rust_cache = tmp_path / "rust-cache"
    monkeypatch.setattr("pyqa.tool_env.RUST_CACHE_DIR", rust_cache)
    monkeypatch.setattr("pyqa.tool_env.RUST_BIN_DIR", rust_cache / "bin")
    monkeypatch.setattr("pyqa.tool_env.RUST_META_DIR", rust_cache / "meta")
    monkeypatch.setattr("pyqa.tool_env.RUST_WORK_DIR", rust_cache / "work")

    def fake_which(cmd: str) -> str | None:
        if cmd == "cargo":
            return "/usr/bin/cargo"
        if cmd == "rustup":
            return "/usr/bin/rustup"
        return None

    monkeypatch.setattr("pyqa.tool_env.shutil.which", fake_which)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("pyqa.tool_env.subprocess.run", fake_run)

    preparer = CommandPreparer()

    def fake_capture(command: Sequence[str], *, env=None) -> str | None:  # noqa: ANN001
        if command[0] == "cargo":
            return "cargo 1.81.0"
        return None

    monkeypatch.setattr(preparer._versions, "capture", fake_capture)  # type: ignore[attr-defined]

    result = preparer.prepare(
        tool=tool,
        base_cmd=("cargo", "clippy", "--message-format=json"),
        root=tmp_path,
        cache_dir=tmp_path,
        system_preferred=True,
        use_local_override=False,
    )

    assert result.cmd[0] == "/usr/bin/cargo"
    assert any(cmd[:3] == ["rustup", "component", "add"] for cmd in calls)
