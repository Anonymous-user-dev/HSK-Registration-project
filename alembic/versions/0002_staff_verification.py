"""Add optimistic versioning and immutable audit records."""

import sqlalchemy as sa

from alembic import op

revision = "0002_staff_verification"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registrations",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "registration_id",
            sa.Integer(),
            sa.ForeignKey("registrations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "staff_user_id",
            sa.Integer(),
            sa.ForeignKey("staff_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.Enum(
                "REGISTRATION_UPDATED",
                "REGISTRATION_VERIFIED",
                "REGISTRATION_REJECTED",
                name="audit_action",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_audit_logs_registration_id", "audit_logs", ["registration_id"]
    )
    op.create_index("ix_audit_logs_staff_user_id", "audit_logs", ["staff_user_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_staff_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_registration_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_column("registrations", "version")
