from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Patient
from app.schemas import REQUIRED_FIELDS


def assert_error(response, status, field=None):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["data"] is None
    assert body["error"]["code"]
    if field:
        assert any(item["field"] == field for item in body["error"]["details"])
    return body


def test_create_and_get_all_fields(client, patient_data):
    patient_data.update(
        {
            "first_name": "Anne-Marie",
            "last_name": "O'Neill",
            "email": "jane@example.com",
            "address_line_2": "Apt 4",
            "insurance_provider": "Example Insurance",
            "insurance_member_id": "ABC123",
            "preferred_language": "Spanish",
            "emergency_contact_name": "John Doe",
            "emergency_contact_phone": "4155550123",
            "zip_code": "20001-1234",
        }
    )
    response = client.post("/patients", json=patient_data)
    assert response.status_code == 201, response.text
    patient = response.json()["data"]
    assert response.json()["error"] is None
    assert UUID(patient["patient_id"]).version == 4
    assert response.headers["Location"] == f"/patients/{patient['patient_id']}"
    for name, value in patient_data.items():
        assert patient[name] == value
    assert patient["deleted_at"] is None
    created = datetime.fromisoformat(patient["created_at"])
    assert created.utcoffset() == timedelta(0)
    assert patient["created_at"] == patient["updated_at"]
    assert client.get(response.headers["Location"]).json()["data"] == patient


def test_defaults_trimming_and_state_normalization(client, patient_data):
    patient_data.update(first_name=" Jane ", state="dc")
    response = client.post("/patients", json=patient_data)
    assert response.status_code == 201
    patient = response.json()["data"]
    assert patient["first_name"] == "Jane"
    assert patient["state"] == "DC"
    assert patient["preferred_language"] == "English"
    assert patient["email"] is None


@pytest.mark.parametrize("field", sorted(REQUIRED_FIELDS - {"preferred_language"}))
def test_missing_required_fields(client, patient_data, field):
    del patient_data[field]
    assert_error(client.post("/patients", json=patient_data), 422, field)
    assert client.get("/patients").json()["data"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_name", "Jane1"),
        ("first_name", "-''"),
        ("first_name", "A" * 51),
        ("last_name", ""),
        ("last_name", "Doe<script>"),
        ("last_name", "A" * 51),
        ("date_of_birth", "02/30/1990"),
        ("date_of_birth", "02/29/2023"),
        ("date_of_birth", "1990-04-15"),
        ("date_of_birth", "4/15/1990"),
        ("date_of_birth", "01/01/0000"),
        ("date_of_birth", 1234567890),
        ("date_of_birth", (datetime.now(UTC) + timedelta(days=1)).strftime("%m/%d/%Y")),
        ("sex", "Unknown"),
        ("sex", "female"),
        ("phone_number", "123"),
        ("phone_number", "0125550123"),
        ("phone_number", "2021550123"),
        ("phone_number", "+12025550123"),
        ("phone_number", "202-555-0123"),
        ("phone_number", 2025550123),
        ("email", "not-an-email"),
        ("email", ""),
        ("address_line_1", "  "),
        ("address_line_1", "123\x00Street"),
        ("city", "A" * 101),
        ("city", ""),
        ("state", "ZZ"),
        ("state", "California"),
        ("zip_code", "1234"),
        ("zip_code", "123456789"),
        ("zip_code", "12345-123"),
        ("insurance_member_id", "ABC-123"),
        ("insurance_member_id", ""),
        ("emergency_contact_phone", "123"),
        ("preferred_language", None),
        ("preferred_language", ""),
        ("unknown_field", "unexpected"),
        ("patient_id", str(uuid4())),
        ("deleted_at", "2026-01-01T00:00:00Z"),
    ],
)
def test_invalid_fields_are_rejected(client, patient_data, field, value):
    patient_data[field] = value
    assert_error(client.post("/patients", json=patient_data), 422, field)
    assert client.get("/patients").json()["data"] == []


@pytest.mark.parametrize("sex", ["Male", "Female", "Other", "Decline to Answer"])
def test_all_sex_values_and_valid_leap_day(client, patient_data, sex):
    patient_data.update(sex=sex, date_of_birth="02/29/2000")
    assert client.post("/patients", json=patient_data).status_code == 201


def test_filters_combine_and_treat_values_as_data(client, patient_data):
    first = client.post("/patients", json=patient_data).json()["data"]
    client.post(
        "/patients", json={**patient_data, "last_name": "Smith", "phone_number": "4155550123"}
    )
    assert len(client.get("/patients").json()["data"]) == 2
    for filters in [
        {"last_name": "doe"},
        {"phone_number": "2025550123"},
        {"last_name": "Doe", "date_of_birth": "04/15/1990", "phone_number": "2025550123"},
    ]:
        assert client.get("/patients", params=filters).json()["data"] == [first]
    assert len(client.get("/patients", params={"date_of_birth": "04/15/1990"}).json()["data"]) == 2
    assert (
        client.get("/patients", params={"last_name": "Doe", "phone_number": "4155550123"}).json()[
            "data"
        ]
        == []
    )
    assert_error(client.get("/patients", params={"last_name": "' OR 1=1 --"}), 422)
    assert_error(client.get("/patients", params={"date_of_birth": "bad-date"}), 422)
    assert_error(client.get("/patients", params={"phone_number": "123"}), 422)


