import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Patient
from app.voice.configuration import assistant_configuration
from app.voice.models import ToolReceipt, VoiceSession

SECRET = "voice-test-secret-not-a-real-credential"


@pytest.fixture
def voice_client(database_url):
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        api_auth_token="",
        vapi_webhook_secret=SECRET,
        vapi_assistant_id="test-assistant",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def send_tool(client, name, arguments, *, call_id="call-1", tool_id=None):
    tool_id = tool_id or str(uuid4())
    response = client.post(
        "/vapi/webhook",
        headers={"Authorization": f"Bearer {SECRET}"},
        json={
            "message": {
                "type": "tool-calls",
                "call": {"id": call_id, "assistantId": "test-assistant"},
                "toolCallList": [
                    {
                        "id": tool_id,
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ],
            }
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["toolCallId"] == tool_id
    return json.loads(result["result"])


def prepare(client, patient_data, **kwargs):
    result = send_tool(client, "prepare_registration", {"patient": patient_data}, **kwargs)
    assert result["ok"], result
    return result["confirmation_token"]


def confirm(client, token, **kwargs):
    return send_tool(
        client, "confirm_registration", {"confirmation_token": token, "confirmed": True}, **kwargs
    )


def count_patients(engine):
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(Patient))


def test_prepare_readback_then_confirm(voice_client, engine, patient_data, caplog):
    patient_data.update(
        email="jane@example.com", insurance_provider="Example", insurance_member_id="A123"
    )
    result = send_tool(voice_client, "prepare_registration", {"patient": patient_data})
    assert result["ok"]
    assert result["status"] == "awaiting_confirmation"
    assert count_patients(engine) == 0
    for value in result["patient"].values():
        if value is not None:
            assert str(value) in result["readback"]
    with caplog.at_level("INFO", logger="app.voice.service"):
        saved = confirm(voice_client, result["confirmation_token"])
    assert saved["status"] == "saved"
    assert count_patients(engine) == 1
    assert "voice_registration_confirmed" in caplog.text
    assert "jane@example.com" in caplog.text
    assert result["confirmation_token"] not in caplog.text
    assert SECRET not in caplog.text


def test_confirm_requires_preparation_and_is_scoped_to_call(voice_client, engine, patient_data):
    assert not confirm(voice_client, str(uuid4()))["ok"]
    token = prepare(voice_client, patient_data)
    assert not confirm(voice_client, token, call_id="another-call")["ok"]
    assert count_patients(engine) == 0
    assert confirm(voice_client, token)["ok"]


@pytest.mark.parametrize("value", ["true", 1, None])
def test_confirmation_must_be_boolean(voice_client, engine, patient_data, value):
    token = prepare(voice_client, patient_data)
    result = send_tool(
        voice_client, "confirm_registration", {"confirmation_token": token, "confirmed": value}
    )
    assert result["error"]["code"] == "validation_error"
    assert count_patients(engine) == 0


def test_declined_confirmation_and_start_over(voice_client, engine, patient_data):
    token = prepare(voice_client, patient_data)
    result = send_tool(
        voice_client, "confirm_registration", {"confirmation_token": token, "confirmed": False}
    )
    assert result["status"] == "not_saved"
    assert not confirm(voice_client, token)["ok"]
    token = prepare(voice_client, patient_data)
    assert send_tool(voice_client, "start_over", {})["status"] == "started_over"
    assert not confirm(voice_client, token)["ok"]
    assert count_patients(engine) == 0


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("validate_fields", {"fields": {"last_name": "Davis"}}),
        ("validate_fields", {"fields": {"phone_number": "123"}}),
        ("prepare_registration", {"patient": {"phone_number": "123"}}),
        ("prepare_registration", "{broken"),
        ("validate_fields", []),
    ],
)
def test_corrections_even_invalid_ones_invalidate_old_confirmation(
    voice_client, engine, patient_data, name, arguments
):
    old = prepare(voice_client, patient_data)
    send_tool(voice_client, name, arguments)
    assert confirm(voice_client, old)["error"]["code"] == "stale_confirmation"
    assert count_patients(engine) == 0
    updated = prepare(voice_client, {**patient_data, "last_name": "Davis"})
    assert confirm(voice_client, updated)["patient"]["last_name"] == "Davis"


def test_retries_are_idempotent_and_ids_cannot_be_reused_for_other_data(
    voice_client, engine, patient_data
):
    first = send_tool(
        voice_client, "prepare_registration", {"patient": patient_data}, tool_id="prepare-1"
    )
    second = send_tool(
        voice_client, "prepare_registration", {"patient": patient_data}, tool_id="prepare-1"
    )
    assert second == first
    conflict = send_tool(
        voice_client,
        "prepare_registration",
        {"patient": {**patient_data, "city": "Boston"}},
        tool_id="prepare-1",
    )
    assert conflict["error"]["code"] == "tool_id_conflict"
    saved = confirm(voice_client, first["confirmation_token"], tool_id="confirm-1")
    assert confirm(voice_client, first["confirmation_token"], tool_id="confirm-1") == saved
    assert confirm(voice_client, first["confirmation_token"])["already_saved"]
    assert count_patients(engine) == 1
    assert not send_tool(voice_client, "start_over", {})["ok"]
    assert not send_tool(
        voice_client,
        "confirm_registration",
        {"confirmation_token": first["confirmation_token"], "confirmed": False},
    )["ok"]
    with Session(engine) as session:
        assert session.get(VoiceSession, "call-1").status == "saved"


