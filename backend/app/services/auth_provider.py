"""Authentication providers: local DB and madang OAuth proxy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from backend.app.config import AuthProviderSettings, load_auth_provider_settings
from backend.app.db.roles import ROLE_PENDING, ROLE_USER
from backend.app.db.users import User, authenticate_user, create_user, get_user_by_userid

logger = logging.getLogger(__name__)


class AuthProviderError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class LoginResult:
    user: User
    profile_required: bool = False


async def verify_madang_credentials(*, oauth_proxy: str, userid: str, password: str) -> bool:
    """Call madang OAuth proxy. Logic-only; tests omitted.

    Expected contract (default):
      POST {OAUTH_PROXY}/login
      JSON body: {"userid": "...", "password": "..."}
      HTTP 2xx => authenticated
    """
    base = oauth_proxy.strip().rstrip("/")
    if not base:
        raise AuthProviderError(500, "OAUTH_PROXY 가 설정되지 않았습니다.")

    url = f"{base}/login"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={"userid": userid, "password": password},
            )
    except httpx.HTTPError as exc:
        logger.warning("Madang OAuth proxy request failed: %s", exc)
        raise AuthProviderError(502, "인증 서버에 연결할 수 없습니다.") from exc

    if response.is_success:
        return True

    logger.info(
        "Madang OAuth proxy rejected login userid=%s status=%s",
        userid,
        response.status_code,
    )
    return False


async def login_with_provider(
    database_path: Path,
    *,
    userid: str,
    password: str,
    settings: AuthProviderSettings | None = None,
) -> LoginResult:
    auth_settings = settings or load_auth_provider_settings()
    normalized_userid = userid.strip()

    if auth_settings.provider_type == "madang":
        is_valid = await verify_madang_credentials(
            oauth_proxy=auth_settings.oauth_proxy,
            userid=normalized_userid,
            password=password,
        )
        if not is_valid:
            raise AuthProviderError(401, "아이디 또는 비밀번호가 올바르지 않습니다.")

        existing = get_user_by_userid(database_path, normalized_userid)
        if existing is not None:
            if existing.role == ROLE_PENDING:
                raise AuthProviderError(
                    403,
                    "가입 승인 대기 중입니다. 관리자에게 문의해 주세요.",
                )
            return LoginResult(user=existing, profile_required=False)

        created = create_user(
            database_path,
            userid=normalized_userid,
            email="",
            username=normalized_userid,
            password="",
            depart="",
            role=ROLE_USER,
        )
        logger.info("Madang login created local user userid=%s", normalized_userid)
        return LoginResult(user=created, profile_required=True)

    user = authenticate_user(database_path, normalized_userid, password)
    if user is None:
        raise AuthProviderError(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    if user.role == ROLE_PENDING:
        raise AuthProviderError(
            403,
            "가입 승인 대기 중입니다. 관리자에게 문의해 주세요.",
        )
    return LoginResult(user=user, profile_required=False)
