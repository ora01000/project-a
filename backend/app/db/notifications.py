from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.users import list_users

NOTIFICATION_TYPE_REVIEW_REQUEST = "review_request"
NOTIFICATION_TYPE_EXECUTION_RESULT = "execution_result"
NOTIFICATION_TYPE_EXECUTION_FAILURE = "execution_failure"
NOTIFICATION_TYPE_REJECTION = "rejection"


@dataclass(frozen=True)
class JobNotification:
    idx: int
    job_idx: int
    target_user: str
    notification_type: str
    title: str
    message: str
    created_at: str


def _row_to_notification(row) -> JobNotification:
    return JobNotification(
        idx=int(row["idx"]),
        job_idx=int(row["job_idx"]),
        target_user=str(row["target_user"]),
        notification_type=str(row["notification_type"]),
        title=str(row["title"]),
        message=str(row["message"]),
        created_at=str(row["created_at"]),
    )


def create_job_notification(
    database_path: str | Path,
    *,
    job_idx: int,
    target_user: str,
    notification_type: str,
    title: str,
    message: str,
) -> JobNotification:
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO job_notifications (
                job_idx,
                target_user,
                notification_type,
                title,
                message,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_idx, target_user.strip(), notification_type, title, message, created_at),
        )
        connection.commit()
        idx = int(cursor.lastrowid)

    notification = get_notification_by_idx(database_path, idx)
    if notification is None:
        raise RuntimeError("Failed to load created notification")
    return notification


def get_notification_by_idx(database_path: str | Path, idx: int) -> JobNotification | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, job_idx, target_user, notification_type, title, message, created_at
            FROM job_notifications
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_notification(row)


def _notification_lookup_keys(database_path: str | Path, target_user: str) -> list[str]:
    """Match both userid-stored rows and legacy username-stored rows."""
    normalized = target_user.strip()
    keys = {normalized} if normalized else set()
    for user in list_users(database_path):
        if user.userid == normalized or user.username == normalized:
            keys.add(user.userid)
            keys.add(user.username)
    return sorted(keys)


def list_notifications_for_user(database_path: str | Path, target_user: str) -> list[JobNotification]:
    keys = _notification_lookup_keys(database_path, target_user)
    if not keys:
        return []

    placeholders = ", ".join("?" for _ in keys)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT idx, job_idx, target_user, notification_type, title, message, created_at
            FROM job_notifications
            WHERE target_user IN ({placeholders})
            ORDER BY idx DESC
            """,
            tuple(keys),
        ).fetchall()

    # Prefer userid-stored rows when legacy username duplicates remain.
    preferred_userids = {
        user.userid
        for user in list_users(database_path)
        if user.userid in keys or user.username in keys
    }
    deduped: dict[tuple[int, str], JobNotification] = {}
    for notification in (_row_to_notification(row) for row in rows):
        key = (notification.job_idx, notification.notification_type)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = notification
            continue
        if (
            notification.target_user in preferred_userids
            and existing.target_user not in preferred_userids
        ):
            deduped[key] = notification
        elif notification.idx > existing.idx and not (
            existing.target_user in preferred_userids
            and notification.target_user not in preferred_userids
        ):
            deduped[key] = notification

    return sorted(deduped.values(), key=lambda item: item.idx, reverse=True)


def delete_job_notification(database_path: str | Path, idx: int) -> bool:
    with get_connection(database_path) as connection:
        cursor = connection.execute("DELETE FROM job_notifications WHERE idx = ?", (idx,))
        connection.commit()
        return int(cursor.rowcount) > 0


def delete_job_notifications_by_job(
    database_path: str | Path,
    job_idx: int,
    *,
    notification_type: str | None = None,
) -> int:
    with get_connection(database_path) as connection:
        if notification_type is None:
            cursor = connection.execute(
                "DELETE FROM job_notifications WHERE job_idx = ?",
                (job_idx,),
            )
        else:
            cursor = connection.execute(
                "DELETE FROM job_notifications WHERE job_idx = ? AND notification_type = ?",
                (job_idx, notification_type),
            )
        connection.commit()
        return int(cursor.rowcount)
