from datetime import date, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import insert, inspect
from sqlalchemy.exc import IntegrityError

from app.db import utc_now
from app.models import Patient
from app.schemas import PatientCreate


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_name", "123"),
        ("last_name", "-''"),
        ("city", ""),
        ("city", " " * 10),
        ("city", "A" * 101),
        ("city", " " * 101 + "Boston"),
        ("state", "ZZ"),
        ("phone_number", "123"),
        ("phone_number", "abcdefghij"),
        ("zip_code", "123456789"),
        ("sex", "Unknown"),
        ("date_of_birth", date.today() + timedelta(days=2)),
        ("insurance_member_id", "ID-123"),
        ("emergency_contact_phone", "bad"),
        ("preferred_language", ""),
        ("address_line_1", None),
    ],
)
def test_database_constraints_reject_invalid_writes_without_pydantic(
    engine, patient_data, field, value
):
    values = PatientCreate(**patient_data).model_dump()
    values.update(patient_id=uuid4(), created_at=utc_now(), updated_at=utc_now())
    values[field] = value
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(insert(Patient).values(**values))


def test_migrations_match_models_and_can_be_reapplied(database_url, engine):
    config = Config("alembic.ini")
    command.check(config)
    command.upgrade(config, "head")
    assert "patients" in inspect(engine).get_table_names()
    command.downgrade(config, "base")
    assert "patients" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert "patients" in inspect(engine).get_table_names()
