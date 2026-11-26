"""Transactional email delivery service for authentication workflows."""

import asyncio
import html
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import urlencode

import structlog

from app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


def _sanitize_header_value(value: str) -> str:
    """Strip CR/LF characters to prevent email header injection."""
    return value.replace("\r", "").replace("\n", "").strip()


class EmailSender(Protocol):
    """Protocol for transactional email senders."""

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None:
        """Deliver a single email message."""


class LoggingEmailSender:
    """Development/test sender that avoids external SMTP calls."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None:
        """Log email metadata; emit body preview only in local development."""
        _ = html_body
        domain = to_email.rsplit("@", maxsplit=1)[-1] if "@" in to_email else "unknown"
        if self._settings.is_development:
            logger.info(
                "email.dev_preview",
                recipient_domain=domain,
                subject=subject,
                preview=text_body,
            )
        else:
            logger.info(
                "email.suppressed_non_smtp",
                environment=self._settings.APP_ENV,
                recipient_domain=domain,
                subject=subject,
            )


class SmtpEmailSender:
    """SMTP transactional email sender executed off the event loop."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _send_sync(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None:
        msg = EmailMessage()
        msg["From"] = _sanitize_header_value(self._settings.SMTP_FROM)
        msg["To"] = _sanitize_header_value(to_email)
        msg["Subject"] = _sanitize_header_value(subject)
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        context = ssl.create_default_context()
        timeout = float(self._settings.SMTP_TIMEOUT_SECONDS)

        if self._settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(
                self._settings.SMTP_HOST,
                self._settings.SMTP_PORT,
                timeout=timeout,
                context=context,
            ) as server:
                self._authenticate_and_send(server, msg)
        else:
            with smtplib.SMTP(
                self._settings.SMTP_HOST,
                self._settings.SMTP_PORT,
                timeout=timeout,
            ) as server:
                if self._settings.SMTP_USE_STARTTLS:
                    server.starttls(context=context)
                self._authenticate_and_send(server, msg)

    def _authenticate_and_send(self, server: smtplib.SMTP, msg: EmailMessage) -> None:
        smtp_password = self._settings.SMTP_PASSWORD.get_secret_value()
        if self._settings.SMTP_USER and smtp_password:
            server.login(self._settings.SMTP_USER, smtp_password)
        server.send_message(msg)

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None:
        """Send email over SMTP via thread pool."""
        await asyncio.to_thread(
            self._send_sync,
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )


def get_email_sender(settings: Settings | None = None) -> EmailSender:
    """Select SMTP or development logging email sender based on settings."""
    cfg = settings or get_settings()
    if cfg.SMTP_HOST.strip():
        return SmtpEmailSender(cfg)
    return LoggingEmailSender(cfg)


def build_action_url(base_url: str, raw_token: str) -> str:
    """Append a URL-encoded single-use token query parameter to base_url."""
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'token': raw_token})}"


def render_verification_email(user_name: str, verification_url: str) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for account email verification."""
    safe_name = html.escape(user_name)
    safe_url = html.escape(verification_url, quote=True)
    subject = "Verify your FinSight email address"
    text_body = (
        f"Hello {user_name},\n\n"
        "Please verify your FinSight account by opening the link below:\n"
        f"{verification_url}\n\n"
        "If you did not create a FinSight account, you can ignore this email.\n\n"
        "FinSight provides financial analysis assistance only and is not investment advice."
    )
    html_body = (
        "<!DOCTYPE html><html><body>"
        f"<p>Hello {safe_name},</p>"
        "<p>Please verify your FinSight account by clicking the link below:</p>"
        f'<p><a href="{safe_url}">Verify email address</a></p>'
        "<p>If you did not create a FinSight account, you can safely ignore this message.</p>"
        "<hr><p><small>FinSight provides financial analysis assistance only "
        "and is not investment advice.</small></p>"
        "</body></html>"
    )
    return subject, text_body, html_body


def render_password_reset_email(user_name: str, reset_url: str) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for password reset."""
    safe_name = html.escape(user_name)
    safe_url = html.escape(reset_url, quote=True)
    subject = "Reset your FinSight password"
    text_body = (
        f"Hello {user_name},\n\n"
        "We received a request to reset your FinSight password. Open the link below to proceed:\n"
        f"{reset_url}\n\n"
        "If you did not request a password reset, you can ignore this email.\n\n"
        "FinSight provides financial analysis assistance only and is not investment advice."
    )
    html_body = (
        "<!DOCTYPE html><html><body>"
        f"<p>Hello {safe_name},</p>"
        "<p>We received a request to reset your FinSight password:</p>"
        f'<p><a href="{safe_url}">Reset password</a></p>'
        "<p>If you did not request this, you can safely ignore this email.</p>"
        "<hr><p><small>FinSight provides financial analysis assistance only "
        "and is not investment advice.</small></p>"
        "</body></html>"
    )
    return subject, text_body, html_body
