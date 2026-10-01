import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings
from app.database import create_database_engine, create_session_factory
from app.models import Base
from app.routes.staff import router as staff_router
from app.routes.student import router as student_router

APP_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    engine = create_database_engine(app_settings.database_url)

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="HSK Pre-Registration",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.engine = engine
    application.state.session_factory = create_session_factory(engine)
    application.state.templates = Jinja2Templates(directory=APP_DIR / "templates")
    Base.metadata.create_all(engine)
    engine.dispose()

    application.add_middleware(
        SessionMiddleware,
        secret_key=application.state.settings.session_secret,
        session_cookie="hsk_staff_session",
        max_age=8 * 60 * 60,
        same_site="lax",
        https_only=application.state.settings.secure_cookies,
    )

    application.mount(
        "/static", StaticFiles(directory=APP_DIR / "static"), name="static"
    )
    application.include_router(student_router)
    application.include_router(staff_router)

    @application.exception_handler(SQLAlchemyError)
    async def handle_database_error(_request, _error) -> JSONResponse:
        logger.error("Database operation failed while processing request")
        return JSONResponse(
            status_code=500,
            content={"detail": "Request could not be completed"},
        )

    @application.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
        )
        if request.url.path.startswith(("/staff", "/registration")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        if app_settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
