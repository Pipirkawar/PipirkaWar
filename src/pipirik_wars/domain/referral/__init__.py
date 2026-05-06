"""Доменный слой реферальной системы (ГДД §13.1, Спринт 2.4.A)."""

from pipirik_wars.domain.referral.entities import Referral, WeeklyClanReferralEntry
from pipirik_wars.domain.referral.errors import (
    MilestoneAlreadyGrantedError,
    ReferralAlreadyExistsError,
    ReferralError,
    ReferralRateLimitedError,
    ReferrerNotRegisteredError,
    SelfReferralError,
    SignupBonusAlreadyGrantedError,
)
from pipirik_wars.domain.referral.repositories import IReferralRepository

__all__ = [
    "IReferralRepository",
    "MilestoneAlreadyGrantedError",
    "Referral",
    "ReferralAlreadyExistsError",
    "ReferralError",
    "ReferralRateLimitedError",
    "ReferrerNotRegisteredError",
    "SelfReferralError",
    "SignupBonusAlreadyGrantedError",
    "WeeklyClanReferralEntry",
]
