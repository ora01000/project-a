import asyncio
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from backend.app.config import EmailNotificationSettings, load_notification_settings
from backend.app.db.users import list_users

logger = logging.getLogger(__name__)


def resolve_recipient_email(database_path: Path | str | None, target: str) -> str | None:
    trimmed = target.strip()
    if "@" in trimmed:
        return trimmed

    if database_path is None:
        return None

    for user in list_users(database_path):
        if user.userid == trimmed or user.username == trimmed:
            return user.email
    return None


def _validate_email_settings(settings: EmailNotificationSettings) -> str | None:
    if not settings.enabled:
        return "EMAIL_ENABLED is false"
    if not settings.smtp_host.strip():
        return "EMAIL_SMTP_HOST is required"
    if not settings.from_address.strip():
        return "EMAIL_FROM_ADDRESS is required"
    return None


def _send_email_sync(
    settings: EmailNotificationSettings,
    *,
    to_address: str,
    subject: str,
    body: str,
) -> None:
    message = EmailMessage()
    message["From"] = settings.from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    if settings.use_ssl:
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.timeout_seconds,
        ) as smtp:
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.timeout_seconds,
    ) as smtp:
        if settings.use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def send_email_notification(
    *,
    database_path: Path | str | None,
    target: str,
    title: str,
    message: str,
    job_idx: int,
    settings: EmailNotificationSettings | None = None,
) -> bool:
    config = settings or load_notification_settings().email
    validation_error = _validate_email_settings(config)
    if validation_error:
        logger.warning("Email notification skipped for job=%s: %s", job_idx, validation_error)
        return False

    recipient = resolve_recipient_email(database_path, target)
    if not recipient:
        logger.warning(
            "Email notification skipped for job=%s: cannot resolve recipient from target=%s",
            job_idx,
            target,
        )
        return False

    body = f"{message}\n\n작업 ID: {job_idx}\n수신 대상: {target}"
    try:
        await asyncio.to_thread(
            _send_email_sync,
            config,
            to_address=recipient,
            subject=title,
            body=body,
        )
        logger.info("Email notification sent for job=%s to=%s", job_idx, recipient)
        return True
    except Exception as exc:
        logger.exception("Email notification failed for job=%s to=%s: %s", job_idx, recipient, exc)
        return False


async def send_signup_rejection_email(
    *,
    database_path: Path | str | None,
    to_address: str,
    username: str,
    userid: str,
    reason: str,
) -> bool:
    config = load_notification_settings().email
    validation_error = _validate_email_settings(config)
    if validation_error:
        logger.warning("Signup rejection email skipped for %s: %s", userid, validation_error)
        return False

    subject = "회원 가입 신청 반려 안내"
    body = (
        f"{username}({userid})님, 회원 가입 신청이 반려되었습니다.\n\n"
        f"반려 사유:\n{reason}\n\n"
        "문의 사항이 있으시면 관리자에게 연락해 주세요."
    )
    try:
        await asyncio.to_thread(
            _send_email_sync,
            config,
            to_address=to_address,
            subject=subject,
            body=body,
        )
        logger.info("Signup rejection email sent to=%s", to_address)
        return True
    except Exception as exc:
        logger.exception("Signup rejection email failed to=%s: %s", to_address, exc)
        return False
