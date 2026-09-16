import logging
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utc_now
from app.errors import ServiceError
from app.models import Patient
from app.schemas import PatientCreate, PatientUpdate

logger = logging.getLogger(__name__)


def get_patient(session: Session, patient_id: UUID, *, for_update: bool = False) -> Patient:
    query = select(Patient).where(Patient.patient_id == patient_id, Patient.deleted_at.is_(None))
    patient = session.scalar(query.with_for_update() if for_update else query)
    if patient is None:
        raise ServiceError(404, "patient_not_found", "Patient not found")
    return patient


def list_patients(
    session: Session,
    *,
    last_name: str | None = None,
    date_of_birth: date | None = None,
    phone_number: str | None = None,
) -> list[Patient]:
    query = select(Patient).where(Patient.deleted_at.is_(None))
    if last_name is not None:
        query = query.where(func.lower(Patient.last_name) == last_name.lower())
    if date_of_birth is not None:
        query = query.where(Patient.date_of_birth == date_of_birth)
    if phone_number is not None:
        query = query.where(Patient.phone_number == phone_number)
    return list(session.scalars(query.order_by(Patient.created_at, Patient.patient_id)))


def create_patient(session: Session, payload: PatientCreate, *, commit: bool = True) -> Patient:
    now = utc_now()
    patient = Patient(**payload.model_dump(), created_at=now, updated_at=now)
    session.add(patient)
    if commit:
        session.commit()
        logger.info("patient_created patient_id=%s", patient.patient_id)
    else:
        session.flush()
    return patient


def update_patient(
    session: Session, patient_id: UUID, payload: PatientUpdate, *, commit: bool = True
) -> Patient:
    patient = get_patient(session, patient_id, for_update=True)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise ServiceError(400, "empty_update", "Provide at least one field to update")
    for name, value in changes.items():
        setattr(patient, name, value)
    patient.updated_at = utc_now()
    if commit:
        session.commit()
        logger.info("patient_updated patient_id=%s", patient.patient_id)
    else:
        session.flush()
    return patient


def delete_patient(session: Session, patient_id: UUID) -> Patient:
    patient = get_patient(session, patient_id)
    patient.deleted_at = patient.updated_at = utc_now()
    session.commit()
    logger.info("patient_deleted patient_id=%s", patient.patient_id)
    return patient
