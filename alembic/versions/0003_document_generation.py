"""Allow document-generation audit records."""

import sqlalchemy as sa

from alembic import op

revision = "0003_document_generation"
down_revision = "0002_staff_verification"
branch_labels = None
depends_on = None

OLD_ACTIONS = (
    "REGISTRATION_EDITED",
    "REGISTRATION_VERIFIED",
    "REGISTRATION_REJECTED",
)
NEW_ACTIONS = (*OLD_ACTIONS, "DOCUMENT_GENERATED")


def audit_action_enum(actions: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *actions,
        name="audit_action",
        native_enum=False,
        create_constraint=True,
    )


def replace_audit_action_constraint(
    existing_actions: tuple[str, ...], target_actions: tuple[str, ...]
) -> None:
    with op.batch_alter_table("audit_logs", recreate="always") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=audit_action_enum(existing_actions),
            type_=audit_action_enum(target_actions),
            existing_nullable=False,
        )


def upgrade() -> None:
    replace_audit_action_constraint(OLD_ACTIONS, NEW_ACTIONS)


def downgrade() -> None:
    document_audit_count = op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM audit_logs "
            "WHERE action = 'DOCUMENT_GENERATED'"
        )
    )
    if document_audit_count:
        raise RuntimeError(
            "Cannot downgrade while DOCUMENT_GENERATED audit rows exist"
        )
    replace_audit_action_constraint(NEW_ACTIONS, OLD_ACTIONS)
