"""Email sending for author invitations.

Uses stdlib smtplib + email.mime, wrapped in asyncio.to_thread() to avoid
blocking the event loop.  The editor provides a markdown template with
``{name}`` as a placeholder; we substitute per recipient, then convert to
HTML via the ``markdown`` library.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import markdown as md

from .config import AuthConfig, get_config

logger = logging.getLogger("latex_jats.web.email")


DEFAULT_TEMPLATE = """\
Dear {name},

Your manuscript "{title}" is now in production at Computational Communication Research (CCR).

Please use the link below to access your manuscript:

{author_url}

From this page you can:

1. Upload your LaTeX source files (if not already uploaded).
2. Review the conversion output and fix any issues in your source.
3. Check the HTML and PDF proofs.
4. Approve the proofs for publication once everything looks correct.

If you have any questions, please reply to this email.

Best regards,
Computational Communication Research"""


def default_template(title: str, author_url: str) -> str:
    """Return the default invitation template with title and URL filled in."""
    return DEFAULT_TEMPLATE.format(
        name="{name}", title=title, author_url=author_url,
    )


def _send_one(
    name: str,
    email: str,
    subject: str,
    body_md: str,
    cfg: AuthConfig,
) -> None:
    """Send a single invitation email (blocking)."""
    plain = body_md.replace("{name}", name)
    html = md.markdown(plain)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_from
    msg["To"] = email
    msg["Reply-To"] = cfg.smtp_from

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
        if cfg.smtp_user and cfg.smtp_password:
            server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(msg)


async def send_invite_emails(
    subject: str,
    body_md: str,
    authors: list[tuple[str, str]],  # (name, email) pairs
    cfg: AuthConfig | None = None,
) -> dict[str, list[str]]:
    """Send invitation emails to authors.

    ``body_md`` is a markdown template; ``{name}`` is replaced per recipient.
    Returns {"sent": [...names], "failed": [...names]}.
    """
    cfg = cfg or get_config()
    sent: list[str] = []
    failed: list[str] = []

    for name, email in authors:
        try:
            await asyncio.to_thread(
                _send_one, name, email, subject, body_md, cfg
            )
            sent.append(name)
            logger.info("Sent invite email to %s <%s>", name, email)
        except Exception:
            failed.append(name)
            logger.exception("Failed to send invite email to %s <%s>", name, email)

    return {"sent": sent, "failed": failed}
