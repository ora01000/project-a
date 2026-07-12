import logging
from typing import Any

import httpx

from backend.app.config import TeamsNotificationSettings, load_notification_settings

logger = logging.getLogger(__name__)

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
GRAPH_MESSAGE_URL = (
    "https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages"
)


def _validate_teams_settings(settings: TeamsNotificationSettings) -> str | None:
    if not settings.enabled:
        return "TEAMS_ENABLED is false"

    if settings.mode == "webhook":
        if not settings.webhook_url.strip():
            return "TEAMS_WEBHOOK_URL is required for webhook mode"
        return None

    if settings.mode == "graph":
        missing = [
            name
            for name, value in {
                "TEAMS_TENANT_ID": settings.tenant_id,
                "TEAMS_CLIENT_ID": settings.client_id,
                "TEAMS_CLIENT_SECRET": settings.client_secret,
                "TEAMS_TEAM_ID": settings.team_id,
                "TEAMS_CHANNEL_ID": settings.channel_id,
            }.items()
            if not value.strip()
        ]
        if missing:
            return f"{', '.join(missing)} required for graph mode"
        return None

    return f"Unsupported TEAMS_MODE: {settings.mode}"


def _build_teams_payload(*, title: str, message: str, target: str, job_idx: int) -> dict[str, Any]:
    text = f"{message}\n\n작업 ID: {job_idx}\n대상: {target}"
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": "0078D7",
        "title": title,
        "text": text,
    }


async def _get_graph_access_token(
    client: httpx.AsyncClient,
    settings: TeamsNotificationSettings,
) -> str:
    token_url = GRAPH_TOKEN_URL.format(tenant_id=settings.tenant_id)
    response = await client.post(
        token_url,
        data={
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "scope": GRAPH_SCOPE,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError("Graph token response missing access_token")
    return str(access_token)


async def _send_via_webhook(
    client: httpx.AsyncClient,
    settings: TeamsNotificationSettings,
    payload: dict[str, Any],
) -> None:
    response = await client.post(settings.webhook_url, json=payload)
    response.raise_for_status()


async def _send_via_graph(
    client: httpx.AsyncClient,
    settings: TeamsNotificationSettings,
    *,
    title: str,
    message: str,
    target: str,
    job_idx: int,
) -> None:
    access_token = await _get_graph_access_token(client, settings)
    message_url = GRAPH_MESSAGE_URL.format(
        team_id=settings.team_id,
        channel_id=settings.channel_id,
    )
    content = f"**{title}**\n\n{message}\n\n작업 ID: {job_idx}\n대상: {target}"
    response = await client.post(
        message_url,
        json={"body": {"contentType": "html", "content": content.replace(chr(10), "<br/>")}},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()


async def send_teams_notification(
    *,
    target: str,
    title: str,
    message: str,
    job_idx: int,
    settings: TeamsNotificationSettings | None = None,
) -> bool:
    config = settings or load_notification_settings().teams
    validation_error = _validate_teams_settings(config)
    if validation_error:
        logger.warning("Teams notification skipped for job=%s: %s", job_idx, validation_error)
        return False

    payload = _build_teams_payload(title=title, message=message, target=target, job_idx=job_idx)
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            if config.mode == "webhook":
                await _send_via_webhook(client, config, payload)
            else:
                await _send_via_graph(
                    client,
                    config,
                    title=title,
                    message=message,
                    target=target,
                    job_idx=job_idx,
                )
        logger.info("Teams notification sent for job=%s target=%s mode=%s", job_idx, target, config.mode)
        return True
    except Exception as exc:
        logger.exception("Teams notification failed for job=%s target=%s: %s", job_idx, target, exc)
        return False
