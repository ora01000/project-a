import logging
from typing import Protocol

from backend.app.agents.system_agents import NotifyChannel
from backend.app.notifications.email_sender import send_email_notification
from backend.app.notifications.teams_sender import send_teams_notification

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    channel: NotifyChannel

    async def send(
        self,
        *,
        target: str,
        title: str,
        message: str,
        job_idx: int,
        notification_type: str = "review_request",
    ) -> bool: ...


class EmailNotificationChannel:
    channel = NotifyChannel.EMAIL

    def __init__(self, database_path) -> None:
        self._database_path = database_path

    async def send(
        self,
        *,
        target: str,
        title: str,
        message: str,
        job_idx: int,
        notification_type: str = "review_request",
    ) -> bool:
        return await send_email_notification(
            database_path=self._database_path,
            target=target,
            title=title,
            message=message,
            job_idx=job_idx,
        )


class TeamsNotificationChannel:
    channel = NotifyChannel.TEAMS

    async def send(
        self,
        *,
        target: str,
        title: str,
        message: str,
        job_idx: int,
        notification_type: str = "review_request",
    ) -> bool:
        return await send_teams_notification(
            target=target,
            title=title,
            message=message,
            job_idx=job_idx,
        )


class IntegratedChatNotificationChannel:
    channel = NotifyChannel.INTEGRATED_CHAT

    def __init__(self, database_path) -> None:
        self._database_path = database_path

    async def send(
        self,
        *,
        target: str,
        title: str,
        message: str,
        job_idx: int,
        notification_type: str = "review_request",
    ) -> bool:
        from backend.app.db.notifications import create_job_notification

        create_job_notification(
            self._database_path,
            job_idx=job_idx,
            target_user=target,
            notification_type=notification_type,
            title=title,
            message=message,
        )
        return True


def get_notification_channel(channel: NotifyChannel, database_path) -> NotificationChannel:
    if channel == NotifyChannel.EMAIL:
        return EmailNotificationChannel(database_path)
    if channel == NotifyChannel.TEAMS:
        return TeamsNotificationChannel()
    return IntegratedChatNotificationChannel(database_path)


async def dispatch_job_notification(
    *,
    database_path,
    channel: NotifyChannel,
    target: str,
    title: str,
    message: str,
    job_idx: int,
    notification_type: str = "review_request",
) -> bool:
    notifier = get_notification_channel(channel, database_path)
    return await notifier.send(
        target=target,
        title=title,
        message=message,
        job_idx=job_idx,
        notification_type=notification_type,
    )
