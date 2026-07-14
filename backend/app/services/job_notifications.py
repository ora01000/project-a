from pathlib import Path

from backend.app.agents.system_agents import NotifyChannel
from backend.app.db.users import list_users
from backend.app.notifications.channels import dispatch_job_notification


def parse_notify_channel(value: str | None) -> NotifyChannel:
    if not value:
        return NotifyChannel.INTEGRATED_CHAT
    try:
        return NotifyChannel(value.strip().lower())
    except ValueError:
        return NotifyChannel.INTEGRATED_CHAT


def resolve_user_targets(database_path: Path, identifier: str) -> list[str]:
    """Resolve a recipient identifier to a single integrated-chat target.

    Registered users are stored by userid only (never username), so the same
    job notification is not inserted twice.
    """
    normalized = identifier.strip()
    if not normalized:
        return []
    for user in list_users(database_path):
        if user.userid == normalized or user.username == normalized:
            return [user.userid]
    return [normalized]


def resolve_user_emails(database_path: Path, identifier: str) -> list[str]:
    from backend.app.notifications.email_sender import resolve_recipient_email

    emails: set[str] = set()
    direct = resolve_recipient_email(database_path, identifier)
    if direct:
        emails.add(direct)

    for user in list_users(database_path):
        if user.username == identifier or user.userid == identifier:
            emails.add(user.email)
    return sorted(emails)


def _resolve_targets_for_channel(
    database_path: Path,
    channel: NotifyChannel,
    recipients: list[str],
    *,
    fallback_emails: list[str] | None = None,
) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()

    if channel == NotifyChannel.EMAIL:
        if fallback_emails:
            for email in fallback_emails:
                normalized = email.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    targets.append(normalized)
        for recipient in recipients:
            for email in resolve_user_emails(database_path, recipient):
                if email not in seen:
                    seen.add(email)
                    targets.append(email)
        return targets

    if channel == NotifyChannel.TEAMS:
        for recipient in recipients:
            normalized = recipient.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                targets.append(normalized)
        return targets

    for recipient in recipients:
        for target in resolve_user_targets(database_path, recipient):
            if target not in seen:
                seen.add(target)
                targets.append(target)
    return targets


async def send_job_notifications(
    database_path: Path,
    *,
    channel: NotifyChannel,
    recipients: list[str],
    title: str,
    message: str,
    job_idx: int,
    notification_type: str,
    fallback_emails: list[str] | None = None,
) -> None:
    targets = _resolve_targets_for_channel(
        database_path,
        channel,
        recipients,
        fallback_emails=fallback_emails,
    )

    for target in targets:
        await dispatch_job_notification(
            database_path=database_path,
            channel=channel,
            target=target,
            title=title,
            message=message,
            job_idx=job_idx,
            notification_type=notification_type,
        )
