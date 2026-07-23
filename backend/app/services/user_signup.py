import logging
from pathlib import Path

from backend.app.db.roles import ROLE_ADMIN, ROLE_PENDING, ROLE_USER
from backend.app.timezone import format_display_datetime
from backend.app.db.signup_notifications import (
    create_signup_notification,
    delete_signup_notification,
    delete_signup_notifications_for_user,
)
from backend.app.db.users import User, create_user, delete_users, get_user_by_idx, list_users, update_user
from backend.app.notifications.email_sender import send_signup_rejection_email

logger = logging.getLogger(__name__)

SIGNUP_NOTIFICATION_TITLE = "신규 가입 신청"


def _build_signup_message(*, signup_date: str, depart: str, username: str, userid: str) -> str:
    return (
        f"가입 날짜: {signup_date}\n"
        f"조직명: {depart}\n"
        f"가입자 이름: {username}\n"
        f"가입자 ID: {userid}"
    )


def _notify_admins(database_path: Path, *, user: User, signup_date: str) -> None:
    message = _build_signup_message(
        signup_date=signup_date,
        depart=user.depart,
        username=user.username,
        userid=user.userid,
    )

    admin_targets: set[str] = set()
    for admin in list_users(database_path):
        if admin.role != ROLE_ADMIN:
            continue
        admin_targets.add(admin.userid)
        admin_targets.add(admin.username)

    for target in sorted(admin_targets):
        create_signup_notification(
            database_path,
            user_idx=user.idx,
            target_user=target,
            title=SIGNUP_NOTIFICATION_TITLE,
            message=message,
        )


def register_pending_user(
    database_path: Path,
    *,
    userid: str,
    email: str,
    username: str,
    password: str,
    depart: str,
) -> User:
    signup_date = format_display_datetime()
    user = create_user(
        database_path,
        userid=userid,
        email=email,
        username=username,
        password=password,
        depart=depart,
        role=ROLE_PENDING,
    )
    _notify_admins(database_path, user=user, signup_date=signup_date)
    logger.info("Pending signup registered for userid=%s", user.userid)
    return user


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
    delete_signup_notifications_for_user(database_path, user_idx)
    logger.info("Signup approved for userid=%s", user.userid)
    return updated


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
    delete_signup_notifications_for_user(database_path, user_idx)
    delete_users(database_path, [user_idx])
    logger.info("Signup rejected for userid=%s", user.userid)
    return True


def dismiss_signup_notification(database_path: Path, notification_idx: int) -> bool:
    return delete_signup_notification(database_path, notification_idx)
