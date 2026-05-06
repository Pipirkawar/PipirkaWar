"""Юнит-тесты VO `Referral` (Спринт 2.4.A).

Покрывают:
- happy-path: построение со всеми обязательными и optional-полями;
- инварианты `__post_init__` (positive id-ы, не само-реферал,
  timezone-aware datetime-ы, неотрицательный milestone-thickness);
- frozen-семантику (нельзя мутировать поля);
- `id=None` валиден (запись до `add()`-а в репозитории);
- `signup_granted_at=None` валиден (бонус ещё не выдан).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.referral import Referral, SelfReferralError

_NOW = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)


class TestReferralConstruction:
    """Happy-path и optional-поля."""

    def test_minimal_construction(self) -> None:
        ref = Referral(id=None, referrer_id=1, referred_id=2, created_at=_NOW)
        assert ref.id is None
        assert ref.referrer_id == 1
        assert ref.referred_id == 2
        assert ref.created_at == _NOW
        assert ref.signup_granted_at is None
        assert ref.last_milestone_thickness == 0

    def test_construction_with_all_fields(self) -> None:
        granted_at = datetime(2026, 5, 6, 12, 5, 0, tzinfo=UTC)
        ref = Referral(
            id=42,
            referrer_id=10,
            referred_id=20,
            created_at=_NOW,
            signup_granted_at=granted_at,
            last_milestone_thickness=3,
        )
        assert ref.id == 42
        assert ref.signup_granted_at == granted_at
        assert ref.last_milestone_thickness == 3


class TestReferralInvariants:
    """Инварианты `__post_init__`."""

    def test_id_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="Referral.id must be positive"):
            Referral(id=0, referrer_id=1, referred_id=2, created_at=_NOW)

    def test_id_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="Referral.id must be positive"):
            Referral(id=-1, referrer_id=1, referred_id=2, created_at=_NOW)

    def test_referrer_id_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="referrer_id must be positive"):
            Referral(id=None, referrer_id=0, referred_id=2, created_at=_NOW)

    def test_referrer_id_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="referrer_id must be positive"):
            Referral(id=None, referrer_id=-5, referred_id=2, created_at=_NOW)

    def test_referred_id_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="referred_id must be positive"):
            Referral(id=None, referrer_id=1, referred_id=0, created_at=_NOW)

    def test_self_referral_rejected(self) -> None:
        with pytest.raises(SelfReferralError) as exc_info:
            Referral(id=None, referrer_id=7, referred_id=7, created_at=_NOW)
        assert exc_info.value.player_id == 7

    def test_naive_created_at_rejected(self) -> None:
        naive = datetime(2026, 5, 6, 12, 0, 0)
        with pytest.raises(ValueError, match="created_at must be timezone-aware"):
            Referral(id=None, referrer_id=1, referred_id=2, created_at=naive)

    def test_naive_signup_granted_at_rejected(self) -> None:
        naive = datetime(2026, 5, 6, 12, 0, 0)
        with pytest.raises(ValueError, match="signup_granted_at must be timezone-aware"):
            Referral(
                id=None,
                referrer_id=1,
                referred_id=2,
                created_at=_NOW,
                signup_granted_at=naive,
            )

    def test_negative_milestone_thickness_rejected(self) -> None:
        with pytest.raises(ValueError, match="last_milestone_thickness must be >= 0"):
            Referral(
                id=None,
                referrer_id=1,
                referred_id=2,
                created_at=_NOW,
                last_milestone_thickness=-1,
            )

    def test_zero_milestone_thickness_ok(self) -> None:
        ref = Referral(
            id=None,
            referrer_id=1,
            referred_id=2,
            created_at=_NOW,
            last_milestone_thickness=0,
        )
        assert ref.last_milestone_thickness == 0


class TestReferralFrozen:
    """Frozen-семантика — `Referral` нельзя мутировать."""

    def test_cannot_mutate_referrer_id(self) -> None:
        ref = Referral(id=None, referrer_id=1, referred_id=2, created_at=_NOW)
        with pytest.raises(FrozenInstanceError):
            ref.referrer_id = 999  # type: ignore[misc]

    def test_cannot_mutate_signup_granted_at(self) -> None:
        ref = Referral(id=None, referrer_id=1, referred_id=2, created_at=_NOW)
        with pytest.raises(FrozenInstanceError):
            ref.signup_granted_at = _NOW  # type: ignore[misc]

    def test_cannot_mutate_last_milestone_thickness(self) -> None:
        ref = Referral(id=None, referrer_id=1, referred_id=2, created_at=_NOW)
        with pytest.raises(FrozenInstanceError):
            ref.last_milestone_thickness = 5  # type: ignore[misc]
