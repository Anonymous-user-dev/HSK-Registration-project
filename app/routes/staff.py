import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csrf import get_csrf_token, validate_csrf_token
from app.models import (
    AuditAction,
    AuditLog,
    HSKLevel,
    Registration,
    RegistrationStatus,
    StaffUser,
)
from app.schemas import RegistrationUpdate
from app.services.auth_service import authenticate_staff
from app.services.document_service import (
    DocumentTemplateError,
    generate_registration_document,
)
from app.services.registration_service import (
    CODE_PATTERN,
    find_registration_by_code,
)
from app.services.verification_service import (
    RegistrationConflictError,
    RegistrationNotFoundError,
    RegistrationStateError,
    reject_registration,
    update_pending_registration,
    verify_registration,
)

router = APIRouter(prefix="/staff")
logger = logging.getLogger(__name__)


def require_staff(request: Request) -> StaffUser:
    staff_user_id = request.session.get("staff_user_id")
    if not isinstance(staff_user_id, int):
        raise HTTPException(status_code=303, headers={"Location": "/staff/login"})

    with request.app.state.session_factory() as db:
        user = db.scalar(
            select(StaffUser).where(
                StaffUser.id == staff_user_id, StaffUser.is_active.is_(True)
            )
        )
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/staff/login"})
    return user


CurrentStaff = Annotated[StaffUser, Depends(require_staff)]


def require_registration_staff(request: Request) -> StaffUser:
    user = require_staff(request)
    if user.role != "REGISTRATION_STAFF":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


RegistrationStaff = Annotated[StaffUser, Depends(require_registration_staff)]


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_login.html",
        context={"error": False, "csrf_token": get_csrf_token(request)},
    )


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request) -> Response:
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))
    validate_csrf_token(request, str(form.get("csrf_token", "")))

    with request.app.state.session_factory() as db:
        user = authenticate_staff(db, username, password)
        user_id = user.id if user is not None else None

    if user_id is None:
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="staff_login.html",
            context={"error": True, "csrf_token": get_csrf_token(request)},
            status_code=401,
        )

    request.session.clear()
    request.session["staff_user_id"] = user_id
    get_csrf_token(request)
    return RedirectResponse("/staff", status_code=303)


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    form = await request.form()
    validate_csrf_token(request, str(form.get("csrf_token", "")))
    request.session.clear()
    return RedirectResponse("/staff/login", status_code=303)


@router.get("", response_class=HTMLResponse)
def staff_home(request: Request, _staff: CurrentStaff) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_search.html",
        context={"csrf_token": get_csrf_token(request)},
    )


@router.get("/registrations", response_class=HTMLResponse)
def submit_search(request: Request, code: str, _staff: CurrentStaff) -> Response:
    normalized = code.strip().upper()
    if CODE_PATTERN.fullmatch(normalized) is None:
        return _registration_not_found(request)
    return RedirectResponse(f"/staff/registrations/{normalized}", status_code=303)


@router.get("/registrations/{code}", response_class=HTMLResponse)
def registration_detail(
    request: Request, code: str, _staff: CurrentStaff
) -> HTMLResponse:
    with request.app.state.session_factory() as db:
        registration = find_registration_by_code(db, code)
        audit_details = None
        if (
            registration is not None
            and registration.status is not RegistrationStatus.PENDING
        ):
            audit_details = db.execute(
                select(AuditLog, StaffUser.username)
                .join(StaffUser, StaffUser.id == AuditLog.staff_user_id)
                .where(AuditLog.registration_id == registration.id)
                .order_by(AuditLog.id.desc())
                .limit(1)
            ).one_or_none()

    if registration is None:
        return _registration_not_found(request)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_registration.html",
        context={
            "registration": registration,
            "csrf_token": get_csrf_token(request),
            "audit_log": audit_details[0] if audit_details else None,
            "audit_staff_username": audit_details[1] if audit_details else None,
        },
    )


@router.get("/registrations/{code}/edit", response_class=HTMLResponse)
def registration_edit_form(
    request: Request, code: str, _staff: RegistrationStaff
) -> HTMLResponse:
    with request.app.state.session_factory() as db:
        registration = find_registration_by_code(db, code)

    if registration is None:
        return _registration_not_found(request)
    if registration.status is not RegistrationStatus.PENDING:
        return _edit_conflict(request, "Registration cannot be edited")
    return _registration_edit_response(request, registration)


