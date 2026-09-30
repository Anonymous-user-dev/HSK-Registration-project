from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.database import create_database_engine, create_session_factory
from app.models import Base
from app.routes.student import router as student_router

APP_DIR = Path(__file__).parent


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="HSK Pre-Registration", docs_url=None, redoc_url=None)
    application.state.settings = settings or Settings.from_env()
    application.state.engine = create_database_engine(
        application.state.settings.database_url
    )
    application.state.session_factory = create_session_factory(application.state.engine)
    application.state.templates = Jinja2Templates(directory=APP_DIR / "templates")
    Base.metadata.create_all(application.state.engine)

    application.mount(
        "/static", StaticFiles(directory=APP_DIR / "static"), name="static"
    )
    application.include_router(student_router)

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
        return response

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
