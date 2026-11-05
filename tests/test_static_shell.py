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