def test_partial_update_preserves_omitted_fields_and_clears_optional_fields(client, patient_data):
    original = client.post("/patients", json={**patient_data, "email": "jane@example.com"}).json()[
        "data"
    ]
    response = client.put(
        f"/patients/{original['patient_id']}", json={"last_name": "Davis", "email": None}
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["last_name"] == "Davis"
    assert updated["email"] is None
    assert updated["updated_at"] > original["updated_at"]
    for field in original.keys() - {"last_name", "email", "updated_at"}:
        assert updated[field] == original[field]


@pytest.mark.parametrize("field", sorted(REQUIRED_FIELDS))
def test_partial_update_rejects_null_required_fields(client, patient_data, field):
    original = client.post("/patients", json=patient_data).json()["data"]
    path = f"/patients/{original['patient_id']}"
    assert_error(client.put(path, json={field: None}), 422, field)
    assert client.get(path).json()["data"] == original


def test_bad_updates_are_atomic(client, patient_data):
    original = client.post("/patients", json=patient_data).json()["data"]
    path = f"/patients/{original['patient_id']}"
    assert_error(client.put(path, json={}), 400)
    assert_error(client.put(path, json={"last_name": "Davis", "date_of_birth": "02/30/2020"}), 422)
    assert_error(client.put(path, json={"created_at": "2020-01-01T00:00:00Z"}), 422)
    assert client.get(path).json()["data"] == original


def test_soft_delete_hides_record_without_removing_it(client, engine, patient_data):
    original = client.post("/patients", json=patient_data).json()["data"]
    path = f"/patients/{original['patient_id']}"
    response = client.delete(path)
    assert response.status_code == 200
    assert response.json()["data"]["deleted_at"] is not None
    assert_error(client.get(path), 404)
    assert_error(client.put(path, json={"last_name": "Davis"}), 404)
    assert_error(client.delete(path), 404)
    assert client.get("/patients").json()["data"] == []
    assert (
        client.get("/patients", params={"phone_number": patient_data["phone_number"]}).json()[
            "data"
        ]
        == []
    )
    with Session(engine) as session:
        stored = session.scalar(select(Patient))
        assert stored is not None
        assert stored.deleted_at is not None
        assert stored.deleted_at.utcoffset() == timedelta(0)


def test_missing_patient_and_bad_uuid(client):
    path = f"/patients/{uuid4()}"
    assert_error(client.get(path), 404)
    assert_error(client.put(path, json={"last_name": "Davis"}), 404)
    assert_error(client.delete(path), 404)
    assert_error(client.get("/patients/not-a-uuid"), 422)


def test_malformed_json_and_framework_errors_use_envelope(client):
    assert_error(
        client.post("/patients", content="{broken", headers={"Content-Type": "application/json"}),
        400,
    )
    assert_error(client.get("/does-not-exist"), 404)
    assert_error(client.patch("/patients"), 405)


def test_records_survive_application_restart(database_url, patient_data):
    settings = Settings(
        _env_file=None, app_env="test", database_url=database_url, api_auth_token=""
    )
    with TestClient(create_app(settings)) as first_app:
        patient = first_app.post("/patients", json=patient_data).json()["data"]
    # New app, engine, and session, sharing only the migrated database file.
    with TestClient(create_app(settings)) as second_app:
        assert second_app.get(f"/patients/{patient['patient_id']}").json()["data"] == patient


def test_database_write_failure_rolls_back_and_does_not_leak_secrets(
    client, patient_data, monkeypatch, caplog
):
    def fail_commit(self):
        self.flush()
        raise OperationalError(
            "secret-database-url", {"secret": "private-value"}, Exception("secret")
        )

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        response = client.post("/patients", json=patient_data)
    body = assert_error(response, 500)
    assert body["error"]["code"] == "database_error"
    assert "secret-database-url" not in response.text + caplog.text
    assert "private-value" not in response.text + caplog.text
    assert client.get("/patients").json()["data"] == []
    assert client.post("/patients", json=patient_data).status_code == 201


def test_health_and_readiness(client):
    assert client.get("/health").json() == {"data": {"status": "ok"}, "error": None}
    assert client.get("/ready").json() == {"data": {"status": "ready"}, "error": None}


def test_openapi_documents_endpoints_envelopes_and_date_format(client):
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]["/patients"]) == {"get", "post"}
    assert set(schema["paths"]["/patients/{patient_id}"]) == {"get", "put", "delete"}
    model = schema["components"]["schemas"]["PatientCreate"]
    assert "pattern" in model["properties"]["date_of_birth"]
    assert "date_of_birth" in model["required"]
    assert "422" in schema["paths"]["/patients"]["post"]["responses"]
