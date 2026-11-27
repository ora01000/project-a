from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.bands import DEFAULT_BAND
from backend.app.db.prod_mode import (
    PROD_MODE_DEV,
    PROD_MODE_PROD,
    THEME_ID_DARK,
    normalize_prod_mode,
    normalize_theme_id,
)
from backend.app.db.roles import ROLE_ADMIN, ROLE_PENDING, is_admin_role, is_hidden_system_user
from backend.app.security.users_field_crypto import (
    blind_index,
    decrypt_field,
    is_ciphertext,
    is_users_field_crypto_enabled,
    pack_user_secrets,
)

LOGGER = logging.getLogger(__name__)

AGENTS_COLUMN_MAX_LENGTH = 200


@dataclass(frozen=True)
class User:
    idx: int
    userid: str
    email: str
    username: str
    depart: str
    role: int
    band: int = DEFAULT_BAND
    agents: str = ""
    last_login: str | None = None
    request_reason: str = ""
    whatap_event_sub: bool = False
    prod_auth: bool = False
    current_prod_mode: int = PROD_MODE_DEV
    theme_for_dev_mode: int = THEME_ID_DARK
    theme_for_prod_mode: int = THEME_ID_DARK


def ensure_whatap_event_sub_column(connection) -> None:
    connection.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS whatap_event_sub INTEGER NOT NULL DEFAULT 0
        """
    )


def ensure_users_prod_columns(connection) -> None:
    ensure_whatap_event_sub_column(connection)
    connection.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS prod_auth INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS current_prod_mode INTEGER NOT NULL DEFAULT 1
        """
    )
    connection.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS theme_for_dev_mode INTEGER NOT NULL DEFAULT 1
        """
    )
    connection.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS theme_for_prod_mode INTEGER NOT NULL DEFAULT 1
        """
    )
    ensure_users_field_crypto_schema(connection)


def ensure_users_field_crypto_schema(connection) -> None:
    """Widen secret columns and ensure blind-index columns/indexes exist."""
    connection.execute("ALTER TABLE users ALTER COLUMN userid TYPE TEXT")
    connection.execute("ALTER TABLE users ALTER COLUMN email TYPE TEXT")
    connection.execute("ALTER TABLE users ALTER COLUMN username TYPE TEXT")
    connection.execute("ALTER TABLE users ALTER COLUMN password TYPE TEXT")
    connection.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS userid_bidx VARCHAR(64) NOT NULL DEFAULT ''"
    )
    connection.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_bidx VARCHAR(64) NOT NULL DEFAULT ''"
    )
    connection.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_userid_key")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_userid_bidx
            ON users (userid_bidx)
            WHERE userid_bidx <> ''
        """
    )
    # email is not unique (seed root/isyun share an address); drop mistaken UNIQUE.
    connection.execute("DROP INDEX IF EXISTS ux_users_email_bidx")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_users_email_bidx
            ON users (email_bidx)
            WHERE email_bidx <> ''
        """
    )


def _plain_userid_from_row(row) -> str:
    raw = str(row["userid"] or "")
    if is_ciphertext(raw):
        try:
            return decrypt_field(raw, aad="userid").strip()
        except Exception:
            return raw.strip()
    return raw.strip()


def dedupe_users_by_plain_userid(connection) -> int:
    """Delete duplicate users sharing the same logical userid (keep lowest idx).

    Can appear after UNIQUE(userid) was dropped and plaintext system users were
    re-inserted beside already-encrypted rows.
    """
    ensure_users_field_crypto_schema(connection)
    rows = connection.execute("SELECT idx, userid FROM users ORDER BY idx").fetchall()
    keep: dict[str, int] = {}
    delete_idxs: list[int] = []
    for row in rows:
        plain = _plain_userid_from_row(row)
        if not plain:
            continue
        key = plain.lower()
        idx = int(row["idx"])
        if key not in keep:
            keep[key] = idx
        else:
            delete_idxs.append(idx)
    if not delete_idxs:
        return 0
    placeholders = ", ".join("?" for _ in delete_idxs)
    connection.execute(
        f"DELETE FROM users WHERE idx IN ({placeholders})",
        delete_idxs,
    )
    connection.commit()
    LOGGER.warning(
        "Removed duplicate users by plain userid count=%s idxs=%s",
        len(delete_idxs),
        delete_idxs,
    )
    return len(delete_idxs)


