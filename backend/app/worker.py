"""FinSight ARQ background worker tasks and lifecycle."""

from typing import Any

import structlog

from app.core.config import get_settings
from app.core.queue import build_arq_redis_settings
from app.services.email import (
    get_email_sender,
    render_password_reset_email,
    render_verification_email,
)

logger = structlog.get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """Minimal F0 health/smoke job for the background worker."""
    _ = ctx
    return "pong"


async def send_verification_email_task(
    ctx: dict[str, Any],
    to_email: str,
    user_name: str,
    verification_url: str,
) -> None:
    """Send account verification email via configured EmailSender."""
    _ = ctx
    subject, text_body, html_body = render_verification_email(user_name, verification_url)
    sender = get_email_sender()
    await sender.send_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )


async def send_password_reset_email_task(
    ctx: dict[str, Any],
    to_email: str,
    user_name: str,
    reset_url: str,
) -> None:
    """Send password reset email via configured EmailSender."""
    _ = ctx
    subject, text_body, html_body = render_password_reset_email(user_name, reset_url)
    sender = get_email_sender()
    await sender.send_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )


async def on_startup(ctx: dict[str, Any]) -> None:
    """Worker startup lifecycle hook."""
    settings = get_settings()
    ctx["app_env"] = settings.APP_ENV
    logger.info("worker.startup", environment=settings.APP_ENV)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown lifecycle hook."""
    _ = ctx
    logger.info("worker.shutdown")


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [ping, send_verification_email_task, send_password_reset_email_task]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = build_arq_redis_settings()
    keep_result = 0
    max_tries = 3
