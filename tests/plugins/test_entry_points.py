from __future__ import annotations

from importlib import metadata
from typing import Any

import pytest

from pyqa.plugins import (
    CATALOG_PLUGIN_GROUP,
    CLI_PLUGIN_GROUP,
    DIAGNOSTICS_PLUGIN_GROUP,
    load_all_plugins,
    load_catalog_plugins,
    load_cli_plugins,
    load_diagnostics_plugins,
)


class _FakeEntryPoint:
    def __init__(self, value: Any) -> None:
        self._value = value

    def load(self) -> Any:
        return self._value


def test_load_catalog_plugins_handles_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata, "entry_points", lambda: {})
    assert load_catalog_plugins() == ()


def test_load_cli_plugins_filters_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadEntryPoint:
        def load(self) -> None:
            raise RuntimeError("boom")

    entries = {
        CLI_PLUGIN_GROUP: (_BadEntryPoint(), _FakeEntryPoint(lambda: 42)),
    }
    monkeypatch.setattr(metadata, "entry_points", lambda: entries)
    plugins = load_cli_plugins()
    assert len(plugins) == 1
    assert plugins[0]() == 42


def test_load_diagnostics_plugins_select_api(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Container:
        def select(self, *, group: str):
            if group == DIAGNOSTICS_PLUGIN_GROUP:
                return (_FakeEntryPoint("diagnostic"),)
            return ()

    monkeypatch.setattr(metadata, "entry_points", lambda: _Container())
    plugins = load_diagnostics_plugins()
    assert plugins == ("diagnostic",)


def test_load_all_plugins_combines_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = {
        CATALOG_PLUGIN_GROUP: (_FakeEntryPoint("catalog"),),
        CLI_PLUGIN_GROUP: (_FakeEntryPoint("cli"),),
        DIAGNOSTICS_PLUGIN_GROUP: (_FakeEntryPoint("diag"),),
    }
    monkeypatch.setattr(metadata, "entry_points", lambda: entries)
    bundle = load_all_plugins()
    assert bundle.catalog == ("catalog",)
    assert bundle.cli == ("cli",)
    assert bundle.diagnostics == ("diag",)
