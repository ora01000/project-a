from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.job_datetime import (
    build_sr_num,
    normalize_job_datetime,
    next_sr_sequence,
    now_job_datetime,
)
from backend.app.db.users import User

JOB_STATUS_RECEIVED = 0
JOB_STATUS_APPROVER_ASSIGNED = 1
JOB_STATUS_DIRECT_APPROVED = 2
JOB_STATUS_COMPLETED_SUCCESS = 10
JOB_STATUS_COMPLETED_FAILURE = 11
JOB_STATUS_REJECTED = 12
JOB_STATUS_CANCELLED = 13

JOB_TYPE_AX_INFRA = 1
JOB_TYPE_SIGNUP = 10

SIGNUP_ACCESS_REQUEST_JOB_TITLE = "[신규사용자] 접속 권한 신청서"

JOB_SELECT_COLUMNS = """
    idx,
    srnum,
    status_code,
    job_type,
    approver_registered_date,
    approver,
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
    received_at,
    reject_reason,
    drop_reason
"""


@dataclass(frozen=True)
class JobRecord:
    idx: int
    srnum: str
    status_code: int
    job_type: int
    approver_registered_date: str | None
    approver: str | None
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
    reject_reason: str = ""
    drop_reason: str = ""


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
    job_type: int = JOB_TYPE_AX_INFRA


