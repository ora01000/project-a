from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.roles import ROLE_ADMIN, ROLE_PENDING


@dataclass(frozen=True)
class User:
    idx: int
    userid: str
    email: str
    username: str
    depart: str
    role: int


def _row_to_user(row) -> User:
    return User(
        idx=int(row["idx"]),
        userid=str(row["userid"]),
        email=str(row["email"]),
        username=str(row["username"]),
        depart=str(row["depart"]),
        role=int(row["role"]),
    )


def list_users(database_path: str | Path, *, viewer_role: int | None = None) -> list[User]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT idx, userid, email, username, depart, role
            FROM users
            ORDER BY idx
            """
        ).fetchall()
    users = [_row_to_user(row) for row in rows]
    if viewer_role != ROLE_ADMIN:
        users = [user for user in users if user.role != ROLE_PENDING]
    return users


def list_admin_users(database_path: str | Path) -> list[User]:
    return [user for user in list_users(database_path, viewer_role=ROLE_ADMIN) if user.role == ROLE_ADMIN]


def get_user_by_idx(database_path: str | Path, idx: int) -> User | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, userid, email, username, depart, role
            FROM users
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def get_user_by_userid(database_path: str | Path, userid: str) -> User | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, userid, email, username, depart, role
            FROM users
            WHERE userid = ?
            """,
            (userid.strip(),),
        ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def authenticate_user(database_path: str | Path, userid: str, password: str) -> User | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, userid, email, username, depart, role
            FROM users
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
) -> User:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (userid, email, username, password, depart, role)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (userid.strip(), email.strip(), username.strip(), password, depart.strip(), role),
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
) -> User | None:
    with get_connection(database_path) as connection:
        if password:
            connection.execute(
                """
                UPDATE users
                SET email = ?, username = ?, password = ?, depart = ?, role = ?
                WHERE idx = ?
                """,
                (email.strip(), username.strip(), password, depart.strip(), role, idx),
            )
        else:
            connection.execute(
                """
                UPDATE users
                SET email = ?, username = ?, depart = ?, role = ?
                WHERE idx = ?
                """,
                (email.strip(), username.strip(), depart.strip(), role, idx),
            )
        connection.commit()

    return get_user_by_idx(database_path, idx)


def delete_users(database_path: str | Path, idx_list: list[int]) -> int:
    if not idx_list:
        return 0

    placeholders = ", ".join("?" for _ in idx_list)
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            f"DELETE FROM users WHERE idx IN ({placeholders})",
            idx_list,
        )
        connection.commit()
        return int(cursor.rowcount)
