from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.app.db.database import get_connection

NOTIFICATION_TYPE_REVIEW_REQUEST = "review_request"
NOTIFICATION_TYPE_EXECUTION_RESULT = "execution_result"
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


def list_notifications_for_user(database_path: str | Path, target_user: str) -> list[JobNotification]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT idx, job_idx, target_user, notification_type, title, message, created_at
            FROM job_notifications
            WHERE target_user = ?
            ORDER BY idx DESC
            """,
            (target_user.strip(),),
        ).fetchall()
    return [_row_to_notification(row) for row in rows]
