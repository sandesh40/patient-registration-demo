from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_browser_config_exposes_only_public_values(database_url):
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        api_auth_token="private-api-token",
        vapi_webhook_secret="private-webhook-token",
        vapi_public_key="public-browser-key",
        vapi_assistant_id="demo-assistant",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/demo/config")
        assert response.json() == {
            "data": {
                "enabled": True,
                "public_key": "public-browser-key",
                "assistant_id": "demo-assistant",
            },
            "error": None,
        }
        assert response.headers["cache-control"] == "no-store"
        for route in ["/", "/assets/demo.js", "/assets/demo.css"]:
            result = client.get(route)
            assert result.status_code == 200
            assert "private-api-token" not in result.text
            assert "private-webhook-token" not in result.text
        assert client.get("/patients").status_code == 401


def test_browser_calling_disabled_without_public_key(database_url):
    settings = Settings(_env_file=None, app_env="test", database_url=database_url)
    with TestClient(create_app(settings)) as client:
        assert client.get("/demo/config").json()["data"]["enabled"] is False


def test_serverless_bundle_without_public_directory(database_url, monkeypatch, tmp_path):
    monkeypatch.setattr("app.main.PUBLIC_DIR", tmp_path / "cdn-only")
    settings = Settings(_env_file=None, app_env="test", database_url=database_url)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        homepage = client.get("/", follow_redirects=False)
        assert homepage.status_code == 307
        assert homepage.headers["location"] == "/index.html"
