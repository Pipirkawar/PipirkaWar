"""Domain-сущности реферальной системы (ГДД §13.1, ПД §6 / Спринт 2.4).

`Referral` — иммутабельная запись таблицы `referrals`: одна пара
`(referrer_id, referred_id)` уникальна (точнее — `referred_id` уникален,
один игрок может быть рефнут только одним другим). Хранит:

- факт реферирования (всегда актуальный);
- момент успешной выдачи signup-бонуса (`signup_granted_at` — `None`
  до выдачи, идемпотентный флаг для use-case-а
  `GrantReferralSignupBonus`);
- максимальный уже выданный milestone по толщине рефнутого игрока
  (`last_milestone_thickness` — `0`, если ни один milestone не выдан;
  иначе максимальный выданный из `balance.referral.on_thickness_milestones`).

Никаких side-эффектов: запись/обновление в БД, начисление длины
через `progression.add_length(reason="referral_*", source=REFERRAL_*)`,
аудит — это use-cases `RegisterReferral`, `GrantReferralSignupBonus`,
`GrantReferralThicknessMilestone` (Спринт 2.4.C).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.domain.referral.errors import SelfReferralError


@dataclass(frozen=True, slots=True)
class Referral:
    """Запись реферальной связи между двумя игроками.

    Поля:
    - `id` — суррогатный PK (None до `add()`-а в репозитории).
    - `referrer_id` — внутренний `players.id` пригласившего (>= 1).
    - `referred_id` — внутренний `players.id` приглашённого (>= 1).
      UNIQUE на уровне БД (один игрок = одна реферальная запись).
    - `created_at` — UTC-таймстамп создания записи.
    - `signup_granted_at` — UTC-таймстамп выдачи signup-бонуса. `None`,
      пока бонус ещё не выдан (use-case `GrantReferralSignupBonus`
      проверяет это перед начислением).
    - `last_milestone_thickness` — максимальный выданный milestone
      из `balance.referral.on_thickness_milestones` (0 — ни одного).

    Инварианты:
    - все id-ы > 0 (или None для новой записи без PK);
    - `referrer_id != referred_id` (само-реферал → `SelfReferralError`);
    - `created_at.tzinfo is not None` (timezone-aware UTC);
    - `signup_granted_at is None` или `signup_granted_at.tzinfo is not None`;
    - `last_milestone_thickness >= 0`.
    """

    id: int | None
    referrer_id: int
    referred_id: int
    created_at: datetime
    signup_granted_at: datetime | None = None
    last_milestone_thickness: int = 0

    def __post_init__(self) -> None:
        if self.id is not None and self.id <= 0:
            raise ValueError(f"Referral.id must be positive or None, got {self.id}")
        if self.referrer_id <= 0:
            raise ValueError(f"Referral.referrer_id must be positive, got {self.referrer_id}")
        if self.referred_id <= 0:
            raise ValueError(f"Referral.referred_id must be positive, got {self.referred_id}")
        if self.referrer_id == self.referred_id:
            raise SelfReferralError(player_id=self.referrer_id)
        if self.created_at.tzinfo is None:
            raise ValueError("Referral.created_at must be timezone-aware (UTC)")
        if self.signup_granted_at is not None and self.signup_granted_at.tzinfo is None:
            raise ValueError("Referral.signup_granted_at must be timezone-aware (UTC)")
        if self.last_milestone_thickness < 0:
            raise ValueError(
                f"Referral.last_milestone_thickness must be >= 0, "
                f"got {self.last_milestone_thickness}"
            )


@dataclass(frozen=True, slots=True)
class WeeklyClanReferralEntry:
    """Один ряд недельной агрегации рефералов клана (Спринт 2.4.E).

    Используется в `IReferralRepository.weekly_summary_by_clan(...)` —
    группировка по `referrer_id` с подсчётом, сколько новых игроков
    этот реферер привёл за окно `[since, until)` среди членов
    конкретного клана.

    Реферер обязан быть в клане (`clan_members.player_id`). Реферал
    (новый игрок) не обязан вступать в клан — главное, чтобы реферер
    был его членом. Это соответствует ГДД §13.1: «реферальный приз
    идёт пригласившему», а еженедельная карточка показывает рост
    клана через активность его участников.

    Инварианты:
    - `referrer_id > 0` (это `players.id`);
    - `count > 0` (репозиторий не возвращает строки с нулём — отсутствие
      = нет записи; таким образом отсутствие референции в выборке
      означает «никого не пригласил за окно»).
    """

    referrer_id: int
    count: int

    def __post_init__(self) -> None:
        if self.referrer_id <= 0:
            raise ValueError(
                f"WeeklyClanReferralEntry.referrer_id must be positive, got {self.referrer_id}"
            )
        if self.count <= 0:
            raise ValueError(f"WeeklyClanReferralEntry.count must be positive, got {self.count}")


__all__ = ["Referral", "WeeklyClanReferralEntry"]
