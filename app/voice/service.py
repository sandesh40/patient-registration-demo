import hashlib
import json
import logging
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db import utc_now
from app.errors import ServiceError
from app.schemas import PatientCreate, PatientRead, PatientUpdate
from app.services import patients
from app.voice.models import ToolReceipt, VoiceSession
from app.voice.schemas import (
    ConfirmInput,
    EmptyInput,
    FieldsInput,
    LookupInput,
    PrepareInput,
    ToolCall,
    normalize_fields,
)

logger = logging.getLogger(__name__)


def failure(code: str, message: str, details=None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "details": details or []}}


def lock_session(session: Session, call_id: str) -> VoiceSession:
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    session.execute(insert(VoiceSession).values(call_id=call_id).on_conflict_do_nothing())
    # PostgreSQL serializes all tool mutations for a call. SQLite serializes the
    # preceding INSERT writer transaction, including conflict/no-op attempts.
    return session.scalar(
        select(VoiceSession).where(VoiceSession.call_id == call_id).with_for_update()
    )


def invalidate_draft(voice: VoiceSession) -> None:
    voice.draft = None
    voice.confirmation_token = None
    voice.target_patient_id = None
    voice.target_updated_at = None
    voice.status = "collecting"


def demographic_data(patient) -> dict:
    return PatientRead.model_validate(patient).model_dump(
        mode="json", include=set(PatientCreate.model_fields)
    )


def readback(payload: dict) -> str:
    # Return every stored, non-null demographic (including the default language).
    labels = {
        "first_name": "first name",
        "last_name": "last name",
        "date_of_birth": "date of birth",
        "sex": "sex",
        "phone_number": "phone number",
        "email": "email",
        "address_line_1": "street address",
        "address_line_2": "apartment or unit",
        "city": "city",
        "state": "state",
        "zip_code": "ZIP code",
        "insurance_provider": "insurance provider",
        "insurance_member_id": "insurance member ID",
        "preferred_language": "preferred language",
        "emergency_contact_name": "emergency contact",
        "emergency_contact_phone": "emergency contact phone",
    }
    parts = [
        f"{label}: {payload[key]}" for key, label in labels.items() if payload.get(key) is not None
    ]
    return "Please confirm these details. " + "; ".join(parts) + ". Is all of that correct?"


def execute_action(session: Session, voice: VoiceSession, name: str, args: dict) -> dict:
    if voice.ended_at is not None:
        raise ServiceError(
            409, "call_ended", "The call has ended. Do not save any further changes."
        )
    if voice.status == "saved" and name != "confirm_registration":
        raise ServiceError(
            409, "already_completed", "This call already saved a patient. End gracefully."
        )

    if name == "validate_fields":
        invalidate_draft(voice)
        fields = FieldsInput.model_validate(args)
        payload = PatientUpdate.model_validate(normalize_fields(fields.fields))
        return {"ok": True, "fields": payload.model_dump(mode="json", exclude_unset=True)}

    if name == "lookup_patient":
        lookup = LookupInput.model_validate(args)
        matches = patients.list_patients(
            session, phone_number=lookup.phone_number, date_of_birth=lookup.date_of_birth
        )
        voice.verified_patient_ids = [str(patient.patient_id) for patient in matches]
        return {
            "ok": True,
            "matches": [PatientRead.model_validate(p).model_dump(mode="json") for p in matches],
        }

    if name == "start_over":
        EmptyInput.model_validate(args)
        invalidate_draft(voice)
        voice.verified_patient_ids = []
        return {
            "ok": True,
            "status": "started_over",
            "instruction": "Discard previous answers and collect anew.",
        }

    if name == "prepare_registration":
        invalidate_draft(voice)
        request = PrepareInput.model_validate(args)
        supplied = normalize_fields(request.patient)
        if request.patient_id is not None:
            if str(request.patient_id) not in voice.verified_patient_ids:
                raise ServiceError(
                    409,
                    "lookup_required",
                    "Look up the patient by phone and DOB before preparing an update.",
                )
            current = patients.get_patient(session, request.patient_id, for_update=True)
            # Validate the patch independently so unknown/immutable fields cannot be injected.
            patch = PatientUpdate.model_validate(supplied).model_dump(
                mode="json", exclude_unset=True
            )
            supplied = demographic_data(current) | patch
            voice.target_patient_id = current.patient_id
            voice.target_updated_at = current.updated_at
        payload = PatientCreate.model_validate(supplied).model_dump(mode="json")
        voice.draft = payload
        voice.confirmation_token = uuid4()
        voice.status = "prepared"
        return {
            "ok": True,
            "status": "awaiting_confirmation",
            "patient": payload,
            "confirmation_token": str(voice.confirmation_token),
            "readback": readback(payload),
            "instruction": (
                "Read back ALL these details, then wait for a new caller response. "
                "Nothing is saved yet."
            ),
        }

    if name == "confirm_registration":
        request = ConfirmInput.model_validate(args)
        if voice.status == "saved":
            if not request.confirmed or request.confirmation_token != voice.confirmation_token:
                raise ServiceError(
                    409, "already_completed", "This call already saved a patient. End gracefully."
                )
            patient = patients.get_patient(session, voice.patient_id)
            return {
                "ok": True,
                "status": "saved",
                "patient": PatientRead.model_validate(patient).model_dump(mode="json"),
                "already_saved": True,
            }
        if not request.confirmed:
            invalidate_draft(voice)
            return {
                "ok": True,
                "status": "not_saved",
                "instruction": "Ask for corrections, prepare again, and reconfirm.",
            }
        if request.confirmation_token != voice.confirmation_token:
            raise ServiceError(
                409,
                "stale_confirmation",
                "Prepare current details and obtain a new confirmation before saving.",
            )
        if voice.status != "prepared" or voice.draft is None:
            raise ServiceError(
                409, "not_prepared", "Validate and read back the patient information before saving."
            )
        payload = PatientCreate.model_validate(voice.draft)
        if voice.target_patient_id:
            current = patients.get_patient(session, voice.target_patient_id, for_update=True)
            if current.updated_at != voice.target_updated_at:
                invalidate_draft(voice)
                raise ServiceError(
                    409,
                    "record_changed",
                    "The record changed. Look it up again, read back, and reconfirm.",
                )
            patient = patients.update_patient(
                session,
                current.patient_id,
                PatientUpdate.model_validate(payload.model_dump()),
                commit=False,
            )
        else:
            patient = patients.create_patient(session, payload, commit=False)
        voice.patient_id = patient.patient_id
        voice.status = "saved"
        voice.draft = None
        return {
            "ok": True,
            "status": "saved",
            "patient": PatientRead.model_validate(patient).model_dump(mode="json"),
        }

    raise ServiceError(
        400, "unknown_tool", "That tool is not available. Use a documented registration tool."
    )