def migrate_users_field_encryption(connection) -> int:
    """Encrypt plaintext user secrets in place and backfill blind indexes.

    Safe to re-run. When crypto is disabled, only fills bidx from plaintext.
    """
    ensure_users_field_crypto_schema(connection)
    dedupe_users_by_plain_userid(connection)
    rows = connection.execute(
        "SELECT idx, userid, email, username, password, userid_bidx, email_bidx FROM users"
    ).fetchall()
    updated = 0
    crypto_on = is_users_field_crypto_enabled()
    for row in rows:
        idx = int(row["idx"])
        userid_raw = str(row["userid"] or "")
        email_raw = str(row["email"] or "")
        username_raw = str(row["username"] or "")
        password_raw = str(row["password"] or "")
        plain_userid = (
            decrypt_field(userid_raw, aad="userid")
            if is_ciphertext(userid_raw)
            else userid_raw.strip()
        )
        plain_email = (
            decrypt_field(email_raw, aad="email")
            if is_ciphertext(email_raw)
            else email_raw.strip()
        )
        plain_username = (
            decrypt_field(username_raw, aad="username")
            if is_ciphertext(username_raw)
            else username_raw.strip()
        )
        plain_password = (
            decrypt_field(password_raw, aad="password")
            if is_ciphertext(password_raw)
            else password_raw
        )
        packed = pack_user_secrets(
            userid=plain_userid,
            email=plain_email,
            username=plain_username,
            password=plain_password,
        )
        needs = (
            packed["userid"] != userid_raw
            or packed["email"] != email_raw
            or packed["username"] != username_raw
            or packed["password"] != password_raw
            or packed["userid_bidx"] != str(row["userid_bidx"] or "")
            or packed["email_bidx"] != str(row["email_bidx"] or "")
        )
        if not needs:
            continue
        if not crypto_on and is_ciphertext(userid_raw):
            # Keys removed while ciphertext remains — leave row untouched.
            continue
        connection.execute(
            """
            UPDATE users
            SET userid = ?, email = ?, username = ?, password = ?,
                userid_bidx = ?, email_bidx = ?
            WHERE idx = ?
            """,
            (
                packed["userid"],
                packed["email"],
                packed["username"],
                packed["password"],
                packed["userid_bidx"],
                packed["email_bidx"],
                idx,
            ),
        )
        updated += 1
    if updated:
        connection.commit()
        LOGGER.info("users field crypto migrate updated=%s crypto_enabled=%s", updated, crypto_on)
    return updated


def parse_agent_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for part in str(raw).split(","):
        agent_id = part.strip()
        if not agent_id or agent_id in seen:
            continue
        seen.add(agent_id)
        result.append(agent_id)
    return result


def encode_agent_ids(agent_ids: list[str]) -> str:
    normalized = parse_agent_ids(",".join(agent_ids))
    encoded = ",".join(normalized)
    if len(encoded) > AGENTS_COLUMN_MAX_LENGTH:
        raise ValueError(
            f"agents 값이 {AGENTS_COLUMN_MAX_LENGTH}자를 초과합니다 ({len(encoded)}자)."
        )
    return encoded


