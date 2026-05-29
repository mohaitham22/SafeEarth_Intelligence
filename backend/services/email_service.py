"""
Email dispatch service — two public functions, both safe to call from BackgroundTasks.

send_verification_email(to, token)
  → smtplib + Jinja2 → templates/emails/verify_email.html
  → dev fallback (SMTP creds absent): prints + writes to .email_dev.log

send_premium_alert_email(to, context) -> str
  → Resend SDK + Jinja2 → templates/emails/premium_alert.html
  → Includes one-click unsubscribe link built from context["unsubscribe_token"]
  → dev fallback (RESEND_API_KEY absent): prints + writes to .email_dev.log
  → returns resend_message_id (or dev-fallback sentinel) for premium_email_logs

Design mirrors Phase-4 "degrade-not-fail":
  Real send attempted only when creds present.
  Fallback never raises — background worker stays alive.
"""
from __future__ import annotations

import logging
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from config import get_settings

logger = logging.getLogger(__name__)

# ── Jinja2 env — loaded once at import time, never per-request ─────────────────
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)

# Dev log file — sits next to backend/ so it is gitignored alongside *.log
_DEV_LOG = Path(__file__).resolve().parent.parent / ".email_dev.log"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _render(template_name: str, context: dict) -> str:
    return _jinja_env.get_template(template_name).render(**context)


def _dev_log(recipient: str, subject: str, html_body: str) -> None:
    """Write a rendered email to the console and .email_dev.log (dev fallback)."""
    sep = "=" * 72
    ts  = datetime.now(timezone.utc).isoformat()
    out = (
        f"\n{sep}\n"
        f"[EMAIL DEV LOG] {ts}\n"
        f"  To:      {recipient}\n"
        f"  Subject: {subject}\n"
        f"--- HTML body (first 1000 chars) ---\n"
        f"{html_body[:1000]}\n"
        f"{sep}\n"
    )
    logger.info(out)
    # Console may be narrow-encoded (cp1252 on Windows) — replace unmappable chars.
    enc = sys.stdout.encoding or "utf-8"
    print(out.encode(enc, errors="replace").decode(enc), flush=True)
    try:
        with open(_DEV_LOG, "a", encoding="utf-8") as fh:
            fh.write(out)
    except OSError:
        pass  # never let a log-write failure crash the background task


# ── Public API ─────────────────────────────────────────────────────────────────

async def send_verification_email(to: str, token: str) -> None:
    """Send an account-verification email.

    Called from the /auth/register endpoint via BackgroundTasks.
    Falls back to dev log when SMTP_USER / SMTP_PASSWORD are empty.
    """
    settings   = get_settings()
    verify_url = f"{settings.frontend_url}/verify-email?token={token}"
    subject    = "Verify your SafeEarth account"

    html_body = _render("verify_email.html", {
        "verify_url":   verify_url,
        "token":        token,
        "frontend_url": settings.frontend_url,
    })

    if not settings.smtp_user or not settings.smtp_password:
        logger.warning(
            "SMTP creds not set — dev-log fallback for verification email to %s", to
        )
        _dev_log(to, subject, html_body)
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = settings.smtp_user
        msg["To"]      = to
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(settings.smtp_user, to, msg.as_string())

        logger.info("Verification email sent via SMTP to %s", to)

    except Exception as exc:
        logger.error(
            "SMTP send failed for %s (%s) — falling back to dev log", to, exc
        )
        _dev_log(to, subject, html_body)


async def send_premium_alert_email(to: str, context: dict) -> str:
    """Send a Premium-tier disaster-alert email via Resend.

    Returns the Resend message_id so the caller can write it to
    premium_email_logs.  Returns a dev-fallback sentinel when RESEND_API_KEY
    is absent or on any send error.

    Required context keys:
      full_name, disaster_type, severity_level, region_name, risk_score,
      unsubscribe_token, message_body (optional)

    The unsubscribe_url and frontend_url are injected here — callers need not
    build them.
    """
    settings = get_settings()

    ctx = dict(context)
    ctx["frontend_url"]    = settings.frontend_url
    ctx["unsubscribe_url"] = (
        f"{settings.frontend_url}/unsubscribe"
        f"?token={ctx.get('unsubscribe_token', '')}"
    )
    ctx.setdefault("message_body", "")
    ctx.setdefault("full_name",    "")
    ctx.setdefault("risk_score",   0)

    disaster_type = ctx.get("disaster_type", "disaster")
    severity      = ctx.get("severity_level", "")
    subject       = f"[SafeEarth Alert] {severity} {disaster_type} risk — take action now"

    html_body = _render("premium_alert.html", ctx)

    if not settings.resend_api_key:
        logger.warning(
            "RESEND_API_KEY not set — dev-log fallback for premium alert to %s", to
        )
        _dev_log(to, subject, html_body)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        return f"dev-fallback-{ts}"

    try:
        resend.api_key = settings.resend_api_key
        params: resend.Emails.SendParams = {
            "from":    settings.resend_from_email,
            "to":      [to],
            "subject": subject,
            "html":    html_body,
        }
        response   = resend.Emails.send(params)
        message_id = getattr(response, "id", None) or (
            response.get("id", "") if isinstance(response, dict) else ""
        )
        logger.info(
            "Premium alert email sent via Resend to %s, message_id=%s", to, message_id
        )
        return message_id

    except Exception as exc:
        logger.error(
            "Resend send failed for %s (%s) — falling back to dev log", to, exc
        )
        _dev_log(to, subject, html_body)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        return f"dev-fallback-error-{ts}"
