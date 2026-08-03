from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.job_datetime import build_sr_num, normalize_job_datetime, now_job_datetime

JOB_STATUS_RECEIVED = 0
JOB_STATUS_APPROVER_ASSIGNED = 1
JOB_STATUS_COMPLETED_SUCCESS = 10
JOB_STATUS_COMPLETED_FAILURE = 11
JOB_STATUS_REJECTED = 12

JOB_SELECT_COLUMNS = """
    idx,
    srnum,
    status_code,
    approver_registered_date,
    job_title,
    requester_name,
    requester_email,
    requester_depart,
    job_content,
    request_date,
    madang_id,
    team_id,
    channel_id,
    message_id,
    received_at
"""


@dataclass(frozen=True)
class JobRecord:
    idx: int
    srnum: str
    status_code: int
    approver_registered_date: str | None
    job_title: str
    requester_name: str
    requester_email: str
    requester_depart: str
    job_content: str
    request_date: str
    madang_id: str
    team_id: str
    channel_id: str
    message_id: str
    received_at: str


@dataclass(frozen=True)
class JobIntakePayload:
    job_title: str
    requester_name: str
    requester_email: str
    requester_depart: str
    job_content: str
    request_date: str
    madang_id: str
    team_id: str
    channel_id: str
    message_id: str


def _row_to_job(row) -> JobRecord:
    approver_registered_date = row["approver_registered_date"]
    return JobRecord(
        idx=int(row["idx"]),
        srnum=str(row["srnum"]),
        status_code=int(row["status_code"]),
        approver_registered_date=(
            str(approver_registered_date) if approver_registered_date is not None else None
        ),
        job_title=str(row["job_title"]),
        requester_name=str(row["requester_name"]),
        requester_email=str(row["requester_email"]),
        requester_depart=str(row["requester_depart"]),
        job_content=str(row["job_content"] or ""),
        request_date=str(row["request_date"]),
        madang_id=str(row["madang_id"]),
        team_id=str(row["team_id"]),
        channel_id=str(row["channel_id"]),
        message_id=str(row["message_id"]),
        received_at=str(row["received_at"]),
    )


def get_job_by_idx(database_path: str | Path, idx: int) -> JobRecord | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            f"""
            SELECT {JOB_SELECT_COLUMNS}
            FROM jobs
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_job(row)


def create_job_from_intake(
    database_path: str | Path,
    payload: JobIntakePayload,
) -> JobRecord:
    normalized_request_date = normalize_job_datetime(payload.request_date)
    received_at = now_job_datetime()

    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                srnum,
                status_code,
                approver_registered_date,
                job_title,
                requester_name,
                requester_email,
                requester_depart,
                job_content,
                request_date,
                madang_id,
                team_id,
                channel_id,
                message_id,
                received_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "",
                JOB_STATUS_RECEIVED,
                None,
                payload.job_title.strip(),
                payload.requester_name.strip(),
                payload.requester_email.strip(),
                payload.requester_depart.strip(),
                payload.job_content,
                normalized_request_date,
                payload.madang_id.strip(),
                payload.team_id.strip(),
                payload.channel_id.strip(),
                payload.message_id.strip(),
                received_at,
            ),
        )
        idx = int(cursor.lastrowid)
        srnum = build_sr_num(payload.request_date, idx)
        connection.execute(
            "UPDATE jobs SET srnum = ? WHERE idx = ?",
            (srnum, idx),
        )
        connection.commit()

    created = get_job_by_idx(database_path, idx)
    if created is None:
        raise RuntimeError("Failed to load created job record")
    return created
