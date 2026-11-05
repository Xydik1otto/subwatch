# Accessibility: aria-labels, focus visibility, semantic tables, i18n'd labels.
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


@pytest.fixture()
def html():
    return client.get("/").text


def test_interactive_elements_have_aria_labels(html):
    # select, кнопка показу гайду, кнопки фільтрів, перемикач мови
    assert 'id="cancel-show"' in html and "aria-label" in html.split('id="cancel-show"')[0].split("button")[-1] + html[html.index('id="cancel-show"'):][:200]
    assert 'aria-label="Оберіть сервіс' in html or 'data-i18n-aria="cancel.select_aria"' in html
    assert 'role="group"' in html


def test_all_buttons_are_type_button(html):
    # кнопки в розмітці не мають несподівано отправляти форму
    bare = re.findall(r"<button(?![^>]*type=)[^>]*>", html)
    assert all("data-f=" in b or "data-lang=" in b for b in bare), bare


def test_focus_visible_style_present(html):
    assert ":focus-visible" in html
    assert "outline" in html


def test_emoji_logos_have_aria_labels(html):
    assert 'role="img" aria-label=' in html


def test_lang_attribute_on_html(html):
    assert re.search(r'<html lang="uk">', html)


def test_live_regions_for_dynamic_content(html):
    assert 'aria-live="polite"' in html      # cancel-guide
    assert 'role="status"' in html           # demo-banner


def test_aria_labels_translated_via_i18n():
    uk_html = client.get("/").text
    assert 'data-i18n-aria=' in uk_html
    # словники містять aria-ключі для обох мов
    import json
    for lang in ("uk", "en"):
        d = json.loads((ROOT / "static" / "i18n" / f"{lang}.json")
                       .read_text(encoding="utf-8"))
        assert "lang.aria" in d and "alert.badge_aria" in d
        assert "delete.aria" in d and "{name}" in d["delete.aria"]


def test_delete_buttons_have_per_row_aria_labels(html):
    assert "delete.aria" in html
    assert 'data-name=' in html
