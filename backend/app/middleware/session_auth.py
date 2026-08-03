from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.config import load_auth_session_settings
from backend.app.db.users import User, get_user_by_idx
from backend.app.services.auth_session import validate_and_touch_session

logger = logging.getLogger(__name__)

PUBLIC_API_ROUTES: set[tuple[str, str]] = {
    ("GET", "/api/auth/provider"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/jobs"),
    ("GET", "/api/release-notes"),
}

PUBLIC_API_PREFIXES: tuple[str, ...] = (
    "/api/debug/",
)

PUBLIC_PATHS: set[str] = {
    "/docs",
    "/openapi.json",
    "/redoc",
}


def extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def is_public_request(method: str, path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if not path.startswith("/api/"):
        return True
    if (method.upper(), path) in PUBLIC_API_ROUTES:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES)


class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.auth_user = None
        request.state.auth_token = None

        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        if is_public_request(request.method, request.url.path):
            return await call_next(request)

        token = extract_bearer_token(request)
        if not token:
            return JSONResponse(status_code=401, content={"detail": "인증이 필요합니다."})

        settings = load_auth_session_settings()
        session = await validate_and_touch_session(
            token,
            ttl_seconds=settings.ttl_seconds,
            absolute_max_seconds=settings.absolute_max_seconds,
        )
        if session is None:
            return JSONResponse(status_code=401, content={"detail": "세션이 만료되었습니다."})

        database_path = request.app.state.database_path
        user = get_user_by_idx(database_path, session.user_idx)
        if user is None:
            logger.warning("Session user not found: idx=%s", session.user_idx)
            return JSONResponse(status_code=401, content={"detail": "사용자를 찾을 수 없습니다."})

        request.state.auth_user = user
        request.state.auth_token = token
        return await call_next(request)


def get_request_auth_user(request: Request) -> User:
    user = getattr(request.state, "auth_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return user