def test_confirmation_cannot_mutate_the_prepared_payload(voice_client, engine, patient_data):
    token = prepare(voice_client, patient_data)
    result = send_tool(
        voice_client,
        "confirm_registration",
        {"confirmation_token": token, "confirmed": True, "patient": {"last_name": "Forged"}},
    )
    assert result["error"]["code"] == "validation_error"
    assert count_patients(engine) == 0


def test_phone_normalization_and_targeted_errors(voice_client):
    result = send_tool(
        voice_client,
        "validate_fields",
        {"fields": {"phone_number": "+1 (202) 555-0123", "state": "ca"}},
    )
    assert result == {"ok": True, "fields": {"phone_number": "2025550123", "state": "CA"}}
    bad = send_tool(
        voice_client, "validate_fields", {"fields": {"phone_number": "123", "city": "Boston"}}
    )
    assert bad["error"]["details"][0]["field"] == "phone_number"
    assert len(bad["error"]["details"]) == 1
    assert not send_tool(
        voice_client, "validate_fields", {"fields": {"phone_number": "abc2025550123"}}
    )["ok"]


def test_returning_patient_update_preserves_omitted_fields(voice_client, engine, patient_data):
    original = voice_client.post(
        "/patients", json={**patient_data, "email": "jane@example.com"}
    ).json()["data"]
    lookup = send_tool(
        voice_client,
        "lookup_patient",
        {"phone_number": "+12025550123", "date_of_birth": patient_data["date_of_birth"]},
    )
    assert lookup["matches"] == [original]
    result = send_tool(
        voice_client,
        "prepare_registration",
        {"patient_id": original["patient_id"], "patient": {"last_name": "Davis"}},
    )
    assert result["patient"]["email"] == "jane@example.com"
    assert (
        voice_client.get(f"/patients/{original['patient_id']}").json()["data"]["last_name"] == "Doe"
    )
    updated = confirm(voice_client, result["confirmation_token"])
    assert updated["patient"]["last_name"] == "Davis"
    assert updated["patient"]["patient_id"] == original["patient_id"]
    assert updated["patient"]["email"] == "jane@example.com"
    assert count_patients(engine) == 1


def test_update_requires_lookup_and_detects_concurrent_changes(voice_client, patient_data):
    original = voice_client.post("/patients", json=patient_data).json()["data"]
    arguments = {"patient_id": original["patient_id"], "patient": {"last_name": "Davis"}}
    assert (
        send_tool(voice_client, "prepare_registration", arguments)["error"]["code"]
        == "lookup_required"
    )
    wrong_dob = send_tool(
        voice_client,
        "lookup_patient",
        {"phone_number": patient_data["phone_number"], "date_of_birth": "01/01/2000"},
    )
    assert wrong_dob["matches"] == []
    send_tool(
        voice_client,
        "lookup_patient",
        {
            "phone_number": patient_data["phone_number"],
            "date_of_birth": patient_data["date_of_birth"],
        },
    )
    token = send_tool(voice_client, "prepare_registration", arguments)["confirmation_token"]
    path = f"/patients/{original['patient_id']}"
    assert voice_client.put(path, json={"city": "Boston"}).status_code == 200
    assert confirm(voice_client, token)["error"]["code"] == "record_changed"
    assert voice_client.get(path).json()["data"]["last_name"] == "Doe"


def end_event(
    client, call_id="call-1", transcript="Demo transcript", event_type="end-of-call-report"
):
    return client.post(
        "/vapi/webhook",
        headers={"Authorization": f"Bearer {SECRET}"},
        json={
            "message": {
                "type": event_type,
                "status": "ended",
                "call": {"id": call_id},
                "endedReason": "customer-ended-call",
                "artifact": {"transcript": transcript},
            }
        },
    )


def test_disconnect_discards_unconfirmed_draft_and_never_saves_from_transcript(
    voice_client, engine, patient_data
):
    token = prepare(voice_client, patient_data)
    assert end_event(voice_client).status_code == 200
    assert end_event(voice_client).status_code == 200
    assert confirm(voice_client, token)["error"]["code"] == "call_ended"
    assert count_patients(engine) == 0
    with Session(engine) as session:
        voice = session.get(VoiceSession, "call-1")
        assert voice.status == "cancelled"
        assert voice.draft is None
        assert voice.confirmation_token is None


