from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    database_url: str
    session_secret: str
    secure_cookies: bool

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if environ is None else environ
        environment = values.get("APP_ENV", "development").strip().lower()
        is_production = environment == "production"
        session_secret = values.get("SESSION_SECRET", "").strip()

        if is_production and not session_secret:
            raise ValueError("SESSION_SECRET is required in production")
        if is_production and len(session_secret) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        if not session_secret:
            session_secret = "development-only-change-me"  # noqa: S105

        return cls(
            environment=environment,
            database_url=values.get(
                "DATABASE_URL", "sqlite:///./hsk_registration.db"
            ).strip(),
            session_secret=session_secret,
            secure_cookies=is_production,
        )
