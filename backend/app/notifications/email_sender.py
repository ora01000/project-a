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
    to_addresses: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    cc_addresses: list[str] | None = None,
    bcc_addresses: list[str] | None = None,
) -> None:
    if not to_addresses:
        raise ValueError("수신자 이메일이 없습니다.")

    cc_list = [address.strip() for address in (cc_addresses or []) if address.strip()]
    bcc_list = [address.strip() for address in (bcc_addresses or []) if address.strip()]

    message = EmailMessage()
    message["From"] = settings.from_address
    message["To"] = ", ".join(to_addresses)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    if bcc_list:
        message["Bcc"] = ", ".join(bcc_list)
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    delivery_targets = list(dict.fromkeys([*to_addresses, *cc_list, *bcc_list]))

    if settings.use_ssl:
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.timeout_seconds,
        ) as smtp:
            _smtp_login_if_needed(smtp, settings)
            smtp.send_message(message, to_addrs=delivery_targets)
        return

    with smtplib.SMTP(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.timeout_seconds,
    ) as smtp:
        if settings.use_tls:
            smtp.starttls()
        _smtp_login_if_needed(smtp, settings)
        smtp.send_message(message, to_addrs=delivery_targets)


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
            to_addresses=[to_address],
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
            to_addresses=[recipient],
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
    to_addresses: list[str],
    subject: str,
    markdown_body: str,
    cc_addresses: list[str] | None = None,
    bcc_addresses: list[str] | None = None,
) -> None:
    plain_body, html_markdown = prepare_markdown_for_email(markdown_body.strip())
    html_body = convert_markdown_to_html(html_markdown)
    await asyncio.to_thread(
        _send_email_sync,
        settings,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        subject=subject,
        body=plain_body,
        html_body=html_body,
    )


def compose_report_markdown(*, forward_message: str, report_body: str) -> str:
    forward = forward_message.strip()
    report = report_body.strip()
    if forward and report:
        return f"{forward}\n\n---\n\n{report}"
    if forward:
        return forward
    return report


async def send_job_report_emails(
    *,
    database_path: Path | str | None,
    to_addresses: list[str],
    subject: str,
    markdown_body: str,
    cc_addresses: list[str] | None = None,
    bcc_addresses: list[str] | None = None,
    settings: EmailNotificationSettings | None = None,
) -> tuple[int, list[str]]:
    """Send one markdown report email with To/Cc/Bcc. Returns (recipient_count, failed_recipients)."""
    config = settings or load_email_settings_from_db(database_path)
    if config is None:
        raise ValueError("메일 서버 설정이 없습니다.")
    validation_error = _validate_email_settings(config)
    if validation_error:
        raise ValueError(validation_error)

    unique_to = list(dict.fromkeys(address.strip() for address in to_addresses if address.strip()))
    unique_cc = list(dict.fromkeys(address.strip() for address in (cc_addresses or []) if address.strip()))
    unique_bcc = list(dict.fromkeys(address.strip() for address in (bcc_addresses or []) if address.strip()))

    if not unique_to:
        raise ValueError("수신자 이메일이 없습니다.")

    recipient_count = len(set([*unique_to, *unique_cc, *unique_bcc]))
    try:
        await send_markdown_email(
            settings=config,
            to_addresses=unique_to,
            cc_addresses=unique_cc,
            bcc_addresses=unique_bcc,
            subject=subject,
            markdown_body=markdown_body,
        )
        logger.info(
            "Job report email sent to=%s cc=%s bcc=%s subject=%s",
            unique_to,
            unique_cc,
            unique_bcc,
            subject,
        )
        return recipient_count, []
    except Exception as exc:
        logger.exception("Job report email failed: %s", exc)
        return 0, unique_to


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
            to_addresses=[to_address],
            subject=subject,
            body=body,
        )
        logger.info("Signup rejection email sent to=%s", to_address)
        return True
    except Exception as exc:
        logger.exception("Signup rejection email failed to=%s: %s", to_address, exc)
        return False


SIGNUP_APPROVAL_ACCESS_URL = "http://axit.apps.pcicd-k8s.lguplus.co.kr"


async def send_signup_approval_email(
    *,
    database_path: Path | str | None,
    to_address: str,
    username: str,
    userid: str,
    access_url: str = SIGNUP_APPROVAL_ACCESS_URL,
) -> bool:
    config = load_email_settings_from_db(database_path)
    if config is None:
        logger.warning("Signup approval email skipped for %s: mailserver_config missing", userid)
        return False
    validation_error = _validate_email_settings(config)
    if validation_error:
        logger.warning("Signup approval email skipped for %s: %s", userid, validation_error)
        return False

    recipient = to_address.strip()
    if not recipient or "@" not in recipient:
        logger.warning("Signup approval email skipped for %s: invalid email", userid)
        return False

    display_name = (username or "").strip() or userid
    subject = "회원 가입 신청 승인 안내"
    body = (
        f"{display_name} 님이 신청하신 접속 권한 신청이 승인되었습니다.\n"
        f"접속 경로는 {access_url} 입니다.\n"
        "감사합니다."
    )
    try:
        await asyncio.to_thread(
            _send_email_sync,
            config,
            to_addresses=[recipient],
            subject=subject,
            body=body,
        )
        logger.info("Signup approval email sent to=%s", recipient)
        return True
    except Exception as exc:
        logger.exception("Signup approval email failed to=%s: %s", recipient, exc)
        return False