@router.post("/registrations/{code}/edit", response_class=HTMLResponse)
async def registration_edit(
    request: Request, code: str, staff: RegistrationStaff
) -> Response:
    form = await request.form()
    validate_csrf_token(request, str(form.get("csrf_token", "")))

    with request.app.state.session_factory() as db:
        registration = find_registration_by_code(db, code)
        if registration is None:
            return _registration_not_found(request)
        if registration.status is not RegistrationStatus.PENDING:
            return _edit_conflict(request, "Registration cannot be edited")

        try:
            expected_version = int(str(form.get("version", "")))
            data = RegistrationUpdate.model_validate(
                {
                    field: form.get(field, "")
                    for field in RegistrationUpdate.model_fields
                }
            )
        except (TypeError, ValueError, ValidationError):
            return _registration_edit_response(
                request, registration, validation_error=True, status_code=422
            )

        try:
            update_pending_registration(
                db,
                registration.id,
                staff.id,
                expected_version,
                data,
            )
        except RegistrationNotFoundError:
            return _registration_not_found(request)
        except (RegistrationConflictError, RegistrationStateError):
            return _edit_conflict(
                request, "Reload the registration before making another correction"
            )

    normalized_code = code.strip().upper()
    return RedirectResponse(
        f"/staff/registrations/{normalized_code}", status_code=303
    )


@router.post("/registrations/{code}/verify", response_class=HTMLResponse)
async def registration_verify(
    request: Request, code: str, staff: RegistrationStaff
) -> Response:
    return await _transition_response(
        request, code, staff, transition=verify_registration
    )


@router.post("/registrations/{code}/reject", response_class=HTMLResponse)
async def registration_reject(
    request: Request, code: str, staff: RegistrationStaff
) -> Response:
    return await _transition_response(
        request, code, staff, transition=reject_registration
    )


@router.post("/registrations/{code}/document")
async def registration_document(
    request: Request, code: str, staff: RegistrationStaff
) -> Response:
    form = await request.form()
    validate_csrf_token(request, str(form.get("csrf_token", "")))

    with request.app.state.session_factory() as db:
        registration = find_registration_by_code(db, code)
        if registration is None:
            return _registration_not_found(request)
        if registration.status is not RegistrationStatus.VERIFIED:
            return HTMLResponse("Document is not available", status_code=409)
        verified_by_username = db.scalar(
            select(StaffUser.username).where(
                StaffUser.id == registration.verified_by
            )
        )
        if verified_by_username is None:
            logger.error("Registration document verifier could not be resolved")
            return HTMLResponse("Document is temporarily unavailable", status_code=503)

        try:
            content = generate_registration_document(
                registration,
                verified_by_username,
                request.app.state.settings.document_template_path,
            )
        except DocumentTemplateError:
            logger.error("Registration document template could not be processed")
            return HTMLResponse("Document is temporarily unavailable", status_code=503)
        db.add(
            AuditLog(
                registration_id=registration.id,
                staff_user_id=staff.id,
                action=AuditAction.DOCUMENT_GENERATED,
                changed_fields=[],
            )
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    normalized_code = code.strip().upper()
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="hsk_registration_{normalized_code}.docx"'
            )
        },
    )


async def _transition_response(
    request: Request,
    code: str,
    staff: StaffUser,
    *,
    transition: Callable[[Session, int, int, int], Registration],
) -> Response:
    form = await request.form()
    validate_csrf_token(request, str(form.get("csrf_token", "")))

    with request.app.state.session_factory() as db:
        registration = find_registration_by_code(db, code)
        if registration is None:
            return _registration_not_found(request)
        try:
            expected_version = int(str(form.get("version", "")))
        except ValueError:
            return _edit_conflict(request, "Reload the registration before continuing")

        try:
            transition(db, registration.id, staff.id, expected_version)
        except RegistrationNotFoundError:
            return _registration_not_found(request)
        except (RegistrationConflictError, RegistrationStateError):
            return _edit_conflict(
                request, "Reload the registration before continuing"
            )

    normalized_code = code.strip().upper()
    return RedirectResponse(
        f"/staff/registrations/{normalized_code}", status_code=303
    )


def _registration_edit_response(
    request: Request,
    registration,
    *,
    validation_error: bool = False,
    status_code: int = 200,
) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_registration_edit.html",
        context={
            "registration": registration,
            "hsk_levels": HSKLevel,
            "csrf_token": get_csrf_token(request),
            "validation_error": validation_error,
            "conflict_message": None,
        },
        status_code=status_code,
    )


def _edit_conflict(request: Request, message: str) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_registration_edit.html",
        context={
            "registration": None,
            "hsk_levels": HSKLevel,
            "csrf_token": get_csrf_token(request),
            "validation_error": False,
            "conflict_message": message,
        },
        status_code=409,
    )


def _registration_not_found(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_registration.html",
        context={"registration": None, "csrf_token": get_csrf_token(request)},
        status_code=404,
    )
