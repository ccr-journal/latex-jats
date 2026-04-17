"""Email sending for author invitations.

Uses stdlib smtplib + email.mime, wrapped in asyncio.to_thread() to avoid
blocking the event loop.  The editor provides a markdown template with
``{names}`` as a placeholder; we format a natural-language name list
(e.g. "Alice, Bob, and Carol") and convert the markdown to HTML via the
``markdown`` library.  A single email is sent to all authors.
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
Dear {names},

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


def _format_names(names: list[str]) -> str:
    """Format a list of names as natural-language enumeration."""
    if len(names) == 0:
        return "Authors"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def default_template(title: str, author_url: str) -> str:
    """Return the default invitation template with title and URL filled in."""
    return DEFAULT_TEMPLATE.format(
        names="{names}", title=title, author_url=author_url,
    )


def _send(
    recipients: list[tuple[str, str]],  # (name, email) pairs
    subject: str,
    body_md: str,
    cfg: AuthConfig,
) -> None:
    """Send a single invitation email to all authors (blocking)."""
    names = _format_names([name for name, _ in recipients])
    plain = body_md.replace("{names}", names)
    html = md.markdown(plain)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_from
    msg["To"] = ", ".join(f"{name} <{email}>" for name, email in recipients)
    msg["Reply-To"] = cfg.smtp_from

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
        if cfg.smtp_user and cfg.smtp_password:
            server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(msg)


async def send_invite_email(
    subject: str,
    body_md: str,
    authors: list[tuple[str, str]],  # (name, email) pairs
    cfg: AuthConfig | None = None,
) -> None:
    """Send a single invitation email to all authors.

    ``body_md`` is a markdown template; ``{names}`` is replaced with a
    formatted name list (e.g. "Alice, Bob, and Carol").
    """
    cfg = cfg or get_config()
    await asyncio.to_thread(_send, authors, subject, body_md, cfg)
    logger.info(
        "Sent invite email to %s",
        ", ".join(f"{name} <{email}>" for name, email in authors),
    )
