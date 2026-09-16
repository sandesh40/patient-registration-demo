"""Exercise the configured database using fictional data and no paid voice calls.

Creates one synthetic patient and soft-deletes it after verification. Never truncates
tables or rolls back migrations. Requires development dependencies (TestClient).
"""

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Patient  # noqa: E402
from app.voice.models import VoiceSession  # noqa: E402


def main():
    settings = Settings()
    logging.getLogger().setLevel(logging.WARNING)
    run_id = f"smoke-{uuid4()}"
    headers = {"Authorization": f"Bearer {settings.api_auth_token.get_secret_value()}"}
    voice_headers = {"Authorization": f"Bearer {settings.vapi_webhook_secret.get_secret_value()}"}
    patient = json.loads(Path("examples/patient.json").read_text())
    patient.update(first_name="Demo", last_name="Assessment", phone_number="2025550199")

    def tool(client, name, arguments, call_id=run_id, tool_id=None):
        response = client.post(
            "/vapi/webhook",
            headers=voice_headers,
            json={
                "message": {
                    "type": "tool-calls",
                    "call": {"id": call_id, "assistantId": settings.vapi_assistant_id},
                    "toolCallList": [
                        {
                            "id": tool_id or str(uuid4()),
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            },
        )
        assert response.status_code == 200, "Webhook request failed"
        return json.loads(response.json()["results"][0]["result"])

    patient_id = None
    try:
        app = create_app(settings)
        with TestClient(app) as client:
            assert client.get("/ready").status_code == 200
            invalid = tool(client, "validate_fields", {"fields": {"date_of_birth": "02/30/2000"}})
            assert invalid["error"]["code"] == "validation_error"
            prepared = tool(client, "prepare_registration", {"patient": patient})
            assert prepared["ok"]
            with Session(app.state.engine) as session:
                assert session.get(VoiceSession, run_id).patient_id is None
            confirmation = {"confirmation_token": prepared["confirmation_token"], "confirmed": True}
            # Two simultaneous deliveries must commit one patient and the same receipt.
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        tool,
                        client,
                        "confirm_registration",
                        confirmation,
                        tool_id="concurrent-confirm",
                    )
                    for _ in range(2)
                ]
                results = [future.result() for future in futures]
            assert all(result["ok"] for result in results)
            patient_id = results[0]["patient"]["patient_id"]
            assert results[0] == results[1]
            print("PASS: invalid-field response, preparation, concurrent confirmation/retry")

        # A new application and database engine must recover saved data and receipts.
        app = create_app(settings)
        with TestClient(app) as client:
            response = client.get(f"/patients/{patient_id}", headers=headers)
            assert response.status_code == 200
            replay = tool(
                client, "confirm_registration", confirmation, tool_id="concurrent-confirm"
            )
            assert replay == results[0]
            update_call = run_id + "-update"
            matches = tool(
                client,
                "lookup_patient",
                {
                    "phone_number": patient["phone_number"],
                    "date_of_birth": patient["date_of_birth"],
                },
                call_id=update_call,
            )
            assert any(p["patient_id"] == patient_id for p in matches["matches"])
            updated = tool(
                client,
                "prepare_registration",
                {"patient_id": patient_id, "patient": {"address_line_2": "Suite 2"}},
                call_id=update_call,
            )
            assert updated["ok"]
            saved = tool(
                client,
                "confirm_registration",
                {"confirmation_token": updated["confirmation_token"], "confirmed": True},
                call_id=update_call,
            )
            assert saved["patient"]["patient_id"] == patient_id
            assert saved["patient"]["address_line_2"] == "Suite 2"
            assert saved["patient"]["email"] == patient["email"]
            ended = client.post(
                "/vapi/webhook",
                headers=voice_headers,
                json={
                    "message": {
                        "type": "end-of-call-report",
                        "call": {"id": update_call},
                        "endedReason": "assistant-ended-call",
                        "artifact": {"transcript": "Synthetic smoke test; no audio call."},
                    }
                },
            )
            assert ended.status_code == 200
            with Session(app.state.engine) as session:
                voice = session.get(VoiceSession, update_call)
                assert voice.patient_id == UUID(patient_id) and voice.transcript
            print("PASS: application restart, returning-patient update, linked transcript")
    finally:
        # Recover a committed ID even if the concurrent response assertions failed.
        app = create_app(settings)
        with TestClient(app) as client:
            with Session(app.state.engine) as session:
                voice = session.get(VoiceSession, run_id)
                patient_id = patient_id or (
                    str(voice.patient_id) if voice and voice.patient_id else None
                )
            if patient_id:
                response = client.delete(f"/patients/{patient_id}", headers=headers)
                assert response.status_code == 200, "Synthetic patient cleanup failed"
                assert client.get(f"/patients/{patient_id}", headers=headers).status_code == 404
                with Session(app.state.engine) as session:
                    retained = session.scalar(
                        select(Patient).where(Patient.patient_id == UUID(patient_id))
                    )
                    assert retained.deleted_at is not None
                print("PASS: synthetic patient soft-deleted and retained in database")
    print("Voice/database smoke test passed. No Vapi call was placed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            f"Smoke test failed ({type(exc).__name__}); connection details omitted.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
