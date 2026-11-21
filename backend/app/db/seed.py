from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from backend.app.db.roles import (
    AUTO_APPROVE_USERID,
    EXTERNAL_USERID,
    ROLE_PENDING,
    WHATAP_USERID,
)


class SeedUser(TypedDict):
    userid: str
    email: str
    username: str
    password: str
    depart: str
    role: int
    band: int


INITIAL_USERS: list[SeedUser] = [
    {
        "userid": "root",
        "email": "isyun@lguplus.co.kr",
        "username": "관리자",
        "password": "root-internal-bypass-only",
        "depart": "IT플랫폼운영팀",
        "role": 100,
        "band": 3,
    },
    {
        "userid": "isyun",
        "email": "isyun@lguplus.co.kr",
        "username": "윤인수",
        "password": "isyun",
        "depart": "IT플랫폼운영팀",
        "role": 0,
        "band": 3,
    },
    {
        "userid": "loadan",
        "email": "loadan@lguplus.co.kr",
        "username": "안세훈",
        "password": "loadan",
        "depart": "IT플랫폼운영팀",
        "role": 0,
        "band": 3,
    },
]

# Hidden system users referenced by jobs.requester_idx / jobs.approver_idx.
# ROLE_PENDING blocks interactive login; hidden-ness is enforced via is_hidden_system_user().
SYSTEM_USERS: list[SeedUser] = [
    {
        "userid": AUTO_APPROVE_USERID,
        "email": "auto_approve@admin.io",
        "username": "auto_approve",
        "password": "system-no-login-auto-approve",
        "depart": "System",
        "role": ROLE_PENDING,
        "band": 1,
    },
    {
        "userid": WHATAP_USERID,
        "email": "whatap@admin.io",
        "username": "Whatap",
        "password": "system-no-login-whatap",
        "depart": "Whatap",
        "role": ROLE_PENDING,
        "band": 1,
    },
    {
        "userid": EXTERNAL_USERID,
        "email": "external@admin.io",
        "username": "External",
        "password": "system-no-login-external",
        "depart": "External",
        "role": ROLE_PENDING,
        "band": 1,
    },
]


def ensure_system_users_on_connection(connection) -> int:
    """Insert missing hidden system users (idempotent). Returns inserted row count."""
    from backend.app.db.users import ensure_users_field_crypto_schema
    from backend.app.security.users_field_crypto import blind_index, pack_user_secrets

    ensure_users_field_crypto_schema(connection)
    inserted = 0
    for user in SYSTEM_USERS:
        bidx = blind_index(user["userid"], kind="userid")
        existing = connection.execute(
            """
            SELECT 1 AS present FROM users
            WHERE userid_bidx = ? OR (userid_bidx = '' AND userid = ?)
            """,
            (bidx, user["userid"]),
        ).fetchone()
        if existing is not None:
            continue
        packed = pack_user_secrets(
            userid=user["userid"],
            email=user["email"],
            username=user["username"],
            password=user["password"],
        )
        cursor = connection.execute(
            """
            INSERT INTO users (
                userid, email, username, password, userid_bidx, email_bidx,
                depart, role, band
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packed["userid"],
                packed["email"],
                packed["username"],
                packed["password"],
                packed["userid_bidx"],
                packed["email_bidx"],
                user["depart"],
                user["role"],
                user["band"],
            ),
        )
        if int(getattr(cursor, "rowcount", 0) or 0) > 0:
            inserted += 1
    connection.commit()
    return inserted


def ensure_system_users(database_path: str | Path | None = None) -> int:
    """Ensure auto_approve / whatap / external users exist."""
    from backend.app.db.database import get_connection

    with get_connection(database_path) as connection:
        return ensure_system_users_on_connection(connection)
