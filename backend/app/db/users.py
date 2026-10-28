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
    return User(
        idx=int(row["idx"]),
        userid=str(row["userid"]),
        email=str(row["email"]),
        username=str(row["username"]),
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
    "SELECT idx, userid, email, username, depart, role, band, agents, "
    "last_login, request_reason, whatap_event_sub, prod_auth, current_prod_mode, "
    "theme_for_dev_mode, theme_for_prod_mode FROM users"
)


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
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        row = connection.execute(
            f"""
            {_USER_SELECT}
            WHERE userid = ?
            """,
            (userid.strip(),),
        ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


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


def resolve_username(value: str, username_by_key: dict[str, str]) -> str:
    key = value.strip()
    if not key:
        return value
    return username_by_key.get(key, value)


def authenticate_user(database_path: str | Path, userid: str, password: str) -> User | None:
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        row = connection.execute(
            f"""
            {_USER_SELECT}
            WHERE userid = ? AND password = ?
            """,
            (userid.strip(), password),
        ).fetchone()

    if row is None:
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
    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        cursor = connection.execute(
            """
            INSERT INTO users (
                userid, email, username, password, depart, role, band, agents,
                request_reason, prod_auth, current_prod_mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                userid.strip(),
                email.strip(),
                username.strip(),
                password,
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

    with get_connection(database_path) as connection:
        ensure_users_prod_columns(connection)
        if password:
            connection.execute(
                """
                UPDATE users
                SET email = ?, username = ?, password = ?, depart = ?, role = ?, band = ?,
                    request_reason = ?, prod_auth = ?, current_prod_mode = ?
                WHERE idx = ?
                """,
                (
                    email.strip(),
                    username.strip(),
                    password,
                    depart.strip(),
                    role,
                    next_band,
                    next_request_reason,
                    1 if next_prod_auth else 0,
                    next_mode,
                    idx,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE users
                SET email = ?, username = ?, depart = ?, role = ?, band = ?,
                    request_reason = ?, prod_auth = ?, current_prod_mode = ?
                WHERE idx = ?
                """,
                (
                    email.strip(),
                    username.strip(),
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
        ensure_whatap_event_sub_column(connection)
        connection.execute("UPDATE users SET whatap_event_sub = 0")
        for userid in sorted(selected):
            connection.execute(
                """
                UPDATE users
                SET whatap_event_sub = 1
                WHERE userid = ?
                """,
                (userid,),
            )
        connection.commit()

    return [user for user in list_users(database_path, viewer_role=ROLE_ADMIN) if user.whatap_event_sub]
