from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import DatabaseSession, require_api_token
from app.schemas import BirthDate, Envelope, Name, PatientCreate, PatientRead, PatientUpdate, Phone
from app.services import patients

router = APIRouter(
    prefix="/patients",
    tags=["patients"],
    dependencies=[Depends(require_api_token)],
    responses={
        status: {"model": Envelope[None], "description": description}
        for status, description in {
            400: "Malformed JSON or empty update",
            401: "Missing or invalid API token",
            404: "Patient not found",
            422: "Invalid patient data",
            500: "Server or database error",
        }.items()
    },
)


@router.get("", response_model=Envelope[list[PatientRead]])
def list_patients(
    session: DatabaseSession,
    last_name: Annotated[Name | None, Query()] = None,
    date_of_birth: Annotated[BirthDate | None, Query()] = None,
    phone_number: Annotated[Phone | None, Query()] = None,
):
    """List active patients; supplied filters are combined with AND."""
    return {
        "data": patients.list_patients(
            session, last_name=last_name, date_of_birth=date_of_birth, phone_number=phone_number
        ),
        "error": None,
    }


@router.get("/{patient_id}", response_model=Envelope[PatientRead])
def get_patient(patient_id: UUID, session: DatabaseSession):
    return {"data": patients.get_patient(session, patient_id), "error": None}


@router.post("", response_model=Envelope[PatientRead], status_code=201)
def create_patient(payload: PatientCreate, session: DatabaseSession, response: Response):
    patient = patients.create_patient(session, payload)
    response.headers["Location"] = f"/patients/{patient.patient_id}"
    return {"data": patient, "error": None}


@router.put("/{patient_id}", response_model=Envelope[PatientRead])
def update_patient(patient_id: UUID, payload: PatientUpdate, session: DatabaseSession):
    """Update supplied fields only, as specified by this assessment."""
    return {"data": patients.update_patient(session, patient_id, payload), "error": None}


@router.delete("/{patient_id}", response_model=Envelope[PatientRead])
def delete_patient(patient_id: UUID, session: DatabaseSession):
    """Soft-delete and return the record with its UTC deletion timestamp."""
    return {"data": patients.delete_patient(session, patient_id), "error": None}
