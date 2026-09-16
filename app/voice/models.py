from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, utc_now


class VoiceSession(Base):
    __tablename__ = "voice_sessions"

    call_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(16), default="collecting", server_default="collecting"
    )
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    confirmation_token: Mapped[UUID | None] = mapped_column(Uuid)
    verified_patient_ids: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    target_patient_id: Mapped[UUID | None] = mapped_column(ForeignKey("patients.patient_id"))
    target_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    patient_id: Mapped[UUID | None] = mapped_column(ForeignKey("patients.patient_id"), index=True)
    transcript: Mapped[str | None] = mapped_column(Text)
    ended_reason: Mapped[str | None] = mapped_column(String(200))
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, onupdate=utc_now, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('collecting', 'prepared', 'saved', 'cancelled')", name="status_values"
        ),
    )


class ToolReceipt(Base):
    __tablename__ = "voice_tool_receipts"

    call_id: Mapped[str] = mapped_column(ForeignKey("voice_sessions.call_id"), primary_key=True)
    tool_call_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, server_default=func.now()
    )
