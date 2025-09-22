"""Tests for filesystem and git discovery strategies."""

# pylint: disable=missing-function-docstring

from pathlib import Path

from pyqa.config import FileDiscoveryConfig
from pyqa.discovery.filesystem import FilesystemDiscovery


def test_filesystem_discovery_respects_excludes(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / "app").mkdir()
    included = project_root / "app" / "main.py"
    included.write_text("print('hello')\n", encoding="utf-8")

    node_modules = project_root / "node_modules"
    node_modules.mkdir()
    (node_modules / "ignored.js").write_text(
        "console.log('ignore');\n", encoding="utf-8"
    )

    excluded_dir = project_root / "app" / "generated"
    excluded_dir.mkdir()
    (excluded_dir / "machine.py").write_text("# generated\n", encoding="utf-8")

    cfg = FileDiscoveryConfig(
        roots=[Path(".")],
        excludes=[Path("app/generated")],
    )

    discovery = FilesystemDiscovery()
    files = list(discovery.discover(cfg, project_root))

    assert included.resolve() in files
    assert not any(path.name == "ignored.js" for path in files)
    assert not any(path.name == "machine.py" for path in files)
