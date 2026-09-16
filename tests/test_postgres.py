"""Optional integration check. TEST_POSTGRES_URL must name a disposable *_test DB."""

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.db import build_engine, utc_now
from app.main import create_app
from app.models import Patient
from app.schemas import PatientCreate


@pytest.mark.postgres
def test_postgres_migration_crud_persistence_and_constraints(monkeypatch, patient_data):
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to a disposable PostgreSQL database")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Refusing to migrate a database whose name does not end in _test")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    engine = build_engine(url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    try:
        command.check(config)
        settings = Settings(_env_file=None, app_env="test", database_url=url, api_auth_token="")
        with TestClient(create_app(settings)) as client:
            response = client.post("/patients", json=patient_data)
            assert response.status_code == 201, response.text
            patient = response.json()["data"]
            path = f"/patients/{patient['patient_id']}"
            assert client.get(path).json()["data"] == patient
            assert client.get("/patients", params={"last_name": "doe"}).json()["data"] == [patient]
            assert client.put(path, json={"last_name": "Davis"}).status_code == 200

        with TestClient(create_app(settings)) as restarted:
            assert restarted.get(path).json()["data"]["last_name"] == "Davis"
            assert restarted.delete(path).json()["data"]["deleted_at"] is not None
            assert restarted.get(path).status_code == 404

        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM patients WHERE deleted_at IS NOT NULL")
                )
                == 1
            )
            assert connection.scalar(
                text("SELECT relrowsecurity FROM pg_class WHERE oid = 'patients'::regclass")
            )

        for field, value in [
            ("first_name", "123"),
            ("last_name", "-''"),
            ("phone_number", "123"),
            ("zip_code", "123456789"),
            ("sex", "Unknown"),
            ("state", "ZZ"),
            ("date_of_birth", date.today() + timedelta(days=2)),
        ]:
            values = PatientCreate(**patient_data).model_dump()
            values.update(patient_id=uuid4(), created_at=utc_now(), updated_at=utc_now())
            values[field] = value
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(insert(Patient).values(**values))
    finally:
        command.downgrade(config, "base")
        engine.dispose()
        get_settings.cache_clear()
