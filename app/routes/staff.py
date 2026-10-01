from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select

from app.csrf import get_csrf_token, validate_csrf_token
from app.models import StaffUser
from app.services.auth_service import authenticate_staff
from app.services.registration_service import (
    CODE_PATTERN,
    find_registration_by_code,
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


def _registration_not_found(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_registration.html",
        context={"registration": None, "csrf_token": get_csrf_token(request)},
        status_code=404,
    )
