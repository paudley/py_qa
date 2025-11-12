# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Unit tests for the spaCy loader helper."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pyqa.analysis.spacy import loader as spacy_loader


@pytest.fixture(autouse=True)
def _reset_loader_state() -> None:
    spacy_loader._STATE.language_cache.clear()
    spacy_loader._STATE.loader = spacy_loader._SENTINEL
    yield
    spacy_loader._STATE.language_cache.clear()
    spacy_loader._STATE.loader = spacy_loader._SENTINEL


def test_load_language_downloads_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    state = SimpleNamespace(installed=False, attempts=0)

    def fake_loader(force: bool = False):
        assert isinstance(force, bool)
        def _load(model_name: str):
            state.attempts += 1
            if not state.installed:
                raise OSError("missing model")

            def _nlp(text: str) -> str:
                return f"{model_name}:{text}"

            return _nlp

        return _load

    def fake_download(model: str) -> bool:
        assert model == "en_core_web_sm"
        state.installed = True
        return True

    monkeypatch.setattr(spacy_loader, "_resolve_loader", fake_loader)
    monkeypatch.setattr(spacy_loader, "_download_spacy_model", fake_download)

    language = spacy_loader.load_language("en_core_web_sm")

    assert state.attempts >= 2
    assert language("text") == "en_core_web_sm:text"


def test_load_language_warns_when_download_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_loader(force: bool = False):
        assert isinstance(force, bool)
        def _load(_model: str):
            raise OSError("still missing")

        return _load

    details: list[tuple[str, str]] = []

    def capture_warning(model: str, detail: str) -> None:
        details.append((model, detail))

    monkeypatch.setattr(spacy_loader, "_resolve_loader", failing_loader)
    monkeypatch.setattr(spacy_loader, "_download_spacy_model", lambda model: False)
    monkeypatch.setattr(spacy_loader, "_warn_spacy_unavailable", capture_warning)

    language = spacy_loader.load_language("en_core_web_sm")

    assert language is None
    assert details and details[0][0] == "en_core_web_sm"
    assert "still missing" in details[0][1]


def test_load_language_warns_when_spacy_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    details: list[tuple[str, str]] = []

    def capture_warning(model: str, detail: str) -> None:
        details.append((model, detail))

    monkeypatch.setattr(spacy_loader, "_resolve_loader", lambda force=False: None)
    monkeypatch.setattr(spacy_loader, "_warn_spacy_unavailable", capture_warning)

    language = spacy_loader.load_language("en_core_web_sm")

    assert language is None
    assert details and details[0][0] == "en_core_web_sm"
    assert "spaCy is not installed" in details[0][1]
