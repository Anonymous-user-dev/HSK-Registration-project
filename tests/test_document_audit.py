from app.models import AuditAction


def test_document_generation_has_a_dedicated_audit_action() -> None:
    assert AuditAction.DOCUMENT_GENERATED.value == "DOCUMENT_GENERATED"
