# README bilingual: UA README.md + English README.en.md cross-linked.
import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


def test_readme_en_exists_and_links_uk():
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "[🇺🇦 Українська](README.md)" in en
    assert "Local-first subscription tracker" in en


def test_readme_uk_links_en():
    uk = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "README.en.md" in uk


def test_readme_en_covers_v1_features():
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    for feature in ("Cancel assistant", "Price-change alerts", "Family mode",
                    "export", "UA/EN"):
        assert feature.lower() in en.lower(), feature


def test_no_russian_localization():
    """Political decision of the owner: Russian locale must never be added."""
    readme_en = (ROOT / "README.en.md").read_text(encoding="utf-8").lower()
    readme_uk = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    for text in (readme_en, readme_uk):
        assert "russian" not in text.replace("no russian localization", "")
    # no ru.json / ru_RU locale files anywhere in the repo
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".md", ".py", ".html", ".js"):
            name = p.name.lower()
            assert not (name.startswith("ru") and "readme" not in name
                        and "requirement" not in name), p


def test_version_badges_consistent_across_readmes():
    import re
    uk = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    def badge(text):
        m = re.search(r"version-(\d+\.\d+\.\d+)-orange", text)
        assert m, text[:200]
        return m.group(1)
    assert badge(uk) == badge(en)
