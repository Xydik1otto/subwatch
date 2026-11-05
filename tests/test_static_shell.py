# Static shell: favicon, OG meta, PWA manifest/service worker wiring.
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_favicon_served():
    r = client.get("/static/favicon.svg")
    assert r.status_code == 200
    assert "image/svg" in r.headers["content-type"]
    assert b"<svg" in r.content


def test_index_has_favicon_and_og_meta():
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'rel="icon"' in html and "/static/favicon.svg" in html
    assert 'property="og:title"' in html
    assert 'property="og:description"' in html
    assert "viewport" in html


def test_index_has_total_card_emoji_and_filter():
    html = client.get("/").text
    # виділена картка total
    assert "card-total" in html
    # emoji-лого за назвою/тегом + фолбек
    assert "function emoji(sub)" in html
    assert "'📦'" in html
    # фільтр paused/active
    assert 'data-f="active"' in html
    assert 'data-f="paused"' in html
    assert "data-f=\"all\"" in html
