# Open-source hygiene: community files, privacy-leak scan, env-only config.
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


@pytest.fixture(scope="module")
def tracked_files():
    import subprocess
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


# --- community files -------------------------------------------------------------

def test_contributing_md_bilingual_no_russian():
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "## English" in text
    assert "англійська" in text or "English" in text
    # політичне рішення: російська локалізація заборонена, і це задокументовано
    assert "російськ" in text.lower() or "Russian" in text


def test_issue_templates_exist_and_bilingual():
    bug = (ROOT / ".github/ISSUE_TEMPLATE/bug_report.md").read_text(encoding="utf-8")
    feat = (ROOT / ".github/ISSUE_TEMPLATE/feature_request.md").read_text(encoding="utf-8")
    for tpl in (bug, feat):
        assert "**UA**" in tpl and "**EN**" in tpl
        assert "name:" in tpl and "about:" in tpl          # frontmatter
    # privacy-нагадування в обох шаблонах
    assert "Не додавайте" in bug and "Do not include" in bug
    assert "Privacy-check" in feat


def test_security_md_bilingual_with_reporting_path():
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "## English" in text
    assert "Report a vulnerability" in text
    assert "127.0.0.1" in text   # описано, що застосунок локальний


# --- privacy-leak scan -----------------------------------------------------------

def test_no_windows_drive_paths_in_tracked_files(tracked_files):
    r"""Жодних шляхів типу 'диск з проєктами' чи профіль користувача у файлах репозиторію."""
    offenders = []
    for p in tracked_files:
        if p.suffix not in (".py", ".md", ".toml", ".txt", ".html", ".js",
                            ".json", ".yml", ".yaml", ".sh", ".bat", ".ini",
                            ".webmanifest", ".cfg"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if re.search(r"[A-Z]:\\+(?:Users|Projects)", text):
            offenders.append(str(p))
    assert offenders == [], offenders


def test_no_tokens_or_passwords_in_tracked_files(tracked_files):
    pattern = re.compile(
        r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
        r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
        r"[Pp]assword\s*[=:]\s*['\"][^'\"]{4,})",)
    offenders = []
    for p in tracked_files:
        if p.suffix not in (".py", ".md", ".toml", ".txt", ".html", ".js",
                            ".json", ".yml", ".yaml", ".sh"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        m = pattern.search(text)
        # SECURITY.md навмисно згадує 'password' термінологією? — перевіряємо факт
        if m and "password" in m.group(0).lower() and "SECURITY" in str(p):
            continue
        if m:
            offenders.append((str(p), m.group(0)[:30]))
    assert offenders == [], offenders


def test_no_personal_names_or_emails_hardcoded(tracked_files):
    email = re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    offenders = []
    for p in tracked_files:
        if p.suffix not in (".py", ".md", ".toml", ".html", ".js", ".json", ".yml"):
            continue
        # package-lock.json — згенерований npm'ом vendor-файл: e-mail'и
        # maintainer'ів залежностей — не наші секрети.
        if p.name == "package-lock.json":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        m = email.search(text)
        if m:
            # Xcode-метадані(asset catalogs) згадують імена файлів іконок
            # виду 'AppIcon-512@2x.png' — '@2x' це scale-суфікс Apple,
            # а не адреса.
            if m.group(0).endswith("@2x.png"):
                continue
            offenders.append((str(p), m.group(0)))
    assert offenders == [], offenders


# --- config via env with safe defaults -------------------------------------------

def test_config_only_via_env_with_safe_defaults():
    import tomllib
    from backend import db, serve
    # БД: env або дефолт поруч з проєктом; без хардкоду приватних шляхів
    assert db.DB_PATH.replace("\\", "/").endswith("subwatch/subwatch.db") or \
        db.DB_PATH.endswith("subwatch.db")
    assert serve.DEFAULT_HOST == "127.0.0.1"     # тільки локальний хост
    assert serve.DEFAULT_PORT == 8000
    # у pyproject немає жодних секретних полів
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    flat = str(cfg).lower()
    for word in ("token", "secret", "api_key", "password"):
        assert word not in flat


def test_gitignore_covers_env():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi
    lines = [l.strip().lstrip("/") for l in gi.splitlines() if l.strip()]
    assert ".env" in lines or ".env.*" in lines
    assert "*.db" in lines          # локальні дані не в репозиторії
    assert "__pycache__/" in lines


def test_readme_has_contributing_and_topics():
    uk = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    for text in (uk, en):
        assert "CONTRIBUTING.md" in text
        assert "SECURITY.md" in text
        assert "subscription-tracker" in text      # recommended topics
        assert "local-first" in text


def test_app_is_not_exposed_by_default():
    """Дефолт — 127.0.0.1, тож open-source користувач не відкриє сервер у LAN."""
    from backend import serve
    import os
    assert os.environ.get("SUBWATCH_HOST", serve.DEFAULT_HOST) == "127.0.0.1"
