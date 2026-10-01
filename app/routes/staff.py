from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select

from app.csrf import get_csrf_token, validate_csrf_token
from app.models import HSKLevel, RegistrationStatus, StaffUser
from app.schemas import RegistrationUpdate
from app.services.auth_service import authenticate_staff
from app.services.registration_service import (
    CODE_PATTERN,
    find_registration_by_code,
)
from app.services.verification_service import (
    RegistrationConflictError,
    RegistrationNotFoundError,
    RegistrationStateError,
    update_pending_registration,
)

router = APIRouter(prefix="/staff")


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

    if registration is None:
        return _registration_not_found(request)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_registration.html",
        context={
            "registration": registration,
            "csrf_token": get_csrf_token(request),
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
