import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_authentication_for_all_patient_endpoints(database_url, patient_data):
    token = "test-token-" + "a" * 32
    settings = Settings(
        _env_file=None, app_env="test", database_url=database_url, api_auth_token=token
    )
    with TestClient(create_app(settings)) as client:
        for method, path, kwargs in [
            ("GET", "/patients", {}),
            ("POST", "/patients", {"json": patient_data}),
            ("GET", "/patients/00000000-0000-0000-0000-000000000000", {}),
            ("PUT", "/patients/00000000-0000-0000-0000-000000000000", {"json": {"city": "Boston"}}),
            ("DELETE", "/patients/00000000-0000-0000-0000-000000000000", {}),
        ]:
            response = client.request(method, path, **kwargs)
            assert response.status_code == 401
            assert response.json()["data"] is None
            assert response.headers["www-authenticate"] == "Bearer"
        assert (
            client.get("/patients", headers={"Authorization": "Bearer incorrect"}).status_code
            == 401
        )
        assert (
            client.get("/patients", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        )
        assert client.get("/health").status_code == 200


def test_production_requires_token_and_persistent_database():
    with pytest.raises(ValidationError, match="API_AUTH_TOKEN"):
        Settings(_env_file=None, app_env="production", api_auth_token="")
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(
            _env_file=None, app_env="production", api_auth_token="a" * 32, database_url="sqlite://"
        )


def test_settings_hide_secrets():
    settings = Settings(
        _env_file=None, database_url="postgresql://secret", api_auth_token="private-token"
    )
    assert "postgresql://secret" not in repr(settings)
    assert "private-token" not in repr(settings)
