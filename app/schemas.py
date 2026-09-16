import re
from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
    field_validator,
)

from app.db import utc_now
from app.models import US_STATES, Sex


def clean_text(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Control characters are not allowed")
    return value


def text_type(max_length: int):
    return Annotated[
        str,
        StringConstraints(min_length=1, max_length=max_length),
        BeforeValidator(clean_text),
    ]


def validate_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z'-]+", value) or not re.search(r"[A-Za-z]", value):
        raise ValueError("Use letters, hyphens, or apostrophes, including at least one letter")
    return value


def validate_phone(value: str) -> str:
    # Require canonical ten-digit NANP format. Avoid carrier lookups: fictional
    # demo numbers must work, and ten digits alone cannot establish US ownership.
    if not re.fullmatch(r"[2-9][0-9]{2}[2-9][0-9]{6}", value):
        raise ValueError("Use a 10-digit U.S. phone number, without +1 or punctuation")
    return value


def parse_birth_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", value):
        try:
            result = datetime.strptime(value, "%m/%d/%Y").date()
        except ValueError as exc:
            raise ValueError("Use a valid date in MM/DD/YYYY format") from exc
    else:
        raise ValueError("Use MM/DD/YYYY format")
    if result > utc_now().date():
        raise ValueError("Date of birth cannot be in the future")
    return result


def format_birth_date(value: date) -> str:
    return f"{value.month:02}/{value.day:02}/{value.year:04}"


def validate_state(value: str) -> str:
    value = value.upper()
    if value not in US_STATES:
        raise ValueError("Use a valid two-letter U.S. state abbreviation (or DC)")
    return value


Name = Annotated[text_type(50), AfterValidator(validate_name)]
Phone = Annotated[text_type(10), AfterValidator(validate_phone)]
BirthDate = Annotated[
    date,
    BeforeValidator(parse_birth_date),
    PlainSerializer(format_birth_date, return_type=str, when_used="json"),
    WithJsonSchema(
        {"type": "string", "pattern": r"^\d{2}/\d{2}/\d{4}$", "examples": ["04/15/1990"]}
    ),
]
State = Annotated[text_type(2), AfterValidator(validate_state)]
ZipCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{5}(-[0-9]{4})?$", max_length=10)]
MemberID = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9]+$", max_length=100)]
Email = Annotated[EmailStr, Field(max_length=254)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def sanitize_text(cls, value: Any) -> Any:
        return clean_text(value)


class PatientCreate(InputModel):
    first_name: Name
    last_name: Name
    date_of_birth: BirthDate
    sex: Sex
    phone_number: Phone
    email: Email | None = None
    address_line_1: text_type(200)
    address_line_2: text_type(200) | None = None
    city: text_type(100)
    state: State
    zip_code: ZipCode
    insurance_provider: text_type(150) | None = None
    insurance_member_id: MemberID | None = None
    preferred_language: text_type(50) = "English"
    emergency_contact_name: text_type(100) | None = None
    emergency_contact_phone: Phone | None = None


REQUIRED_FIELDS = frozenset(
    name for name, field in PatientCreate.model_fields.items() if field.is_required()
) | {"preferred_language"}


class PatientUpdate(InputModel):
    # Omitted fields are unchanged; explicit null clears only nullable fields.
    first_name: Name | None = None
    last_name: Name | None = None
    date_of_birth: BirthDate | None = None
    sex: Sex | None = None
    phone_number: Phone | None = None
    email: Email | None = None
    address_line_1: text_type(200) | None = None
    address_line_2: text_type(200) | None = None
    city: text_type(100) | None = None
    state: State | None = None
    zip_code: ZipCode | None = None
    insurance_provider: text_type(150) | None = None
    insurance_member_id: MemberID | None = None
    preferred_language: text_type(50) | None = None
    emergency_contact_name: text_type(100) | None = None
    emergency_contact_phone: Phone | None = None

    @field_validator("*", mode="before")
    @classmethod
    def reject_required_nulls(cls, value, info):
        if value is None and info.field_name in REQUIRED_FIELDS:
            raise ValueError("This field cannot be null")
        return value


class PatientRead(PatientCreate):
    model_config = ConfigDict(from_attributes=True)

    patient_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class FieldIssue(BaseModel):
    field: str
    message: str
    code: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[FieldIssue] = Field(default_factory=list)


class Envelope[T](BaseModel):
    data: T | None = None
    error: ErrorDetail | None = None
