from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select

from app.models import StaffUser
from app.services.auth_service import authenticate_staff

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


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="staff_login.html",
        context={"error": False},
    )


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request) -> Response:
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    with request.app.state.session_factory() as db:
        user = authenticate_staff(db, username, password)
        user_id = user.id if user is not None else None

    if user_id is None:
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="staff_login.html",
            context={"error": True},
            status_code=401,
        )

    request.session.clear()
    request.session["staff_user_id"] = user_id
    return RedirectResponse("/staff", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/staff/login", status_code=303)


@router.get("", response_class=HTMLResponse)
def staff_home(_staff: CurrentStaff) -> HTMLResponse:
    return HTMLResponse("<h1>Staff registration search</h1>")
