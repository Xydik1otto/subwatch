# INSTALL.md: step-by-step install for non-programmers (Windows + Linux).
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


@pytest.fixture()
def install_md():
    return (ROOT / "INSTALL.md").read_text(encoding="utf-8")


def test_install_md_exists_and_covers_both_os(install_md):
    assert "## Windows 10/11" in install_md
    assert "## Linux" in install_md
    assert "## Оновлення" in install_md


def test_install_md_windows_autostart_via_startup_folder(install_md):
    assert "shell:startup" in install_md
    assert "start.bat" in install_md


def test_install_md_linux_systemd_user_unit(install_md):
    assert "systemd user unit" in install_md
    assert "~/.config/systemd/user/subwatch.service" in install_md
    assert "systemctl --user enable --now subwatch" in install_md


def test_install_md_has_no_local_filesystem_leaks(install_md):
    # жодних приватних шляхів (G:\, C:\Users\...) у публічній документації
    assert not re.search(r"[A-Z]:\\Users", install_md)
    assert "G:" not in install_md


def test_install_md_documents_env_config(install_md):
    for var in ("SUBWATCH_DB", "SUBWATCH_PORT", "SUBWATCH_HOST"):
        assert var in install_md


def test_quick_start_mentions_start_bat_and_serve(install_md):
    # start.bat uses python -m backend.serve (same entry point as console script)
    assert "python -m backend.serve" in install_md
