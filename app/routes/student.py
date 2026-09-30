from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import HSKLevel
from app.schemas import RegistrationCreate
from app.services.registration_service import (
    create_registration,
    find_registration_by_code,
)

router = APIRouter()
DatabaseSession = Annotated[Session, Depends(get_db)]


def _templates(request: Request):
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse)
def registration_form(request: Request) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="registration_form.html",
        context={"hsk_levels": list(HSKLevel), "errors": []},
    )


@router.post("/registrations", response_class=HTMLResponse)
async def submit_registration(
    request: Request, db: DatabaseSession
) -> Response:
    form = await request.form()
    submitted = {
        field: form.get(field, "")
        for field in RegistrationCreate.model_fields
    }
    try:
        data = RegistrationCreate.model_validate(submitted)
    except ValidationError as error:
        error_fields = sorted(
            {
                str(item["loc"][0]).replace("_", " ").title()
                for item in error.errors()
            }
        )
        return _templates(request).TemplateResponse(
            request=request,
            name="registration_form.html",
            context={"hsk_levels": list(HSKLevel), "errors": error_fields},
            status_code=422,
        )

    registration = create_registration(db, data)
    return RedirectResponse(
        url=f"/registration/success/{registration.registration_code}",
        status_code=303,
    )


@router.get("/registration/success/{code}", response_class=HTMLResponse)
def registration_success(
    request: Request, code: str, db: DatabaseSession
) -> HTMLResponse:
    registration = find_registration_by_code(db, code)
    if registration is None:
        return _templates(request).TemplateResponse(
            request=request,
            name="registration_success.html",
            context={"registration_code": None},
            status_code=404,
        )
    return _templates(request).TemplateResponse(
        request=request,
        name="registration_success.html",
        context={"registration_code": registration.registration_code},
    )
