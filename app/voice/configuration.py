"""Reviewable Vapi configuration; no account keys are embedded in the prompt or tools."""

from pathlib import Path

from app.schemas import PatientCreate

FUNCTIONS = {
    "validate_fields": (
        "Validate new or corrected demographics. Re-prompt only invalid fields. "
        "Invalidates old confirmation."
    ),
    "lookup_patient": (
        "Find fictional patients matching phone AND date of birth; "
        "ask permission before updating a match."
    ),
    "prepare_registration": (
        "Validate a new patient or changes to a looked-up patient, then return ALL details "
        "for readback. Does not save a patient."
    ),
    "confirm_registration": (
        "Save the latest prepared snapshot ONLY after a separate caller turn explicitly "
        "confirms the full readback. Never call together with prepare."
    ),
    "start_over": (
        "Discard the unconfirmed draft and patient selection when the caller asks to "
        "start over. Does not delete saved patients."
    ),
}


def patient_properties() -> dict:
    schema = PatientCreate.model_json_schema()
    properties = schema["properties"]
    # Inline this small enum for provider portability (avoid Pydantic-local $defs).
    properties["sex"] = {"type": "string", "enum": ["Male", "Female", "Other", "Decline to Answer"]}
    return properties


def tool_definitions(server: dict | None = None) -> list[dict]:
    properties = patient_properties()
    partial_patient = {"type": "object", "properties": properties, "additionalProperties": False}
    schemas = {
        "validate_fields": {
            "type": "object",
            "properties": {"fields": partial_patient},
            "required": ["fields"],
        },
        "lookup_patient": {
            "type": "object",
            "properties": {
                "phone_number": {"type": "string"},
                "date_of_birth": properties["date_of_birth"],
            },
            "required": ["phone_number", "date_of_birth"],
        },
        "prepare_registration": {
            "type": "object",
            "properties": {
                "patient": partial_patient,
                "patient_id": {
                    "type": "string",
                    "description": "Only for an update: patient_id returned by lookup_patient.",
                },
            },
            "required": ["patient"],
        },
        "confirm_registration": {
            "type": "object",
            "properties": {
                "confirmation_token": {
                    "type": "string",
                    "description": "Exact token from the latest successful prepare_registration.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "True only after explicit confirmation of the full readback.",
                },
            },
            "required": ["confirmation_token", "confirmed"],
        },
        "start_over": {"type": "object", "properties": {}, "required": []},
    }
    tools = []
    for name, description in FUNCTIONS.items():
        schemas[name]["additionalProperties"] = False
        tool = {
            "type": "function",
            "async": False,
            "function": {"name": name, "description": description, "parameters": schemas[name]},
        }
        if name in {"lookup_patient", "prepare_registration", "confirm_registration"}:
            tool["messages"] = [
                {"type": "request-start", "content": "One moment while I check that."}
            ]
        if server:
            tool["server"] = server
        tools.append(tool)
    tools.append({"type": "endCall"})
    return tools


def assistant_configuration(
    *,
    api_base_url: str | None = None,
    credential_id: str | None = None,
    model: str = "gemini-2.5-flash",
) -> dict:
    server = None
    if api_base_url:
        if not api_base_url.startswith("https://") or not credential_id:
            raise ValueError(
                "Live configuration requires an HTTPS API URL and a Vapi server credential ID"
            )
        server = {
            "url": api_base_url.rstrip("/") + "/vapi/webhook",
            "credentialId": credential_id,
            "timeoutSeconds": 20,
        }
    config = {
        "name": "Patient Registration Demo",
        "firstMessage": (
            "Hello! I'm Alex, your registration assistant. This is a demo, so please use "
            "fictional information. What are your first and last names?"
        ),
        "model": {
            "provider": "google",
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": Path(__file__).with_name("prompt.md").read_text()}
            ],
            "tools": tool_definitions(server),
        },
        "voice": {"provider": "deepgram", "voiceId": "asteria"},
        "transcriber": {"provider": "deepgram", "model": "nova-3", "language": "en"},
        "maxDurationSeconds": 600,
        "silenceTimeoutSeconds": 30,
        "backgroundSound": "off",
        "serverMessages": ["tool-calls", "status-update", "end-of-call-report"],
        "artifactPlan": {"recordingEnabled": False},
        "endCallMessage": "Thank you. Goodbye!",
    }
    if server:
        config["server"] = server
    return config
