from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyqa.filesystem import display_relative_path, normalize_path, normalize_path_key


def test_normalize_path_absolute_inside_base(tmp_path: Path) -> None:
    base = tmp_path
    target = base / "src" / "module.py"
    target.parent.mkdir()
    target.touch()

    result = normalize_path(target, base_dir=base)

    assert result == Path("src/module.py")


def test_normalize_path_relative_input(tmp_path: Path) -> None:
    base = tmp_path
    (base / "pkg").mkdir()

    result = normalize_path(Path("pkg/__init__.py"), base_dir=base)

    assert result == Path("pkg/__init__.py")


def test_normalize_path_outside_base_includes_parent_segments(tmp_path: Path) -> None:
    base = tmp_path / "project"
    base.mkdir()
    external = tmp_path / "shared" / "util.py"
    external.parent.mkdir()
    external.touch()

    result = normalize_path(external, base_dir=base)

    expected = Path(os.path.relpath(external, base))
    assert result == expected


def test_normalize_path_expands_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    target = fake_home / "workspace" / "config.toml"
    target.parent.mkdir()
    target.touch()

    result = normalize_path("~/workspace/config.toml", base_dir=fake_home)

    assert result == Path("workspace/config.toml")


def test_normalize_path_rejects_none() -> None:
    with pytest.raises(ValueError):
        normalize_path(None)  # type: ignore[arg-type]


def test_normalize_path_returns_dot_for_base(tmp_path: Path) -> None:
    result = normalize_path(tmp_path, base_dir=tmp_path)

    assert result == Path()


def test_normalize_path_defaults_to_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.touch()
    monkeypatch.chdir(tmp_path)

    result = normalize_path(target)

    assert result == Path("example.py")


def test_normalize_path_key_uses_posix(tmp_path: Path) -> None:
    target = tmp_path / "folder" / "example.py"
    target.parent.mkdir()
    target.touch()

    key = normalize_path_key(target, base_dir=tmp_path)

    assert key == "folder/example.py"


def test_display_relative_path_falls_back_on_absolute(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    external = tmp_path / "other" / "data.txt"
    external.parent.mkdir()
    external.touch()

    display = display_relative_path(external, base)

    assert display.endswith("other/data.txt")
