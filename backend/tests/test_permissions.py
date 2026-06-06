"""
Unit tests for the central permission layer (core/permissions.py).

Pure functions — no DB, no client, no network. This is the single source of truth
for role/capability decisions, so the matrix is asserted explicitly here.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.permissions import (
    Feature,
    can,
    meets_role,
    normalize_role,
    subscription_limit,
)
from models.enums import UserRole


def _user(role):
    """Fake user with a .role attribute (accepts a UserRole enum or a plain string)."""
    return SimpleNamespace(role=role)


# ── normalize_role ───────────────────────────────────────────────────────────

def test_normalize_role_none_is_guest():
    assert normalize_role(None) == "guest"


def test_normalize_role_free_aliases_subscriber():
    assert normalize_role("free") == "subscriber"
    assert normalize_role(_user("free")) == "subscriber"


def test_normalize_role_accepts_enum_user_and_string():
    assert normalize_role(_user(UserRole.premium)) == "premium"
    assert normalize_role(UserRole.admin) == "admin"
    assert normalize_role("subscriber") == "subscriber"


# ── meets_role ───────────────────────────────────────────────────────────────

def test_meets_role_rank_ordering():
    assert meets_role(_user(UserRole.admin), "subscriber") is True
    assert meets_role(_user(UserRole.subscriber), "premium") is False
    assert meets_role(None, "subscriber") is False
    assert meets_role(_user(UserRole.premium), "premium") is True


def test_meets_role_free_equals_subscriber():
    assert meets_role(_user("free"), "subscriber") is True
    assert meets_role(_user("free"), "premium") is False


# ── can() — the full feature matrix ──────────────────────────────────────────

@pytest.mark.parametrize(
    "role, feature, expected",
    [
        # Guest (None) can do none of the gated features.
        (None, Feature.RUN_PREDICTION, False),
        (None, Feature.MANAGE_USERS, False),
        # Subscriber: prediction/subscribe/checkout yes; email alerts/PDF/admin no.
        (UserRole.subscriber, Feature.RUN_PREDICTION, True),
        (UserRole.subscriber, Feature.SUBSCRIBE_REGION, True),
        (UserRole.subscriber, Feature.START_CHECKOUT, True),
        (UserRole.subscriber, Feature.RECEIVE_EMAIL_ALERTS, False),
        (UserRole.subscriber, Feature.DOWNLOAD_PDF, False),
        (UserRole.subscriber, Feature.DISPATCH_ALERTS, False),
        # Premium: adds email alerts + PDF; still not admin.
        (UserRole.premium, Feature.RECEIVE_EMAIL_ALERTS, True),
        (UserRole.premium, Feature.DOWNLOAD_PDF, True),
        (UserRole.premium, Feature.MANAGE_USERS, False),
        # Admin: everything.
        (UserRole.admin, Feature.RUN_PREDICTION, True),
        (UserRole.admin, Feature.RECEIVE_EMAIL_ALERTS, True),
        (UserRole.admin, Feature.DISPATCH_ALERTS, True),
        (UserRole.admin, Feature.MANAGE_USERS, True),
    ],
)
def test_can_matrix(role, feature, expected):
    user = None if role is None else _user(role)
    assert can(user, feature) is expected


def test_free_behaves_exactly_like_subscriber():
    """The decisive alias check — every feature decision matches subscriber."""
    free = _user("free")
    sub = _user(UserRole.subscriber)
    for feature in Feature:
        assert can(free, feature) == can(sub, feature)


# ── subscription_limit ───────────────────────────────────────────────────────

def test_subscription_limit_by_role():
    assert subscription_limit(UserRole.subscriber) == 8
    assert subscription_limit("free") == 8           # alias
    assert subscription_limit(UserRole.premium) > 8
    assert subscription_limit(UserRole.admin) > 8
    assert subscription_limit(None) == 0             # guest
