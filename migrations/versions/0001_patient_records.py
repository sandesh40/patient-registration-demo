"""Create persistent patient records and their database constraints.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    constraints = [
        sa.CheckConstraint(
            sa.func.length(sa.column(name)).between(1, maximum)
            & (sa.func.length(sa.func.trim(sa.column(name))) > 0),
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
    ]
    # SQLAlchemy compiles these as PostgreSQL ~ or SQLite REGEXP. Do not freeze
    # a SQLite-specific operator into a migration intended for Supabase.
    constraints.extend(
        sa.CheckConstraint(sa.column(name).regexp_match(pattern), name=f"{name}_format")
        for name, pattern in {
            "first_name": "^[A-Za-z'-]+$",
            "last_name": "^[A-Za-z'-]+$",
            "phone_number": "^[2-9][0-9]{2}[2-9][0-9]{6}$",
            "emergency_contact_phone": "^[2-9][0-9]{2}[2-9][0-9]{6}$",
            "zip_code": "^[0-9]{5}(-[0-9]{4})?$",
            "insurance_member_id": "^[A-Za-z0-9]+$",
        }.items()
    )
    constraints.extend(
        sa.CheckConstraint(sa.column(name).regexp_match("[A-Za-z]"), name=f"{name}_letter")
        for name in ("first_name", "last_name")
    )
    states = [
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
    constraints.extend(
        [
            sa.CheckConstraint(sa.column("state").in_(sorted(set(states))), name="state_values"),
            sa.CheckConstraint("date_of_birth <= CURRENT_DATE", name="date_of_birth_not_future"),
            sa.CheckConstraint("date_of_birth >= '0001-01-01'", name="date_of_birth_positive_year"),
        ]
    )
    op.create_table(
        "patients",
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("first_name", sa.String(50), nullable=False),
        sa.Column("last_name", sa.String(50), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column(
            "sex",
            sa.Enum(
                "Male",
                "Female",
                "Other",
                "Decline to Answer",
                name="sex_values",
                native_enum=False,
                create_constraint=True,
                length=17,
            ),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(10), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("address_line_1", sa.String(200), nullable=False),
        sa.Column("address_line_2", sa.String(200)),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("zip_code", sa.String(10), nullable=False),
        sa.Column("insurance_provider", sa.String(150)),
        sa.Column("insurance_member_id", sa.String(100)),
        sa.Column("preferred_language", sa.String(50), server_default="English", nullable=False),
        sa.Column("emergency_contact_name", sa.String(100)),
        sa.Column("emergency_contact_phone", sa.String(10)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("patient_id"),
        *constraints,
    )
    for name in ("last_name", "date_of_birth", "phone_number", "deleted_at"):
        op.create_index(f"ix_patients_{name}", "patients", [name])
    if op.get_bind().dialect.name == "postgresql":
        # Access is through our authenticated backend using the DB owner. Public
        # Supabase Data API roles receive no policies permitting patient access.
        op.execute("ALTER TABLE patients ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("patients")
