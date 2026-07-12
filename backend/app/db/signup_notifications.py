from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.app.db.database import get_connection

SIGNUP_NOTIFICATION_TYPE = "signup_request"


@dataclass(frozen=True)
class SignupNotification:
    idx: int
    user_idx: int
    target_user: str
    title: str
    message: str
    created_at: str


def _row_to_notification(row) -> SignupNotification:
    return SignupNotification(
        idx=int(row["idx"]),
        user_idx=int(row["user_idx"]),
        target_user=str(row["target_user"]),
        title=str(row["title"]),
        message=str(row["message"]),
        created_at=str(row["created_at"]),
    )


def create_signup_notification(
    database_path: str | Path,
    *,
    user_idx: int,
    target_user: str,
    title: str,
    message: str,
) -> SignupNotification:
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO signup_notifications (user_idx, target_user, title, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_idx, target_user.strip(), title, message, created_at),
        )
        connection.commit()
        idx = int(cursor.lastrowid)

    notification = get_signup_notification_by_idx(database_path, idx)
    if notification is None:
        raise RuntimeError("Failed to load created signup notification")
    return notification


def get_signup_notification_by_idx(database_path: str | Path, idx: int) -> SignupNotification | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, user_idx, target_user, title, message, created_at
            FROM signup_notifications
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_notification(row)


def list_signup_notifications_for_user(database_path: str | Path, target_user: str) -> list[SignupNotification]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT idx, user_idx, target_user, title, message, created_at
            FROM signup_notifications
            WHERE target_user = ?
            ORDER BY idx DESC
            """,
            (target_user.strip(),),
        ).fetchall()
    return [_row_to_notification(row) for row in rows]


def delete_signup_notification(database_path: str | Path, idx: int) -> bool:
    with get_connection(database_path) as connection:
        cursor = connection.execute("DELETE FROM signup_notifications WHERE idx = ?", (idx,))
        connection.commit()
        return int(cursor.rowcount) > 0


def delete_signup_notifications_for_user(database_path: str | Path, user_idx: int) -> int:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM signup_notifications WHERE user_idx = ?",
            (user_idx,),
        )
        connection.commit()
        return int(cursor.rowcount)
