import secrets

from fastapi import HTTPException, Request

CSRF_SESSION_KEY = "csrf_token"


def get_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(request: Request, submitted_token: str) -> None:
    session_token = request.session.get(CSRF_SESSION_KEY)
    if not isinstance(session_token, str) or not secrets.compare_digest(
        session_token, submitted_token
    ):
        raise HTTPException(status_code=403, detail="Invalid request token")