def _row_to_job(row) -> JobRecord:
    approver_registered_date = row["approver_registered_date"]
    approver = row["approver"]
    return JobRecord(
        idx=int(row["idx"]),
        srnum=str(row["srnum"]),
        status_code=int(row["status_code"]),
        job_type=int(row["job_type"] if row["job_type"] is not None else JOB_TYPE_AX_INFRA),
        approver_registered_date=(
            str(approver_registered_date) if approver_registered_date is not None else None
        ),
        approver=str(approver).strip() if approver is not None and str(approver).strip() else None,
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
        reject_reason=str(row["reject_reason"] or ""),
        drop_reason=str(row["drop_reason"] or ""),
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


def list_jobs(
    database_path: str | Path,
    *,
    status_code: int | None = None,
    min_status_code: int | None = None,
    approver: str | None = None,
    exclude_status_code: int | None = None,
    exclude_job_type: int | None = None,
) -> list[JobRecord]:
    clauses: list[str] = []
    params: list[object] = []
    if status_code is not None:
        clauses.append("status_code = ?")
        params.append(status_code)
    if min_status_code is not None:
        clauses.append("status_code >= ?")
        params.append(min_status_code)
    if exclude_status_code is not None:
        clauses.append("status_code != ?")
        params.append(exclude_status_code)
    if exclude_job_type is not None:
        clauses.append("job_type != ?")
        params.append(exclude_job_type)
    if approver is not None and approver.strip():
        clauses.append("approver = ?")
        params.append(approver.strip())

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT {JOB_SELECT_COLUMNS}
            FROM jobs
            {where_sql}
            ORDER BY idx DESC
            """,
            params,
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def create_job_from_intake(
    database_path: str | Path,
    payload: JobIntakePayload,
) -> JobRecord:
    normalized_request_date = normalize_job_datetime(payload.request_date)
    received_at = now_job_datetime()

    with get_connection(database_path) as connection:
        sequence = next_sr_sequence(connection, normalized_request_date)
        srnum = build_sr_num(normalized_request_date, sequence)
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                srnum,
                status_code,
                job_type,
                approver_registered_date,
                approver,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                srnum,
                JOB_STATUS_RECEIVED,
                int(payload.job_type),
                None,
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
        connection.commit()

    created = get_job_by_idx(database_path, idx)
    if created is None:
        raise RuntimeError("Failed to load created job record")
    return created


def create_user_access_request_job(database_path: str | Path, user: User) -> JobRecord:
    """Create a signup access-request job for a pending user."""
    requester_name = f"{user.username.strip()} {user.depart.strip()}".strip()
    submitted_at = now_job_datetime()
    payload = JobIntakePayload(
        job_title=SIGNUP_ACCESS_REQUEST_JOB_TITLE,
        requester_name=requester_name,
        requester_email=user.email.strip(),
        requester_depart=user.depart.strip(),
        job_content=user.request_reason.strip(),
        request_date=submitted_at,
        madang_id=user.userid.strip(),
        team_id="",
        channel_id="",
        message_id="",
        job_type=JOB_TYPE_SIGNUP,
    )
    return create_job_from_intake(database_path, payload)


def approval_target_status_code(job: JobRecord) -> int:
    """Signup access requests complete without agent delegation."""
    if job.job_type == JOB_TYPE_SIGNUP:
        return JOB_STATUS_COMPLETED_SUCCESS
    return JOB_STATUS_DIRECT_APPROVED


def _resolve_user_display_name(
    database_path: str | Path,
    userid: str,
    *,
    fallback: str = "",
) -> str:
    from backend.app.db.users import get_user_by_userid

    normalized_userid = userid.strip()
    if normalized_userid:
        user = get_user_by_userid(database_path, normalized_userid)
        if user is not None and user.username.strip():
            return user.username.strip()
    normalized_fallback = fallback.strip()
    if normalized_fallback:
        return normalized_fallback
    return normalized_userid


def _record_signup_job_approval_result(database_path: str | Path, job: JobRecord) -> None:
    from backend.app.db.jobs_result import upsert_job_result

    approver_userid = (job.approver or "").strip()
    if not approver_userid:
        raise ValueError("signup job approval result requires approver")

    approver_name = _resolve_user_display_name(database_path, approver_userid, fallback=approver_userid)
    requester_userid = (job.madang_id or "").strip()
    requester_name = _resolve_user_display_name(
        database_path,
        requester_userid,
        fallback=job.requester_name,
    )
    result_text = f"{approver_name} 이 {requester_name} 의 접속 권한을 승인완료 하였습니다"
    upsert_job_result(
        database_path,
        srnum=job.srnum,
        result=result_text,
        complete_date=now_job_datetime(),
    )


def _finalize_signup_job_approval(database_path: str | Path, job: JobRecord) -> None:
    if job.job_type != JOB_TYPE_SIGNUP:
        return
    from backend.app.services.user_signup import approve_pending_user_for_signup_job

    approve_pending_user_for_signup_job(database_path, job)
    _record_signup_job_approval_result(database_path, job)


def assign_job_approver(
    database_path: str | Path,
    idx: int,
    *,
    approver_userid: str,
    status_code: int = JOB_STATUS_APPROVER_ASSIGNED,
) -> JobRecord:
    from backend.app.db.roles import is_hidden_system_user
    from backend.app.db.users import get_user_by_userid

    userid = approver_userid.strip()
    if not userid:
        raise ValueError("approver is required")

    approver = get_user_by_userid(database_path, userid)
    if approver is None or is_hidden_system_user(approver.userid, approver.role):
        raise ValueError(f"unknown approver userid: {userid}")

    existing = get_job_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("job not found")
    if existing.approver:
        raise ValueError("approver is already assigned")

    registered_at = now_job_datetime()
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET approver = ?,
                approver_registered_date = ?,
                status_code = ?
            WHERE idx = ? AND (approver IS NULL OR TRIM(approver) = '')
            """,
            (userid, registered_at, status_code, idx),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("approver is already assigned")

    updated = get_job_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated job record")
    return updated


def direct_approve_job(
    database_path: str | Path,
    idx: int,
    *,
    approver_userid: str,
) -> JobRecord:
    existing = get_job_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("job not found")
    updated = assign_job_approver(
        database_path,
        idx,
        approver_userid=approver_userid,
        status_code=approval_target_status_code(existing),
    )
    _finalize_signup_job_approval(database_path, updated)
    return updated


def _require_assigned_reviewer(job: JobRecord, actor_userid: str) -> None:
    actor = actor_userid.strip()
    if not actor:
        raise ValueError("actor_userid is required")
    if job.status_code != JOB_STATUS_APPROVER_ASSIGNED:
        raise ValueError("job is not awaiting review")
    if (job.approver or "").strip() != actor:
        raise ValueError("only assigned approver can perform this action")


def approve_assigned_job(
    database_path: str | Path,
    idx: int,
    *,
    actor_userid: str,
) -> JobRecord:
    existing = get_job_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("job not found")
    _require_assigned_reviewer(existing, actor_userid)
    target_status = approval_target_status_code(existing)

    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status_code = ?
            WHERE idx = ? AND status_code = ? AND approver = ?
            """,
            (target_status, idx, JOB_STATUS_APPROVER_ASSIGNED, actor_userid.strip()),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("job review state has changed")

    updated = get_job_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated job record")
    _finalize_signup_job_approval(database_path, updated)
    return updated


def reject_assigned_job(
    database_path: str | Path,
    idx: int,
    *,
    actor_userid: str,
    drop_reason: str = "",
) -> JobRecord:
    existing = get_job_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("job not found")
    _require_assigned_reviewer(existing, actor_userid)

    normalized_reason = drop_reason.strip()[:200]
    if not normalized_reason:
        raise ValueError("drop_reason is required")

    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status_code = ?,
                drop_reason = ?
            WHERE idx = ? AND status_code = ? AND approver = ?
            """,
            (
                JOB_STATUS_REJECTED,
                normalized_reason,
                idx,
                JOB_STATUS_APPROVER_ASSIGNED,
                actor_userid.strip(),
            ),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("job review state has changed")

    updated = get_job_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated job record")
    return updated


def reject_received_job(
    database_path: str | Path,
    idx: int,
    *,
    actor_userid: str,
    drop_reason: str = "",
) -> JobRecord:
    existing = get_job_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("job not found")

    actor = actor_userid.strip()
    if not actor:
        raise ValueError("actor_userid is required")
    if existing.status_code != JOB_STATUS_RECEIVED:
        raise ValueError("only received jobs can be rejected from intake review")
    if existing.approver and existing.approver.strip():
        raise ValueError("approver is already assigned")

    normalized_reason = drop_reason.strip()[:200]
    if not normalized_reason:
        raise ValueError("drop_reason is required")

    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status_code = ?,
                drop_reason = ?
            WHERE idx = ? AND status_code = ?
              AND (approver IS NULL OR TRIM(approver) = '')
            """,
            (
                JOB_STATUS_REJECTED,
                normalized_reason,
                idx,
                JOB_STATUS_RECEIVED,
            ),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("job reject state has changed")

    updated = get_job_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated job record")
    return updated


def update_job_status(
    database_path: str | Path,
    idx: int,
    status_code: int,
    *,
    expected_status: int | None = None,
) -> JobRecord:
    with get_connection(database_path) as connection:
        if expected_status is None:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status_code = ?
                WHERE idx = ?
                """,
                (status_code, idx),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status_code = ?
                WHERE idx = ? AND status_code = ?
                """,
                (status_code, idx, expected_status),
            )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("job status update failed")

    updated = get_job_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated job record")
    return updated


def rework_job(
    database_path: str | Path,
    idx: int,
    *,
    actor_userid: str,
) -> JobRecord:
    existing = get_job_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("job not found")

    actor = actor_userid.strip()
    if not actor:
        raise ValueError("actor_userid is required")
    if (existing.approver or "").strip() != actor:
        raise ValueError("only assigned approver can rework this job")
    if existing.status_code < JOB_STATUS_COMPLETED_SUCCESS:
        raise ValueError("job is not in a completed state")
    if existing.status_code == JOB_STATUS_CANCELLED:
        raise ValueError("cancelled jobs cannot be reworked")

    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status_code = ?
            WHERE idx = ? AND approver = ? AND status_code >= ? AND status_code != ?
            """,
            (JOB_STATUS_DIRECT_APPROVED, idx, actor, JOB_STATUS_COMPLETED_SUCCESS, JOB_STATUS_CANCELLED),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("job rework state has changed")

    updated = get_job_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated job record")
    return updated


def cancel_failed_job(
    database_path: str | Path,
    idx: int,
    *,
    actor_userid: str,
    drop_reason: str = "",
) -> JobRecord:
    existing = get_job_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("job not found")

    actor = actor_userid.strip()
    if not actor:
        raise ValueError("actor_userid is required")
    if (existing.approver or "").strip() != actor:
        raise ValueError("only assigned approver can cancel this job")
    if existing.status_code != JOB_STATUS_COMPLETED_FAILURE:
        raise ValueError("only failed jobs can be cancelled")

    normalized_reason = drop_reason.strip()[:200]
    if not normalized_reason:
        raise ValueError("drop_reason is required")

    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status_code = ?,
                drop_reason = ?
            WHERE idx = ? AND status_code = ? AND approver = ?
            """,
            (
                JOB_STATUS_CANCELLED,
                normalized_reason,
                idx,
                JOB_STATUS_COMPLETED_FAILURE,
                actor,
            ),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("job cancel state has changed")

    updated = get_job_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated job record")
    return updated
