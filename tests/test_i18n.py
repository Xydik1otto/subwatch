# i18n UA/EN: JSON dictionaries, browser-language autodetect, saved choice.
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "static" / "i18n"
client = TestClient(app)


def _load(lang):
    return json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))


def test_dictionaries_exist_uk_and_en_only():
    files = sorted(p.name for p in I18N.glob("*.json"))
    assert files == ["en.json", "uk.json"]   # жодної російської локалі


def test_dictionaries_cover_same_keys():
    uk, en = _load("uk"), _load("en")
    assert set(uk) == set(en)
    assert set(uk) >= {"app.tagline", "col.name", "col.payer",
                       "card.total", "demo.seed", "badge.cancel_before",
                       "cancel.show", "filter.active"}
    # values differ (real translation, not a copy)
    assert uk["app.tagline"] != en["app.tagline"]
    assert uk["col.name"] == "Назва"
    assert en["col.name"] == "Name"


def test_no_placeholders_lost_in_translation():
    uk, en = _load("uk"), _load("en")
    for d in (uk, en):
        assert "{deadline}" in d["badge.cancel_before"]
        assert "{name}" in d["delete.confirm"]


def test_no_russian_words_in_dictionaries():
    # Russian-only markers that must never appear in the localizations
    ru_markers = ["подписка", "отменить", "язык", "настройки", "загрузить"]
    for lang in ("uk", "en"):
        text = json.dumps(_load(lang), ensure_ascii=False).lower()
        for m in ru_markers:
            assert m not in text, (lang, m)


def test_i18n_files_served():
    for lang in ("uk", "en"):
        r = client.get(f"/static/i18n/{lang}.json")
        assert r.status_code == 200
        assert r.json()["col.name"]


def test_index_has_lang_switch_and_autodetect():
    html = client.get("/").text
    assert 'id="lang-switch"' in html
    assert 'data-lang="uk"' in html and 'data-lang="en"' in html
    assert "subwatch.lang" in html          # збереження вибору
    assert "navigator.language" in html     # авто-детект браузера
    assert "loadI18n" in html


def test_aria_labels_are_translatable():
    html = client.get("/").text
    assert 'data-i18n-aria="lang.aria"' in html
    assert 'data-i18n-aria="alert.badge_aria"' in html