def _row_to_user(row) -> User:
    agents_value = ""
    try:
        agents_value = str(row["agents"] or "")
    except (KeyError, IndexError):
        agents_value = ""
    last_login: str | None = None
    try:
        raw_login = row["last_login"]
        if raw_login is not None and str(raw_login).strip():
            last_login = str(raw_login).strip()
    except (KeyError, IndexError):
        last_login = None
    band = DEFAULT_BAND
    try:
        if row["band"] is not None:
            band = int(row["band"])
    except (KeyError, IndexError, TypeError, ValueError):
        band = DEFAULT_BAND
    request_reason = ""
    try:
        request_reason = str(row["request_reason"] or "")
    except (KeyError, IndexError):
        request_reason = ""
    whatap_event_sub = False
    try:
        whatap_event_sub = bool(int(row["whatap_event_sub"] or 0))
    except (KeyError, IndexError, TypeError, ValueError):
        whatap_event_sub = False
    prod_auth = False
    try:
        prod_auth = bool(int(row["prod_auth"] or 0))
    except (KeyError, IndexError, TypeError, ValueError):
        prod_auth = False
    current_prod_mode = PROD_MODE_DEV
    try:
        current_prod_mode = normalize_prod_mode(row["current_prod_mode"])
    except (KeyError, IndexError, TypeError, ValueError):
        current_prod_mode = PROD_MODE_DEV
    if not prod_auth and current_prod_mode != PROD_MODE_DEV:
        current_prod_mode = PROD_MODE_DEV
    theme_for_dev_mode = THEME_ID_DARK
    try:
        theme_for_dev_mode = normalize_theme_id(row["theme_for_dev_mode"])
    except (KeyError, IndexError, TypeError, ValueError):
        theme_for_dev_mode = THEME_ID_DARK
    theme_for_prod_mode = THEME_ID_DARK
    try:
        theme_for_prod_mode = normalize_theme_id(row["theme_for_prod_mode"])
    except (KeyError, IndexError, TypeError, ValueError):
        theme_for_prod_mode = THEME_ID_DARK
    try:
        plain = {
            "userid": decrypt_field(str(row["userid"] or ""), aad="userid"),
            "email": decrypt_field(str(row["email"] or ""), aad="email"),
            "username": decrypt_field(str(row["username"] or ""), aad="username"),
        }
    except Exception:
        LOGGER.exception("Failed to decrypt users row idx=%s", row["idx"])
        plain = {
            "userid": str(row["userid"] or ""),
            "email": str(row["email"] or ""),
            "username": str(row["username"] or ""),
        }
    return User(
        idx=int(row["idx"]),
        userid=plain["userid"],
        email=plain["email"],
        username=plain["username"],
        depart=str(row["depart"]),
        role=int(row["role"]),
        band=band,
        agents=agents_value,
        last_login=last_login,
        request_reason=request_reason,
        whatap_event_sub=whatap_event_sub,
        prod_auth=prod_auth,
        current_prod_mode=current_prod_mode,
        theme_for_dev_mode=theme_for_dev_mode,
        theme_for_prod_mode=theme_for_prod_mode,
    )


_USER_SELECT = (
    "SELECT idx, userid, email, username, password, depart, role, band, agents, "
    "last_login, request_reason, whatap_event_sub, prod_auth, current_prod_mode, "
    "theme_for_dev_mode, theme_for_prod_mode, userid_bidx, email_bidx FROM users"
)


def _userid_lookup_clause(userid: str) -> tuple[str, tuple[object, ...]]:
    """Return SQL fragment + params for userid equality (bidx preferred)."""
    normalized = (userid or "").strip()
    bidx = blind_index(normalized, kind="userid")
    if bidx:
        return "(userid_bidx = ? OR (userid_bidx = '' AND userid = ?))", (bidx, normalized)
    return "userid = ?", (normalized,)


def list_users(database_path: str | Path, *, viewer_role: int | None = None) -> list[User]:
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        rows = connection.execute(
            f"""
            {_USER_SELECT}
            ORDER BY idx
            """
        ).fetchall()
    users = [_row_to_user(row) for row in rows]
    users = [user for user in users if not is_hidden_system_user(user.userid, user.role)]
    if viewer_role is not None and not is_admin_role(viewer_role):
        users = [user for user in users if user.role != ROLE_PENDING]
    return users