def test_transcript_is_linked_to_confirmed_patient(voice_client, engine, patient_data):
    saved = confirm(voice_client, prepare(voice_client, patient_data))
    assert end_event(voice_client, event_type="status-update", transcript=None).status_code == 200
    assert end_event(voice_client).status_code == 200
    with Session(engine) as session:
        voice = session.get(VoiceSession, "call-1")
        assert voice.status == "saved"
        assert str(voice.patient_id) == saved["patient"]["patient_id"]
        assert voice.transcript == "Demo transcript"


def test_failure_rolls_back_patient_and_receipt_then_same_retry_succeeds(
    voice_client, engine, patient_data, monkeypatch
):
    token = prepare(voice_client, patient_data)

    def fail_commit(self):
        self.flush()
        raise OperationalError("secret", {}, Exception("unavailable"))

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        result = confirm(voice_client, token, tool_id="retry-me")
    assert result["error"]["code"] == "database_error"
    assert count_patients(engine) == 0
    with Session(engine) as session:
        assert session.get(ToolReceipt, ("call-1", "retry-me")) is None
        assert session.get(VoiceSession, "call-1").status == "prepared"
    assert confirm(voice_client, token, tool_id="retry-me")["ok"]
    assert count_patients(engine) == 1


def test_draft_and_confirmation_survive_application_restart(
    voice_client, database_url, patient_data
):
    token = prepare(voice_client, patient_data)
    new_settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        api_auth_token="",
        vapi_webhook_secret=SECRET,
    )
    with TestClient(create_app(new_settings)) as restarted:
        assert confirm(restarted, token)["ok"]


@pytest.mark.parametrize("shape", ["flat", "parameters", "wrapped"])
def test_supported_vapi_protocol_shapes(voice_client, shape):
    function = {
        "id": "shape-test",
        "name": "validate_fields",
        "arguments": {"fields": {"city": "Boston"}},
    }
    message = {"type": "tool-calls", "call": {"id": "call-shape"}}
    if shape == "parameters":
        function["parameters"] = function.pop("arguments")
    if shape == "wrapped":
        message["toolWithToolCallList"] = [{"name": function["name"], "toolCall": function}]
    else:
        message["toolCallList"] = [function]
    response = voice_client.post(
        "/vapi/webhook", headers={"Authorization": f"Bearer {SECRET}"}, json={"message": message}
    )
    assert response.status_code == 200
    assert json.loads(response.json()["results"][0]["result"])["ok"]


def test_json_string_arguments_and_unknown_tool(voice_client):
    assert send_tool(voice_client, "validate_fields", json.dumps({"fields": {"city": "Boston"}}))[
        "ok"
    ]
    assert send_tool(voice_client, "delete_all_patients", {})["error"]["code"] == "unknown_tool"


def test_authentication_and_malformed_protocol(voice_client):
    payload = {"message": {"type": "tool-calls", "call": {"id": "call-1"}, "toolCallList": []}}
    assert voice_client.post("/vapi/webhook", json=payload).status_code == 401
    assert (
        voice_client.post(
            "/vapi/webhook", json=payload, headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    headers = {"Authorization": f"Bearer {SECRET}"}
    assert voice_client.post("/vapi/webhook", json=payload, headers=headers).status_code == 400
    payload["message"]["call"]["assistantId"] = "wrong-assistant"
    assert voice_client.post("/vapi/webhook", json=payload, headers=headers).status_code == 403


def test_confirmation_in_batch_is_rejected(voice_client, engine, patient_data):
    token = prepare(voice_client, patient_data)
    tools = [
        {"id": "batch1", "name": "validate_fields", "arguments": {"fields": {"city": "Boston"}}},
        {
            "id": "batch2",
            "name": "confirm_registration",
            "arguments": {"confirmation_token": token, "confirmed": True},
        },
    ]
    response = voice_client.post(
        "/vapi/webhook",
        headers={"Authorization": f"Bearer {SECRET}"},
        json={"message": {"type": "tool-calls", "call": {"id": "call-1"}, "toolCallList": tools}},
    )
    assert (
        json.loads(response.json()["results"][1]["result"])["error"]["code"]
        == "separate_confirmation_required"
    )
    assert count_patients(engine) == 0


def test_configuration_includes_prompt_tools_and_bounded_calls():
    config = assistant_configuration(
        api_base_url="https://demo.example", credential_id="credential-id"
    )
    assert config["server"]["credentialId"] == "credential-id"
    assert config["maxDurationSeconds"] == 600
    assert config["model"]["provider"] == "google"
    assert "WAIT for the caller" in config["model"]["messages"][0]["content"]
    names = [
        tool["function"]["name"] for tool in config["model"]["tools"] if tool["type"] == "function"
    ]
    assert set(names) == {
        "validate_fields",
        "lookup_patient",
        "prepare_registration",
        "confirm_registration",
        "start_over",
    }
    assert config["model"]["tools"][-1]["type"] == "endCall"
    assert "$ref" not in json.dumps(config)
    with pytest.raises(ValueError):
        assistant_configuration(api_base_url="http://example.com", credential_id="id")