WHATAP_SUBSCRIBER_FORWARD_MESSAGE = (
    "본 메일은 Whatap 이벤트 리포트 구독자에게 자동으로 발송하는 메일입니다."
)


async def send_whatap_event_subscriber_report(
    *,
    database_path: Path | str | None,
    job_title: str,
    report_body: str,
    settings: EmailNotificationSettings | None = None,
) -> tuple[int, list[str]]:
    """Email Whatap completion report to users with ``whatap_event_sub=True``.

    Returns ``(sent_recipient_count, skipped_or_failed_targets)``.
    """
    if database_path is None:
        logger.warning("Whatap subscriber report skipped: database_path missing")
        return 0, []

    from backend.app.db.roles import ROLE_ADMIN

    subscribers = [
        user
        for user in list_users(database_path, viewer_role=ROLE_ADMIN)
        if user.whatap_event_sub and "@" in (user.email or "")
    ]
    if not subscribers:
        logger.info("Whatap subscriber report skipped: no subscribers with email")
        return 0, []

    to_addresses = list(
        dict.fromkeys(user.email.strip() for user in subscribers if user.email.strip())
    )
    if not to_addresses:
        logger.info("Whatap subscriber report skipped: no valid subscriber emails")
        return 0, [user.userid for user in subscribers]

    markdown_body = compose_report_markdown(
        forward_message=WHATAP_SUBSCRIBER_FORWARD_MESSAGE,
        report_body=report_body,
    )
    subject = (job_title or "").strip() or "Whatap 이벤트 리포트"

    try:
        sent_count, failed = await send_job_report_emails(
            database_path=database_path,
            to_addresses=to_addresses,
            subject=subject,
            markdown_body=markdown_body,
            settings=settings,
        )
        if failed:
            logger.warning(
                "Whatap subscriber report partially failed subject=%s failed=%s",
                subject,
                failed,
            )
        else:
            logger.info(
                "Whatap subscriber report sent subject=%s recipients=%s",
                subject,
                sent_count,
            )
        return sent_count, failed
    except Exception as exc:
        logger.exception("Whatap subscriber report failed subject=%s: %s", subject, exc)
        return 0, [user.userid for user in subscribers]


AX_INFRA_COMPLETION_FORWARD_MESSAGE = (
    "본 메일은 요청하신 작업 요청서의 처리 결과를 요청자에게 자동으로 발송하는 메일입니다."
)
AX_INFRA_REJECTION_FORWARD_MESSAGE = (
    "본 메일은 요청하신 작업 요청서의 반려를 요청자에게 자동으로 발송하는 메일입니다."
)
AX_INFRA_CANCELLATION_FORWARD_MESSAGE = (
    "본 메일은 요청하신 작업 요청서의 취소를 요청자에게 자동으로 발송하는 메일입니다."
)


def _resolve_ax_infra_mail_targets(
    database_path: Path | str | None,
    requester_email: str,
    approver_userid: str | None,
) -> tuple[str | None, list[str]]:
    to_address = (requester_email or "").strip()
    if not to_address or "@" not in to_address:
        return None, []

    cc_addresses: list[str] = []
    if database_path is not None and (approver_userid or "").strip():
        from backend.app.db.users import get_user_by_userid

        approver = get_user_by_userid(database_path, approver_userid.strip())
        if approver is not None:
            approver_email = (approver.email or "").strip()
            if "@" in approver_email and approver_email.lower() != to_address.lower():
                cc_addresses = [approver_email]
    return to_address, cc_addresses


async def _send_ax_infra_requester_notice(
    *,
    database_path: Path | str | None,
    subject_prefix: str,
    job_title: str,
    requester_email: str,
    approver_userid: str | None,
    forward_message: str,
    report_body: str,
    log_label: str,
    settings: EmailNotificationSettings | None = None,
) -> tuple[int, list[str]]:
    to_address, cc_addresses = _resolve_ax_infra_mail_targets(
        database_path, requester_email, approver_userid
    )
    if to_address is None:
        logger.warning("%s skipped: invalid requester_email=%s", log_label, requester_email)
        return 0, []

    title = (job_title or "").strip() or "작업 요청서"
    subject = f"{subject_prefix} {title}"
    markdown_body = compose_report_markdown(
        forward_message=forward_message,
        report_body=report_body,
    )

    try:
        sent_count, failed = await send_job_report_emails(
            database_path=database_path,
            to_addresses=[to_address],
            cc_addresses=cc_addresses,
            subject=subject,
            markdown_body=markdown_body,
            settings=settings,
        )
        if failed:
            logger.warning(
                "%s partially failed subject=%s failed=%s",
                log_label,
                subject,
                failed,
            )
        else:
            logger.info(
                "%s sent subject=%s to=%s cc=%s recipients=%s",
                log_label,
                subject,
                to_address,
                cc_addresses,
                sent_count,
            )
        return sent_count, failed
    except Exception as exc:
        logger.exception("%s failed subject=%s: %s", log_label, subject, exc)
        return 0, [to_address, *cc_addresses]