def list_admin_users(database_path: str | Path) -> list[User]:
    return [
        user
        for user in list_users(database_path, viewer_role=ROLE_ADMIN)
        if is_admin_role(user.role) and not is_hidden_system_user(user.userid, user.role)
    ]


def get_user_by_idx(database_path: str | Path, idx: int) -> User | None:
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        row = connection.execute(
            f"""
            {_USER_SELECT}
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def get_user_by_userid(database_path: str | Path, userid: str) -> User | None:
    clause, params = _userid_lookup_clause(userid)
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        row = connection.execute(
            f"""
            {_USER_SELECT}
            WHERE {clause}
            """,
            params,
        ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def get_user_idx_by_userid(database_path: str | Path, userid: str) -> int | None:
    """Resolve users.idx from users.userid (None when blank or unknown)."""
    normalized = (userid or "").strip()
    if not normalized:
        return None
    clause, params = _userid_lookup_clause(normalized)
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        row = connection.execute(
            f"SELECT idx FROM users WHERE {clause}",
            params,
        ).fetchone()
    if row is None:
        return None
    return int(row["idx"])


def get_user_idx_by_email(database_path: str | Path, email: str) -> int | None:
    """Resolve users.idx from a (case-insensitive) email address (hidden system users excluded)."""
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    email_bidx = blind_index(normalized, kind="email")
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        rows = connection.execute(
            f"""
            {_USER_SELECT}
            WHERE email_bidx = ?
               OR (email_bidx = '' AND LOWER(email) = ?)
            ORDER BY idx
            """,
            (email_bidx, normalized),
        ).fetchall()
    for row in rows:
        user = _row_to_user(row)
        if is_hidden_system_user(user.userid, user.role):
            continue
        return user.idx
    return None


def require_system_user_idx(database_path: str | Path, userid: str) -> int:
    """Return users.idx for a hidden system user, creating system users when missing."""
    idx = get_user_idx_by_userid(database_path, userid)
    if idx is not None:
        return idx
    from backend.app.db.seed import ensure_system_users

    ensure_system_users(database_path)
    idx = get_user_idx_by_userid(database_path, userid)
    if idx is None:
        raise RuntimeError(f"system user not found: {userid}")
    return idx


def build_userid_username_map(database_path: str | Path) -> dict[str, str]:
    """Map userid (and legacy username keys) to display username."""
    mapping: dict[str, str] = {}
    for user in list_users(database_path, viewer_role=ROLE_ADMIN):
        userid = user.userid.strip()
        username = user.username.strip()
        if userid:
            mapping[userid] = username or userid
        if username:
            mapping[username] = username
    return mapping


def build_idx_username_map(database_path: str | Path) -> dict[int, str]:
    """Map users.idx to display username (falls back to userid; hidden system users included)."""
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        rows = connection.execute(
            "SELECT idx, userid, username FROM users"
        ).fetchall()
    mapping: dict[int, str] = {}
    for row in rows:
        try:
            username = decrypt_field(str(row["username"] or ""), aad="username").strip()
            userid = decrypt_field(str(row["userid"] or ""), aad="userid").strip()
        except Exception:
            username = str(row["username"] or "").strip()
            userid = str(row["userid"] or "").strip()
        mapping[int(row["idx"])] = username or userid
    return mapping


def resolve_username_by_idx(idx: int, username_by_idx: dict[int, str]) -> str:
    """Display name for users.idx (empty string when unknown)."""
    return username_by_idx.get(int(idx), "")


def resolve_username(value: str, username_by_key: dict[str, str]) -> str:
    key = value.strip()
    if not key:
        return value
    return username_by_key.get(key, value)


def authenticate_user(database_path: str | Path, userid: str, password: str) -> User | None:
    """Local/seed login path. Production auth does not rely on stored password."""
    clause, params = _userid_lookup_clause(userid)
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        row = connection.execute(
            f"""
            {_USER_SELECT}
            WHERE {clause}
            """,
            params,
        ).fetchone()
    if row is None:
        return None
    raw_password = str(row["password"] or "")
    try:
        stored_password = decrypt_field(raw_password, aad="password")
    except Exception:
        LOGGER.exception("authenticate_user decrypt failed userid=%s", userid)
        return None
    if stored_password != password:
        return None
    return _row_to_user(row)


def create_user(
    database_path: str | Path,
    *,
    userid: str,
    email: str,
    username: str,
    password: str,
    depart: str,
    role: int,
    band: int = DEFAULT_BAND,
    agents: str = "",
    request_reason: str = "",
    prod_auth: bool = False,
) -> User:
    if is_hidden_system_user(userid):
        raise ValueError("userid is not allowed")
    encoded_agents = encode_agent_ids(parse_agent_ids(agents))
    packed = pack_user_secrets(
        userid=userid.strip(),
        email=email.strip(),
        username=username.strip(),
        password=password,
    )
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        cursor = connection.execute(
            """
            INSERT INTO users (
                userid, email, username, password, userid_bidx, email_bidx,
                depart, role, band, agents,
                request_reason, prod_auth, current_prod_mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packed["userid"],
                packed["email"],
                packed["username"],
                packed["password"],
                packed["userid_bidx"],
                packed["email_bidx"],
                depart.strip(),
                role,
                int(band),
                encoded_agents,
                request_reason.strip(),
                1 if prod_auth else 0,
                PROD_MODE_DEV,
            ),
        )
        connection.commit()
        idx = int(cursor.lastrowid)

    user = get_user_by_idx(database_path, idx)
    if user is None:
        raise RuntimeError("Failed to load created user")
    return user


