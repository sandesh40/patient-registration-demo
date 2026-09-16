import json
import re
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, field_validator

from app.schemas import BirthDate, InputModel, Phone


def normalize_phone(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    # Only strip actual formatting, never arbitrary letters or wrong-length digits.
    if not re.fullmatch(r"[+0-9().\s-]+", value):
        return value
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: normalize_phone(value) if key in {"phone_number", "emergency_contact_phone"} else value
        for key, value in fields.items()
    }


class FieldsInput(InputModel):
    fields: dict[str, Any] = Field(min_length=1, max_length=16)


class LookupInput(InputModel):
    phone_number: Annotated[Phone, BeforeValidator(normalize_phone)]
    date_of_birth: BirthDate


class PrepareInput(InputModel):
    patient: dict[str, Any] = Field(min_length=1, max_length=16)
    patient_id: UUID | None = None


class ConfirmInput(InputModel):
    confirmation_token: UUID
    confirmed: StrictBool


class EmptyInput(InputModel):
    pass


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    arguments: Any = Field(default_factory=dict)

    @classmethod
    def from_vapi(cls, raw: dict) -> "ToolCall":
        # Vapi emits both OpenAI-style nested calls and flat toolCallList entries.
        function = raw.get("function") or raw
        return cls(
            id=raw.get("id"),
            name=function.get("name"),
            arguments=function.get("arguments", function.get("parameters", {})),
        )

    def parsed_arguments(self) -> dict[str, Any]:
        value = json.loads(self.arguments) if isinstance(self.arguments, str) else self.arguments
        if not isinstance(value, dict):
            raise ValueError("Tool arguments must be an object")
        return value


class CallContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1, max_length=128)
    assistantId: str | None = None


class VapiMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str = Field(min_length=1, max_length=100)
    call: CallContext
    toolCallList: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    toolWithToolCallList: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    artifact: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    endedReason: str | None = Field(default=None, max_length=200)

    @field_validator("toolCallList", "toolWithToolCallList", mode="before")
    @classmethod
    def null_list(cls, value):
        return [] if value is None else value

    def tools(self) -> list[ToolCall]:
        if self.toolCallList:
            calls = [ToolCall.from_vapi(raw) for raw in self.toolCallList]
        else:
            calls = []
            for item in self.toolWithToolCallList:
                raw = dict(item.get("toolCall", {}))
                raw.setdefault("name", item.get("name"))
                calls.append(ToolCall.from_vapi(raw))
        if not calls or len({call.id for call in calls}) != len(calls):
            raise ValueError("Supply at least one tool call with unique IDs")
        return calls


class VapiRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: VapiMessage
