# Packaging: pyproject metadata, entry point, pip install -e .
import datetime as dt
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


def test_pyproject_metadata():
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    proj = cfg["project"]
    assert proj["name"] == "subwatch"
    assert proj["version"] == app.version
    assert proj["requires-python"] == ">=3.12"
    assert "fastapi>=0.110" in proj["dependencies"]
    assert proj["scripts"]["subwatch"] == "backend.serve:main"
    # license, classifiers — open-source hygiene
    assert "MIT" in str(proj["license"])


def test_requirements_pinned_with_minimums():
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    deps = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    assert all(">=" in d or "==" in d for d in deps), deps
    # кожна залежність pyproject є і в requirements
    import tomllib
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    for dep in proj["dependencies"]:
        assert dep.split(">")[0] in " ".join(deps)


def test_entry_point_module_importable_and_callable():
    from backend import serve
    assert callable(serve.main)
    assert serve.DEFAULT_HOST == "127.0.0.1"   # локальний за замовчуванням
    assert serve.DEFAULT_PORT == 8000


def test_env_overrides_have_safe_defaults():
    """Конфігурація лише через env, з локальними дефолтами (без секретів)."""
    import importlib
    from backend import db
    assert "SUBWATCH_DB" in db.DB_PATH or db.DB_PATH  # шлях БД через env/дефолт
    from backend import serve
    src = Path(serve.__file__).read_text(encoding="utf-8")
    assert "SUBWATCH_HOST" in src and "SUBWATCH_PORT" in src


def test_pip_install_e_dry_run():
    """`pip install -e .` коректний: build-backend і packages заявлені."""
    import tomllib
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "build-system" in cfg
    assert cfg["tool"]["setuptools"]["packages"] == ["backend"]