def update_user(
    database_path: str | Path,
    idx: int,
    *,
    email: str,
    username: str,
    password: str | None,
    depart: str,
    role: int,
    band: int | None = None,
    request_reason: str | None = None,
    prod_auth: bool | None = None,
) -> User | None:
    existing = get_user_by_idx(database_path, idx)
    if existing is None:
        return None
    if is_hidden_system_user(existing.userid, existing.role):
        return None
    next_band = existing.band if band is None else int(band)
    next_request_reason = existing.request_reason if request_reason is None else request_reason.strip()
    next_prod_auth = existing.prod_auth if prod_auth is None else bool(prod_auth)
    next_mode = existing.current_prod_mode if next_prod_auth else PROD_MODE_DEV

    next_password = password if password else None
    # Keep existing password ciphertext when password is omitted.
    if next_password is None:
        with get_connection(database_path) as connection:
            ensure_users_prod_columns(connection)
            row = connection.execute(
                "SELECT password FROM users WHERE idx = ?",
                (idx,),
            ).fetchone()
        raw_pw = str(row["password"] or "") if row else ""
        try:
            next_password = decrypt_field(raw_pw, aad="password")
        except Exception:
            next_password = raw_pw
    packed = pack_user_secrets(
        userid=existing.userid,
        email=email.strip(),
        username=username.strip(),
        password=next_password or "",
    )
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        connection.execute(
            """
            UPDATE users
            SET email = ?, username = ?, password = ?, email_bidx = ?,
                depart = ?, role = ?, band = ?,
                request_reason = ?, prod_auth = ?, current_prod_mode = ?
            WHERE idx = ?
            """,
            (
                packed["email"],
                packed["username"],
                packed["password"],
                packed["email_bidx"],
                depart.strip(),
                role,
                next_band,
                next_request_reason,
                1 if next_prod_auth else 0,
                next_mode,
                idx,
            ),
        )
        connection.commit()

    return get_user_by_idx(database_path, idx)


def update_user_current_prod_mode(
    database_path: str | Path,
    idx: int,
    current_prod_mode: int,
) -> User | None:
    existing = get_user_by_idx(database_path, idx)
    if existing is None:
        return None
    if is_hidden_system_user(existing.userid, existing.role):
        return None
    mode = normalize_prod_mode(current_prod_mode)
    if mode == PROD_MODE_DEV:
        pass
    elif not existing.prod_auth:
        raise PermissionError("운영 플랫폼 관리 권한이 없습니다.")
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        connection.execute(
            """
            UPDATE users
            SET current_prod_mode = ?
            WHERE idx = ?
            """,
            (mode, idx),
        )
        connection.commit()
    return get_user_by_idx(database_path, idx)


