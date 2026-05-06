"""Referrals table (Sprint 2.4.B).

Хранит реферальные связи между игроками (ГДД §13.1) — по одной записи
на приглашённого игрока (`referred_id` UNIQUE). Used by:

* `IReferralRepository.add(...)` — создание связи при `/start ref_<id>`
  в Спринте 2.4.D.
* `IReferralRepository.get_by_referred_id(...)` — lookup для использования
  use-case-ом `GrantReferralSignupBonus` (Спринт 2.4.C) и
  `GrantReferralThicknessMilestone` (Спринт 2.4.C).
* `IReferralRepository.mark_signup_granted(...)` — идемпотентный апдейт
  колонки `signup_granted_at` после успешного начисления +5/+1 см.
* `IReferralRepository.mark_milestone_granted(...)` — идемпотентный
  апдейт колонки `last_milestone_thickness` после начисления +10/+30 см
  по достижению толщины 3/5 рефнутым игроком.

CHECK-инварианты на уровне БД (last-line-of-defense):

* `referrer_id <> referred_id` — само-реферал запрещён доменом и БД.
* `last_milestone_thickness >= 0` — отрицательных milestone-ов не бывает.

UNIQUE на `referred_id` гарантирует «один игрок = одна реферальная
запись»: повторная попытка использовать `start=ref_<X>` после уже
прошедшей регистрации с другим `start=ref_<Y>` будет тихо отброшена
БД-ой через `IntegrityError`, который репозиторий конвертирует в
`ReferralAlreadyExistsError`.

FK:

* `referrer_id → users.id ON DELETE CASCADE` — при удалении реферера
  историческая запись о пригласённом теряет смысл (бонус-длина уже
  начислена и зафиксирована в `audit_log`, реферальная схема
  рассчитана только на «живых» рефереров).
* `referred_id → users.id ON DELETE CASCADE` — то же для приглашённого.

Index `(referrer_id, created_at DESC, id DESC)` нужен для запроса
«последние N рефералов реферера» / еженедельных итогов (ГДД §13.3 /
Спринт 2.4.F).

Revision ID: 0015_referrals
Revises: 0014_audit_source_daily_head
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_referrals"
down_revision: str | Sequence[str] | None = "0014_audit_source_daily_head"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("referrer_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signup_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_milestone_thickness",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_referrals"),
        sa.ForeignKeyConstraint(
            ["referrer_id"],
            ["users.id"],
            name="fk_referrals_referrer_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["referred_id"],
            ["users.id"],
            name="fk_referrals_referred_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "referrer_id <> referred_id",
            name="ck_referrals_no_self_referral",
        ),
        sa.CheckConstraint(
            "last_milestone_thickness >= 0",
            name="ck_referrals_milestone_non_negative",
        ),
    )
    # Один игрок = одна реферальная запись. Last-line-of-defense
    # против гонки «два start=ref_<X>+ref_<Y> одновременно» — БД
    # отбрасывает второй INSERT, репозиторий конвертирует
    # IntegrityError в ReferralAlreadyExistsError.
    op.create_index(
        "uq_referrals_referred_id",
        "referrals",
        ["referred_id"],
        unique=True,
    )
    # «Последние N рефералов реферера» — нужно для еженедельных
    # итогов клана (ГДД §13.3, Спринт 2.4.F) и для будущих
    # инсайтов «сколько успешных рефералов у X».
    op.create_index(
        "ix_referrals_referrer_id_created_at_id",
        "referrals",
        [
            "referrer_id",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_referrals_referrer_id_created_at_id", table_name="referrals")
    op.drop_index("uq_referrals_referred_id", table_name="referrals")
    op.drop_table("referrals")