async def send_ax_infra_job_completion_email(
    *,
    database_path: Path | str | None,
    job_title: str,
    requester_email: str,
    approver_userid: str | None,
    report_body: str,
    settings: EmailNotificationSettings | None = None,
) -> tuple[int, list[str]]:
    """Email job_type=1 completion result to requester, Cc approver."""
    return await _send_ax_infra_requester_notice(
        database_path=database_path,
        subject_prefix="[작업처리결과]",
        job_title=job_title,
        requester_email=requester_email,
        approver_userid=approver_userid,
        forward_message=AX_INFRA_COMPLETION_FORWARD_MESSAGE,
        report_body=report_body,
        log_label="AX infra completion email",
        settings=settings,
    )


async def send_ax_infra_job_rejection_email(
    *,
    database_path: Path | str | None,
    job_title: str,
    requester_email: str,
    approver_userid: str | None,
    reject_reason: str,
    settings: EmailNotificationSettings | None = None,
) -> tuple[int, list[str]]:
    """Email job_type=1 rejection (status 12) to requester, Cc approver."""
    return await _send_ax_infra_requester_notice(
        database_path=database_path,
        subject_prefix="[작업반려]",
        job_title=job_title,
        requester_email=requester_email,
        approver_userid=approver_userid,
        forward_message=AX_INFRA_REJECTION_FORWARD_MESSAGE,
        report_body=(reject_reason or "").strip(),
        log_label="AX infra rejection email",
        settings=settings,
    )


async def send_ax_infra_job_cancellation_email(
    *,
    database_path: Path | str | None,
    job_title: str,
    requester_email: str,
    approver_userid: str | None,
    drop_reason: str,
    settings: EmailNotificationSettings | None = None,
) -> tuple[int, list[str]]:
    """Email job_type=1 cancellation (status 13) to requester, Cc approver."""
    return await _send_ax_infra_requester_notice(
        database_path=database_path,
        subject_prefix="[작업취소]",
        job_title=job_title,
        requester_email=requester_email,
        approver_userid=approver_userid,
        forward_message=AX_INFRA_CANCELLATION_FORWARD_MESSAGE,
        report_body=(drop_reason or "").strip(),
        log_label="AX infra cancellation email",
        settings=settings,
    )


async def send_signup_request_admin_emails(
    *,
    database_path: Path | str | None,
    job_title: str,
    srnum: str,
    requester_name: str,
    request_reason: str,
    settings: EmailNotificationSettings | None = None,
) -> tuple[int, list[str]]:
    """Notify role=0 admins when a signup access-request job is received."""
    if database_path is None:
        logger.warning("Signup request admin email skipped: database_path missing")
        return 0, []

    from backend.app.db.roles import ROLE_ADMIN

    admins = [
        user
        for user in list_users(database_path, viewer_role=ROLE_ADMIN)
        if user.role == ROLE_ADMIN and "@" in (user.email or "")
    ]
    if not admins:
        logger.info("Signup request admin email skipped: no role=0 admins with email")
        return 0, []

    to_addresses = list(
        dict.fromkeys(user.email.strip() for user in admins if user.email.strip())
    )
    if not to_addresses:
        logger.info("Signup request admin email skipped: no valid admin emails")
        return 0, [user.userid for user in admins]

    forward_message = (
        f"[{srnum}]{requester_name} 님이 신규 사용자 접속 권한을 신청하셨습니다."
    )
    markdown_body = compose_report_markdown(
        forward_message=forward_message,
        report_body=(request_reason or "").strip(),
    )
    subject = (job_title or "").strip() or "신규 사용자 접속 권한 신청서"

    try:
        sent_count, failed = await send_job_report_emails(
            database_path=database_path,
            to_addresses=to_addresses,
            subject=subject,
            markdown_body=markdown_body,
            settings=settings,
        )
        if failed:
            logger.warning(
                "Signup request admin email partially failed subject=%s failed=%s",
                subject,
                failed,
            )
        else:
            logger.info(
                "Signup request admin email sent subject=%s recipients=%s",
                subject,
                sent_count,
            )
        return sent_count, failed
    except Exception as exc:
        logger.exception("Signup request admin email failed subject=%s: %s", subject, exc)
        return 0, [user.userid for user in admins]