def update_user_theme_for_mode(
    database_path: str | Path,
    idx: int,
    *,
    theme_id: int,
    prod_mode: int | None = None,
) -> User | None:
    """Persist theme for the given (or current) platform mode."""
    existing = get_user_by_idx(database_path, idx)
    if existing is None:
        return None
    if is_hidden_system_user(existing.userid, existing.role):
        return None
    mode = normalize_prod_mode(
        prod_mode if prod_mode is not None else existing.current_prod_mode
    )
    theme = normalize_theme_id(theme_id)
    column = "theme_for_prod_mode" if mode == PROD_MODE_PROD else "theme_for_dev_mode"
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        connection.execute(
            f"""
            UPDATE users
            SET {column} = ?
            WHERE idx = ?
            """,
            (theme, idx),
        )
        connection.commit()
    return get_user_by_idx(database_path, idx)


def update_user_agents(
    database_path: str | Path,
    idx: int,
    agent_ids: list[str],
) -> User | None:
    existing = get_user_by_idx(database_path, idx)
    if existing is not None and is_hidden_system_user(existing.userid, existing.role):
        return None
    encoded = encode_agent_ids(agent_ids)
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE users
            SET agents = ?
            WHERE idx = ?
            """,
            (encoded, idx),
        )
        connection.commit()
        if cursor.rowcount == 0:
            return None
    return get_user_by_idx(database_path, idx)


def record_user_login(database_path: str | Path, idx: int) -> tuple[str | None, User | None]:
    """Persist current login time and reset platform mode to DEV.

    Returns (previous_last_login, updated_user).
    """
    from backend.app.db.job_datetime import now_job_datetime

    existing = get_user_by_idx(database_path, idx)
    if existing is None:
        return None, None

    previous = existing.last_login
    login_at = now_job_datetime()
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        connection.execute(
            """
            UPDATE users
            SET last_login = ?, current_prod_mode = ?
            WHERE idx = ?
            """,
            (login_at, PROD_MODE_DEV, idx),
        )
        connection.commit()

    updated = get_user_by_idx(database_path, idx)
    return previous, updated


def delete_users(database_path: str | Path, idx_list: list[int]) -> int:
    if not idx_list:
        return 0

    safe_idx_list: list[int] = []
    for idx in idx_list:
        existing = get_user_by_idx(database_path, idx)
        if existing is not None and is_hidden_system_user(existing.userid, existing.role):
            continue
        safe_idx_list.append(idx)

    if not safe_idx_list:
        return 0

    placeholders = ", ".join("?" for _ in safe_idx_list)
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            f"DELETE FROM users WHERE idx IN ({placeholders})",
            safe_idx_list,
        )
        connection.commit()
        return int(cursor.rowcount)


def replace_whatap_event_subscribers(
    database_path: str | Path,
    userids: list[str],
) -> list[User]:
    """Set ``whatap_event_sub=1`` for ``userids`` and ``0`` for all other users."""
    selected: set[str] = set()
    for raw in userids:
        userid = str(raw or "").strip()
        if userid:
            selected.add(userid[:50])

    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        connection.execute("UPDATE users SET whatap_event_sub = 0")
        for userid in sorted(selected):
            clause, params = _userid_lookup_clause(userid)
            connection.execute(
                f"""
                UPDATE users
                SET whatap_event_sub = 1
                WHERE {clause}
                """,
                params,
            )
        connection.commit()

    return [user for user in list_users(database_path, viewer_role=ROLE_ADMIN) if user.whatap_event_sub]


def reencrypt_all_users_fields(database_path: str | Path) -> int:
    """Re-encrypt all users rows with the current KEK (rotation helper)."""
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        return migrate_users_field_encryption(connection)
