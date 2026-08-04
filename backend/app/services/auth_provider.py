"""Authentication providers: local DB and madang OAuth."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from backend.app.config import AuthProviderSettings, load_auth_provider_settings
from backend.app.db.roles import ROLE_PENDING
from backend.app.db.users import User, authenticate_user, get_user_by_userid

logger = logging.getLogger(__name__)

MADANG_EMAIL_DOMAINS = frozenset({"@lguplus.co.kr", "@lgupluspartners.co.kr"})


class AuthProviderError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class LoginResult:
    user: User | None = None
    profile_required: bool = False
    registration_required: bool = False
    userid: str = ""


def sha512_hex(value: str) -> str:
    return hashlib.sha512(value.encode()).hexdigest()


def _madang_http_client(*, verify_ssl: bool) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0, verify=verify_ssl)


async def verify_madang_via_direct_oauth(
    *,
    settings: AuthProviderSettings,
    userid: str,
    password: str,
) -> bool:
    """Port of server-samples/oauth/login.jsp — password grant to madang token API."""
    if not settings.oauth_url or not settings.oauth_client_id or not settings.oauth_client_secret:
        raise AuthProviderError(
            500,
            "madang OAuth 설정(OAUTH_URL, OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET)이 필요합니다.",
        )

    hashed_password = sha512_hex(password)
    form_data = {
        "grant_type": settings.oauth_grant_type,
        "client_id": settings.oauth_client_id,
        "client_secret": settings.oauth_client_secret,
        "scope": settings.oauth_scope,
        "auth_type": settings.oauth_auth_type,
        "user_id": userid,
        "password": hashed_password,
    }

    try:
        async with _madang_http_client(verify_ssl=settings.oauth_verify_ssl) as client:
            response = await client.post(
                settings.oauth_url,
                data=form_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("Madang OAuth token request failed: %s", exc)
        raise AuthProviderError(502, "인증 서버에 연결할 수 없습니다.") from exc

    if response.status_code == 200:
        return True

    logger.info(
        "Madang OAuth rejected login userid=%s status=%s",
        userid,
        response.status_code,
    )
    return False


async def verify_madang_via_proxy(
    *,
    oauth_proxy: str,
    userid: str,
    password: str,
    verify_ssl: bool,
) -> bool:
    """Call deployed oauth proxy (Basic Auth), compatible with login.jsp."""
    base = oauth_proxy.strip().rstrip("/")
    if not base:
        raise AuthProviderError(500, "OAUTH_PROXY 가 설정되지 않았습니다.")

    candidates = (f"{base}/login", f"{base}/login.jsp")
    last_status: int | None = None

    try:
        async with _madang_http_client(verify_ssl=verify_ssl) as client:
            for url in candidates:
                response = await client.post(url, auth=(userid, password))
                last_status = response.status_code
                if response.is_success:
                    return True
    except httpx.HTTPError as exc:
        logger.warning("Madang OAuth proxy request failed: %s", exc)
        raise AuthProviderError(502, "인증 서버에 연결할 수 없습니다.") from exc

    logger.info(
        "Madang OAuth proxy rejected login userid=%s status=%s",
        userid,
        last_status,
    )
    return False


async def verify_madang_credentials(
    *,
    settings: AuthProviderSettings,
    userid: str,
    password: str,
) -> bool:
    if settings.oauth_url and settings.oauth_client_id and settings.oauth_client_secret:
        return await verify_madang_via_direct_oauth(
            settings=settings,
            userid=userid,
            password=password,
        )
    if settings.oauth_proxy:
        return await verify_madang_via_proxy(
            oauth_proxy=settings.oauth_proxy,
            userid=userid,
            password=password,
            verify_ssl=settings.oauth_verify_ssl,
        )
    raise AuthProviderError(
        500,
        "madang 인증 설정이 없습니다. OAUTH_URL 또는 OAUTH_PROXY 를 설정해 주세요.",
    )


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
            settings=auth_settings,
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

        return LoginResult(registration_required=True, userid=normalized_userid)

    user = authenticate_user(database_path, normalized_userid, password)
    if user is None:
        raise AuthProviderError(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    if user.role == ROLE_PENDING:
        raise AuthProviderError(
            403,
            "가입 승인 대기 중입니다. 관리자에게 문의해 주세요.",
        )
    return LoginResult(user=user, profile_required=False)
