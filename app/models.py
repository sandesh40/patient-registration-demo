import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, Enum, Index, String, Uuid, column, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, utc_now

US_STATES = frozenset(
    [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    ]
)


class Sex(StrEnum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE = "Decline to Answer"


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex: Mapped[Sex] = mapped_column(
        Enum(
            Sex,
            values_callable=lambda enum: [member.value for member in enum],
            native_enum=False,
            create_constraint=True,
            name="sex_values",
            length=17,
        )
    )
    phone_number: Mapped[str] = mapped_column(String(10))
    email: Mapped[str | None] = mapped_column(String(254))
    address_line_1: Mapped[str] = mapped_column(String(200))
    address_line_2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2))
    zip_code: Mapped[str] = mapped_column(String(10))
    insurance_provider: Mapped[str | None] = mapped_column(String(150))
    insurance_member_id: Mapped[str | None] = mapped_column(String(100))
    preferred_language: Mapped[str] = mapped_column(
        String(50), default="English", server_default="English"
    )
    emergency_contact_name: Mapped[str | None] = mapped_column(String(100))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, onupdate=utc_now, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    __table_args__ = (
        *[
            CheckConstraint(
                func.length(column(name)).between(1, maximum)
                & (func.length(func.trim(column(name))) > 0),
                name=f"{name}_length",
            )
            for name, maximum in {
                "first_name": 50,
                "last_name": 50,
                "address_line_1": 200,
                "address_line_2": 200,
                "city": 100,
                "insurance_provider": 150,
                "insurance_member_id": 100,
                "preferred_language": 50,
                "emergency_contact_name": 100,
                "email": 254,
            }.items()
        ],
        *[
            CheckConstraint(column(name).regexp_match(pattern), name=f"{name}_format")
            for name, pattern in {
                "first_name": "^[A-Za-z'-]+$",
                "last_name": "^[A-Za-z'-]+$",
                "phone_number": "^[2-9][0-9]{2}[2-9][0-9]{6}$",
                "emergency_contact_phone": "^[2-9][0-9]{2}[2-9][0-9]{6}$",
                "zip_code": "^[0-9]{5}(-[0-9]{4})?$",
                "insurance_member_id": "^[A-Za-z0-9]+$",
            }.items()
        ],
        *[
            CheckConstraint(column(name).regexp_match("[A-Za-z]"), name=f"{name}_letter")
            for name in ("first_name", "last_name")
        ],
        CheckConstraint(column("state").in_(sorted(US_STATES)), name="state_values"),
        CheckConstraint("date_of_birth <= CURRENT_DATE", name="date_of_birth_not_future"),
        CheckConstraint("date_of_birth >= '0001-01-01'", name="date_of_birth_positive_year"),
        Index("ix_patients_last_name", "last_name"),
        Index("ix_patients_date_of_birth", "date_of_birth"),
        Index("ix_patients_phone_number", "phone_number"),
        Index("ix_patients_deleted_at", "deleted_at"),
    )
