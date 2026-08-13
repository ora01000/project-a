import logging
from pathlib import Path

from backend.app.db.roles import ROLE_PENDING, ROLE_USER
from backend.app.db.jobs import JobRecord, create_user_access_request_job
from backend.app.db.users import User, create_user, delete_users, get_user_by_idx, get_user_by_userid, update_user
from backend.app.notifications.email_sender import (
    send_signup_approval_email,
    send_signup_rejection_email,
)

logger = logging.getLogger(__name__)


def register_pending_user(
    database_path: Path,
    *,
    userid: str,
    email: str,
    username: str,
    password: str,
    depart: str,
    band: int = 1,
    request_reason: str = "",
) -> tuple[User, JobRecord]:
    user = create_user(
        database_path,
        userid=userid,
        email=email,
        username=username,
        password=password,
        depart=depart,
        role=ROLE_PENDING,
        band=band,
        request_reason=request_reason,
    )
    job = create_user_access_request_job(database_path, user)
    logger.info("Pending signup registered for userid=%s job=%s", user.userid, job.srnum)
    return user, job


def approve_signup(database_path: Path, user_idx: int) -> User | None:
    user = get_user_by_idx(database_path, user_idx)
    if user is None:
        return None
    if user.role != ROLE_PENDING:
        raise ValueError("승인 대기 상태의 사용자만 승인할 수 있습니다.")

    updated = update_user(
        database_path,
        user_idx,
        email=user.email,
        username=user.username,
        password=None,
        depart=user.depart,
        role=ROLE_USER,
        band=user.band,
    )
    logger.info("Signup approved for userid=%s", user.userid)
    return updated


async def notify_signup_approved(database_path: Path, user: User) -> None:
    """Best-effort approval notice to the requester; does not raise on mail failure."""
    try:
        await send_signup_approval_email(
            database_path=database_path,
            to_address=user.email,
            username=user.username,
            userid=user.userid,
        )
    except Exception:
        logger.exception("Signup approval email notify failed for userid=%s", user.userid)


def approve_pending_user_for_signup_job(database_path: Path, job: JobRecord) -> User | None:
    """Activate pending user when a signup access-request job (job_type=10) is approved."""
    from backend.app.db.jobs import JOB_TYPE_SIGNUP

    if job.job_type != JOB_TYPE_SIGNUP:
        return None

    userid = str(job.madang_id or "").strip()
    if not userid:
        raise ValueError("signup job is missing userid (madang_id)")

    user = get_user_by_userid(database_path, userid)
    if user is None:
        raise ValueError(f"signup user not found for userid={userid!r}")

    return approve_signup(database_path, user.idx)


async def reject_signup(database_path: Path, user_idx: int, reason: str) -> bool:
    user = get_user_by_idx(database_path, user_idx)
    if user is None:
        return False
    if user.role != ROLE_PENDING:
        raise ValueError("승인 대기 상태의 사용자만 반려할 수 있습니다.")

    await send_signup_rejection_email(
        database_path=database_path,
        to_address=user.email,
        username=user.username,
        userid=user.userid,
        reason=reason.strip(),
    )
    delete_users(database_path, [user_idx])
    logger.info("Signup rejected for userid=%s", user.userid)
    return True
