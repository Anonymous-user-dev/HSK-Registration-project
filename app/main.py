from fastapi import FastAPI

from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="HSK Pre-Registration", docs_url=None, redoc_url=None)
    application.state.settings = settings or Settings.from_env()

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
