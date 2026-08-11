import asyncio
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

import markdown

from backend.app.config import EmailNotificationSettings
from backend.app.notifications.d2_renderer import prepare_markdown_for_email
from backend.app.db.mailserver_config import get_mailserver_config
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


def load_email_settings_from_db(database_path: Path | str | None) -> EmailNotificationSettings | None:
    if database_path is None:
        return None
    row = get_mailserver_config(database_path)
    if row is None:
        return None
    return EmailNotificationSettings(
        enabled=row.enabled,
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_username=row.smtp_username,
        smtp_password=row.smtp_password,
        from_address=row.from_address,
        smtp_auth=row.smtp_auth,
        use_tls=row.use_tls,
        use_ssl=row.use_ssl,
        timeout_seconds=row.timeout_seconds,
    )


def _validate_email_settings(settings: EmailNotificationSettings) -> str | None:
    if not settings.enabled:
        return "메일 발송이 비활성화되어 있습니다"
    if not settings.smtp_host.strip():
        return "SMTP 호스트가 필요합니다"
    if not settings.from_address.strip():
        return "발신 주소가 필요합니다"
    if settings.smtp_auth and not settings.smtp_username.strip():
        return "SMTP 인증이 켜져 있으면 사용자명이 필요합니다"
    return None


def _smtp_login_if_needed(smtp: smtplib.SMTP, settings: EmailNotificationSettings) -> None:
    if not settings.smtp_auth:
        return
    smtp.login(settings.smtp_username, settings.smtp_password)


def convert_markdown_to_html(markdown_text: str) -> str:
    rendered = markdown.markdown(
        markdown_text,
        extensions=["extra", "nl2br", "sane_lists"],
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<style>\n"
        "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; "
        "line-height: 1.6; color: #1e293b; padding: 16px; }\n"
        "pre { background: #f1f5f9; padding: 12px; border-radius: 6px; overflow-x: auto; }\n"
        "code { background: #f1f5f9; padding: 2px 4px; border-radius: 3px; font-size: 0.9em; }\n"
        "table { border-collapse: collapse; margin: 12px 0; }\n"
        "th, td { border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }\n"
        "th { background: #f8fafc; }\n"
        "h1, h2, h3 { color: #0f172a; }\n"
        "blockquote { border-left: 4px solid #94a3b8; margin: 0; padding-left: 12px; color: #475569; }\n"
        "img { max-width: 100%; height: auto; }\n"
        "</style>\n"
        "</head>\n"
        f"<body>\n{rendered}\n</body>\n"
        "</html>"
    )


def _send_email_sync(
    settings: EmailNotificationSettings,
    *,
    to_address: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    message = EmailMessage()
    message["From"] = settings.from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    if settings.use_ssl:
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.timeout_seconds,
        ) as smtp:
            _smtp_login_if_needed(smtp, settings)
            smtp.send_message(message)
        return

    with smtplib.SMTP(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.timeout_seconds,
    ) as smtp:
        if settings.use_tls:
            smtp.starttls()
        _smtp_login_if_needed(smtp, settings)
        smtp.send_message(message)


async def send_test_email(
    *,
    settings: EmailNotificationSettings,
    to_address: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    """Send ignoring the enabled flag (admin test). Returns (ok, message)."""
    if not settings.smtp_host.strip():
        return False, "SMTP 호스트가 필요합니다"
    if not settings.from_address.strip():
        return False, "발신 주소가 필요합니다"
    if settings.smtp_auth and not settings.smtp_username.strip():
        return False, "SMTP 인증이 켜져 있으면 사용자명이 필요합니다"
    try:
        await asyncio.to_thread(
            _send_email_sync,
            settings,
            to_address=to_address,
            subject=subject,
            body=body,
        )
        return True, f"테스트 메일을 {to_address} 로 전송했습니다."
    except Exception as exc:
        logger.exception("Test email failed to=%s: %s", to_address, exc)
        return False, f"메일 전송 실패: {exc}"


async def send_email_notification(
    *,
    database_path: Path | str | None,
    target: str,
    title: str,
    message: str,
    job_idx: int,
    settings: EmailNotificationSettings | None = None,
) -> bool:
    config = settings or load_email_settings_from_db(database_path)
    if config is None:
        logger.warning("Email notification skipped for job=%s: mailserver_config missing", job_idx)
        return False
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


async def send_markdown_email(
    *,
    settings: EmailNotificationSettings,
    to_address: str,
    subject: str,
    markdown_body: str,
) -> None:
    plain_body, html_markdown = prepare_markdown_for_email(markdown_body.strip())
    html_body = convert_markdown_to_html(html_markdown)
    await asyncio.to_thread(
        _send_email_sync,
        settings,
        to_address=to_address,
        subject=subject,
        body=plain_body,
        html_body=html_body,
    )


async def send_job_report_emails(
    *,
    database_path: Path | str | None,
    recipient_emails: list[str],
    subject: str,
    markdown_body: str,
    settings: EmailNotificationSettings | None = None,
) -> tuple[int, list[str]]:
    """Send markdown report to multiple recipients. Returns (sent_count, failed_recipients)."""
    config = settings or load_email_settings_from_db(database_path)
    if config is None:
        raise ValueError("메일 서버 설정이 없습니다.")
    validation_error = _validate_email_settings(config)
    if validation_error:
        raise ValueError(validation_error)

    unique_recipients = []
    seen: set[str] = set()
    for address in recipient_emails:
        normalized = address.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_recipients.append(normalized)

    if not unique_recipients:
        raise ValueError("수신자 이메일이 없습니다.")

    sent_count = 0
    failed: list[str] = []
    for recipient in unique_recipients:
        try:
            await send_markdown_email(
                settings=config,
                to_address=recipient,
                subject=subject,
                markdown_body=markdown_body,
            )
            sent_count += 1
            logger.info("Job report email sent to=%s subject=%s", recipient, subject)
        except Exception as exc:
            logger.exception("Job report email failed to=%s: %s", recipient, exc)
            failed.append(recipient)
    return sent_count, failed


async def send_signup_rejection_email(
    *,
    database_path: Path | str | None,
    to_address: str,
    username: str,
    userid: str,
    reason: str,
) -> bool:
    config = load_email_settings_from_db(database_path)
    if config is None:
        logger.warning("Signup rejection email skipped for %s: mailserver_config missing", userid)
        return False
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
