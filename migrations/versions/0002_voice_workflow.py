"""Persist voice drafts, confirmation state, transcripts, and retry receipts.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("call_id", sa.String(128), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="collecting"),
        sa.Column("draft", sa.JSON(none_as_null=True)),
        sa.Column("confirmation_token", sa.Uuid()),
        sa.Column("verified_patient_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("target_patient_id", sa.Uuid(), sa.ForeignKey("patients.patient_id")),
        sa.Column("target_updated_at", sa.DateTime(timezone=True)),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.patient_id")),
        sa.Column("transcript", sa.Text()),
        sa.Column("ended_reason", sa.String(200)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('collecting', 'prepared', 'saved', 'cancelled')", name="status_values"
        ),
    )
    op.create_index("ix_voice_sessions_patient_id", "voice_sessions", ["patient_id"])
    op.create_table(
        "voice_tool_receipts",
        sa.Column(
            "call_id", sa.String(128), sa.ForeignKey("voice_sessions.call_id"), primary_key=True
        ),
        sa.Column("tool_call_id", sa.String(128), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE voice_sessions ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE voice_tool_receipts ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("voice_tool_receipts")
    op.drop_index("ix_voice_sessions_patient_id", table_name="voice_sessions")
    op.drop_table("voice_sessions")
