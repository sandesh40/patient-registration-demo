from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import build_engine
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def patient_data():
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": "04/15/1990",
        "sex": "Female",
        "phone_number": "2025550123",
        "address_line_1": "123 Example Street",
        "city": "Washington",
        "state": "DC",
        "zip_code": "20001",
    }


def migrate(database_url: str, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    get_settings.cache_clear()


@pytest.fixture
def database_url(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'patients.db'}"
    migrate(url, monkeypatch)
    yield url
    get_settings.cache_clear()


@pytest.fixture
def app(database_url):
    return create_app(
        Settings(_env_file=None, database_url=database_url, app_env="test", api_auth_token="")
    )


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def engine(database_url):
    result = build_engine(database_url)
    yield result
    result.dispose()
