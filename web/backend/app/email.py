"""Email sending for author invitations.

Uses stdlib smtplib + email.mime, wrapped in asyncio.to_thread() to avoid
blocking the event loop.  The editor provides a ready-to-send markdown body
which is converted to HTML via the ``markdown`` library.  A single email is
sent to all recipients.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import markdown as md

from .config import AuthConfig, get_config

logger = logging.getLogger("jatsmith.web.email")


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


def default_template(title: str, author_url: str, author_name: str) -> str:
    """Return the default invitation template with all values filled in."""
    return DEFAULT_TEMPLATE.format(
        name=author_name, title=title, author_url=author_url,
    )


def completion_template(
    *,
    title: str,
    succeeded: bool,
    pipeline_steps: list[dict] | None,
    author_url: str,
) -> tuple[str, str]:
    """Build the (subject, body_md) for a conversion-completion notification."""
    verb = "finished" if succeeded else "failed"
    subject = f"Conversion {verb}: {title}"

    if pipeline_steps:
        steps_md = "\n".join(
            f"- **{s.get('name', '?')}**: {s.get('status', 'unknown')}"
            for s in pipeline_steps
        )
    else:
        steps_md = "_(no step information available)_"

    headline = (
        "Your manuscript has finished conversion."
        if succeeded
        else "Conversion did not complete successfully."
    )

    body_md = (
        f"{headline}\n\n"
        f"**Manuscript:** {title}\n\n"
        f"**Pipeline results:**\n\n"
        f"{steps_md}\n\n"
        f"Open the manuscript here:\n\n"
        f"{author_url}\n\n"
        f"Please review the proofs and any warnings or errors, then either "
        f"approve the manuscript or upload a corrected source.\n\n"
        f"— Computational Communication Research"
    )
    return subject, body_md


def _send(
    recipients: list[tuple[str, str]],  # (name, email) pairs
    subject: str,
    body_md: str,
    cfg: AuthConfig,
) -> None:
    """Send a single invitation email to all recipients (blocking)."""
    plain = body_md
    html = md.markdown(plain)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_from
    # formataddr properly quotes display names with special chars and emits
    # just the bare address when the name is empty — important for Gmail's
    # spam heuristics (a long, odd-looking display name flags as suspicious).
    msg["To"] = ", ".join(formataddr((name, email)) for name, email in recipients)
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
    """Send a single invitation email to all recipients."""
    cfg = cfg or get_config()
    await asyncio.to_thread(_send, authors, subject, body_md, cfg)
    logger.info(
        "Sent invite email to %s",
        ", ".join(f"{name} <{email}>" for name, email in authors),
    )
