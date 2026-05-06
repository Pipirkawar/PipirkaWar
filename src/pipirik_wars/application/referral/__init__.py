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
from pipirik_wars.application.referral.run_weekly_clan_summary import (
    TOP_LIMIT,
    WEEKLY_WINDOW,
    RunWeeklyClanReferralSummary,
)
from pipirik_wars.application.referral.weekly_summary_dto import (
    WeeklyClanReferralEntryDTO,
    WeeklyClanReferralSummary,
)
from pipirik_wars.application.referral.weekly_summary_notifier import (
    IWeeklyClanReferralSummaryNotifier,
)

__all__ = [
    "TOP_LIMIT",
    "WEEKLY_WINDOW",
    "GrantReferralSignupBonus",
    "GrantReferralThicknessMilestone",
    "GrantReferralThicknessMilestoneResult",
    "IWeeklyClanReferralSummaryNotifier",
    "ReferralAlreadyRegistered",
    "ReferralMilestoneGranted",
    "ReferralMilestoneNotApplicable",
    "ReferralRegistered",
    "ReferralSignupBonusGranted",
    "RegisterReferral",
    "RegisterReferralResult",
    "RunWeeklyClanReferralSummary",
    "WeeklyClanReferralEntryDTO",
    "WeeklyClanReferralSummary",
]
