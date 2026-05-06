"""Application use-cases реферальной системы (ГДД §13.1, Спринт 2.4.C)."""

from pipirik_wars.application.referral.grant_signup_bonus import (
    GrantReferralSignupBonus,
    ReferralSignupBonusGranted,
)
from pipirik_wars.application.referral.grant_thickness_milestone import (
    GrantReferralThicknessMilestone,
    GrantReferralThicknessMilestoneResult,
    ReferralMilestoneGranted,
    ReferralMilestoneNotApplicable,
)
from pipirik_wars.application.referral.register import (
    ReferralAlreadyRegistered,
    ReferralRegistered,
    RegisterReferral,
    RegisterReferralResult,
)

__all__ = [
    "GrantReferralSignupBonus",
    "GrantReferralThicknessMilestone",
    "GrantReferralThicknessMilestoneResult",
    "ReferralAlreadyRegistered",
    "ReferralMilestoneGranted",
    "ReferralMilestoneNotApplicable",
    "ReferralRegistered",
    "ReferralSignupBonusGranted",
    "RegisterReferral",
    "RegisterReferralResult",
]
