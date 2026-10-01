"""Create the initial registration and staff schema."""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_code", sa.String(length=10), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("nationality", sa.String(length=100), nullable=False),
        sa.Column("passport_number", sa.String(length=32), nullable=False),
        sa.Column("phone_number", sa.String(length=24), nullable=False),
        sa.Column("parent_phone_number", sa.String(length=24), nullable=False),
        sa.Column(
            "hsk_level",
            sa.Enum(
                "HSK1",
                "HSK2",
                "HSK3",
                "HSK4",
                "HSK5",
                "HSK6",
                name="hsk_level",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "VERIFIED",
                "REJECTED",
                name="registration_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_registrations_registration_code",
        "registrations",
        ["registration_code"],
        unique=True,
    )
    op.create_table(
        "staff_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_staff_users_username", "staff_users", ["username"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_staff_users_username", table_name="staff_users")
    op.drop_table("staff_users")
    op.drop_index("ix_registrations_registration_code", table_name="registrations")
    op.drop_table("registrations")
