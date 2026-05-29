"""
Unit tests for email_service (Phase 6).

All tests are pure unit tests — no DB, no ASGI client, no network.
  send_verification_email — SMTP path (mocked) + dev-fallback when creds absent
  send_premium_alert_email — Resend path (mocked) + dev-fallback when key absent
  Template rendering — jinja2 renders both HTML templates without errors
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import email_service


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_settings(**overrides):
    """Return a mock settings object with sensible defaults."""
    s = MagicMock()
    s.smtp_host         = "smtp.gmail.com"
    s.smtp_port         = 587
    s.smtp_user         = ""
    s.smtp_password     = ""
    s.resend_api_key    = ""
    s.resend_from_email = "alerts@safeearth.tech"
    s.frontend_url      = "http://localhost:3000"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


ALERT_CONTEXT = {
    "full_name":         "Mia Test",
    "disaster_type":     "Flood",
    "severity_level":    "Critical",
    "region_name":       "Cairo",
    "risk_score":        85.0,
    "unsubscribe_token": "tok-abc123",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. send_verification_email — dev-log fallback when SMTP creds absent
# ─────────────────────────────────────────────────────────────────────────────

async def test_send_verification_email_dev_fallback_no_error():
    """Falls back to dev log silently when SMTP_USER is empty — must not raise."""
    settings = _make_settings(smtp_user="", smtp_password="")
    with patch("services.email_service.get_settings", return_value=settings):
        # Should complete without raising
        await email_service.send_verification_email("user@example.com", "tok-xyz")


# ─────────────────────────────────────────────────────────────────────────────
# 2. send_verification_email — SMTP path called when creds present
# ─────────────────────────────────────────────────────────────────────────────

async def test_send_verification_email_smtp_called_when_creds_present():
    settings = _make_settings(smtp_user="u@gmail.com", smtp_password="secret")
    mock_smtp_cls = MagicMock()
    mock_smtp_instance = mock_smtp_cls.return_value.__enter__.return_value

    with (
        patch("services.email_service.get_settings", return_value=settings),
        patch("services.email_service.smtplib.SMTP", mock_smtp_cls),
    ):
        await email_service.send_verification_email("user@example.com", "tok-xyz")

    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("u@gmail.com", "secret")
    mock_smtp_instance.sendmail.assert_called_once()
    args = mock_smtp_instance.sendmail.call_args[0]
    assert args[1] == "user@example.com"  # recipient


# ─────────────────────────────────────────────────────────────────────────────
# 3. send_verification_email — SMTP error → dev-log fallback, no raise
# ─────────────────────────────────────────────────────────────────────────────

async def test_send_verification_email_smtp_error_falls_back():
    settings = _make_settings(smtp_user="u@gmail.com", smtp_password="secret")
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__.side_effect = Exception("connection refused")

    with (
        patch("services.email_service.get_settings", return_value=settings),
        patch("services.email_service.smtplib.SMTP", mock_smtp_cls),
    ):
        # Should NOT raise even though SMTP raised
        await email_service.send_verification_email("user@example.com", "tok-xyz")


# ─────────────────────────────────────────────────────────────────────────────
# 4. send_premium_alert_email — dev-fallback returns sentinel when key absent
# ─────────────────────────────────────────────────────────────────────────────

async def test_send_premium_alert_email_dev_fallback_returns_sentinel():
    settings = _make_settings(resend_api_key="")
    with patch("services.email_service.get_settings", return_value=settings):
        result = await email_service.send_premium_alert_email(
            "prem@example.com", ALERT_CONTEXT
        )
    assert result.startswith("dev-fallback-")


# ─────────────────────────────────────────────────────────────────────────────
# 5. send_premium_alert_email — Resend called and message_id returned
# ─────────────────────────────────────────────────────────────────────────────

async def test_send_premium_alert_email_resend_called():
    settings = _make_settings(resend_api_key="re_live_key_abc")
    mock_response = MagicMock()
    mock_response.id = "resend-msg-001"

    with (
        patch("services.email_service.get_settings", return_value=settings),
        patch("services.email_service.resend.Emails.send", return_value=mock_response),
    ):
        result = await email_service.send_premium_alert_email(
            "prem@example.com", ALERT_CONTEXT
        )

    assert result == "resend-msg-001"


# ─────────────────────────────────────────────────────────────────────────────
# 6. send_premium_alert_email — Resend SDK error → dev-fallback, no raise
# ─────────────────────────────────────────────────────────────────────────────

async def test_send_premium_alert_email_resend_error_falls_back():
    settings = _make_settings(resend_api_key="re_live_key_abc")
    with (
        patch("services.email_service.get_settings", return_value=settings),
        patch("services.email_service.resend.Emails.send", side_effect=Exception("network")),
    ):
        result = await email_service.send_premium_alert_email(
            "prem@example.com", ALERT_CONTEXT
        )
    assert result.startswith("dev-fallback-error-")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Template rendering — verify_email.html renders without error
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_email_template_renders():
    html = email_service._render("verify_email.html", {
        "verify_url":   "http://localhost:3000/verify-email?token=abc",
        "token":        "abc",
        "frontend_url": "http://localhost:3000",
    })
    assert "Verify" in html
    assert "abc" in html
    assert "SafeEarth" in html


# ─────────────────────────────────────────────────────────────────────────────
# 8. Template rendering — premium_alert.html renders without error
# ─────────────────────────────────────────────────────────────────────────────

def test_premium_alert_template_renders():
    html = email_service._render("premium_alert.html", {
        "full_name":       "Mia",
        "disaster_type":   "Flood",
        "severity_level":  "Critical",
        "region_name":     "Cairo",
        "risk_score":      85.0,
        "message_body":    "Critical flood risk detected.",
        "frontend_url":    "http://localhost:3000",
        "unsubscribe_url": "http://localhost:3000/unsubscribe?token=tok-abc",
    })
    assert "Flood" in html
    assert "Critical" in html
    assert "Cairo" in html
    assert "Mia" in html
    assert "unsubscribe" in html.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 9. Unsubscribe URL is correctly injected
# ─────────────────────────────────────────────────────────────────────────────

async def test_premium_alert_unsubscribe_url_built_correctly():
    settings = _make_settings(
        resend_api_key="",
        frontend_url="http://localhost:3000",
    )
    captured_html: list[str] = []

    original_dev_log = email_service._dev_log

    def _capture_log(recipient, subject, html_body):
        captured_html.append(html_body)
        original_dev_log(recipient, subject, html_body)

    with (
        patch("services.email_service.get_settings", return_value=settings),
        patch("services.email_service._dev_log", side_effect=_capture_log),
    ):
        await email_service.send_premium_alert_email(
            "prem@example.com",
            {**ALERT_CONTEXT, "unsubscribe_token": "tok-XYZ"},
        )

    assert captured_html, "dev log should have been called"
    assert "tok-XYZ" in captured_html[0]
    assert "/unsubscribe" in captured_html[0]


# ─────────────────────────────────────────────────────────────────────────────
# 10. Resend response as dict also works (SDK may return dict in some versions)
# ─────────────────────────────────────────────────────────────────────────────

async def test_send_premium_alert_email_resend_dict_response():
    settings = _make_settings(resend_api_key="re_live_key_abc")
    mock_response = {"id": "resend-msg-dict-002"}  # dict, not object

    with (
        patch("services.email_service.get_settings", return_value=settings),
        patch("services.email_service.resend.Emails.send", return_value=mock_response),
    ):
        result = await email_service.send_premium_alert_email(
            "prem@example.com", ALERT_CONTEXT
        )

    assert result == "resend-msg-dict-002"