def process_tool(session: Session, call_id: str, tool: ToolCall) -> dict[str, Any]:
    try:
        arguments = tool.parsed_arguments()
    except (ValueError, TypeError):
        # A malformed correction must invalidate previously prepared information too.
        if tool.name in {"prepare_registration", "validate_fields"}:
            voice = lock_session(session, call_id)
            if voice.status != "saved" and voice.ended_at is None:
                invalidate_draft(voice)
                session.commit()
        return failure(
            "invalid_arguments",
            "Tool arguments must be a valid JSON object. Retry with corrected arguments.",
        )
    fingerprint = hashlib.sha256(
        json.dumps([tool.name, arguments], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    voice = lock_session(session, call_id)
    receipt = session.get(ToolReceipt, (call_id, tool.id))
    if receipt is not None:
        result = (
            receipt.result
            if receipt.request_hash == fingerprint
            else failure(
                "tool_id_conflict", "This tool-call ID was already used with different arguments."
            )
        )
        session.commit()
        return result
    try:
        result = execute_action(session, voice, tool.name, arguments)
    except ValidationError as exc:
        result = failure(
            "validation_error",
            "Ask the caller to correct only the indicated fields.",
            [
                {"field": ".".join(map(str, error["loc"])), "message": error["msg"]}
                for error in exc.errors(include_input=False, include_context=False)
            ],
        )
    except ServiceError as exc:
        result = failure(exc.code, exc.message)
    voice.updated_at = utc_now()
    session.add(
        ToolReceipt(call_id=call_id, tool_call_id=tool.id, request_hash=fingerprint, result=result)
    )
    session.commit()  # The receipt and patient write are one transaction.
    if result.get("status") == "saved" and not result.get("already_saved"):
        logger.info(
            "voice_registration_confirmed %s",
            json.dumps({"call_id": call_id, "patient": result["patient"]}),
        )
    return result


def end_call(session: Session, call_id: str, reason: str | None, transcript: str | None) -> None:
    voice = lock_session(session, call_id)
    if voice.ended_at is None:
        voice.ended_at = utc_now()
    if reason:
        voice.ended_reason = reason
    if isinstance(transcript, str):
        voice.transcript = transcript[:100_000]
    if voice.status != "saved":
        invalidate_draft(voice)
        voice.status = "cancelled"
    session.commit()
    logger.info("voice_call_ended call_id=%s status=%s", call_id, voice.status)
