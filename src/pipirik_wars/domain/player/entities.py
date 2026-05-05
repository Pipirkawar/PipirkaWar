"""Сущность `Player` — игрок Пипирик Варс (Спринт 1.1, ГДД §2).

Агрегат `Player` иммутабельный (frozen-датакласс). Все мутации —
методы, возвращающие *новый* инстанс с обновлёнными полями. Это
гарантирует, что use-case не сможет частично применить изменение,
наполовину перезаписав поле объекта, который ещё лежит в каком-нибудь
кэше или audit-buffer-е. Старая ссылка остаётся валидной.

Поля, проставляемые БД:
- `id` (`int | None`) — `None` до первого `INSERT`, потом — Postgres serial.
- `created_at`, `updated_at` — `datetime` в UTC. UoW обязан передавать
  «текущее время» из `IClock`, чтобы тесты не зависели от системных часов.

Поля, проставляемые при регистрации (см. ГДД §1.1):
- `tg_id` — стабильный идентификатор Telegram-юзера (ключ снаружи).
- `username` — текущая `@username` пользователя; `None`, если не задан.
- `length` = 2 см, `thickness` = 1 (стартовые значения, ГДД §1.1).
- `title` = `None`, `name` = `None` (титул выдаётся в первом лесу,
  имя — выбивается дропом, ГДД §2.4 / §2.5).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from datetime import datetime

from pipirik_wars.domain.player.errors import PlayerFrozenError
from pipirik_wars.domain.player.value_objects import (
    Length,
    PlayerName,
    Thickness,
    Title,
    Username,
)


class PlayerStatus(str, enum.Enum):
    """Статус игрока (ГДД §1.5 / Спринт 1.1.6).

    `ACTIVE` — играет нормально.
    `FROZEN` — данные сохранены, но играть нельзя (бот удалён из чата
        клана / админ заморозил вручную). При этом сами данные не
        теряются — игрока можно «разморозить» обратно.
    """

    ACTIVE = "active"
    FROZEN = "frozen"


# Стартовые значения регистрации (ГДД §1.1, закрыто Q1/Q2/Q3 в ГДД v8).
_INITIAL_LENGTH_CM: int = 2
_INITIAL_THICKNESS_LEVEL: int = 1


@dataclass(frozen=True, slots=True)
class Player:
    """Игрок (Telegram-пользователь, прошедший RegisterPlayer)."""

    id: int | None
    tg_id: int
    username: Username | None
    length: Length
    thickness: Thickness
    title: Title | None
    name: PlayerName | None
    status: PlayerStatus
    created_at: datetime
    updated_at: datetime
    locale_override: str | None = None
    # ── Спринт 1.6.A (anti-cheat hardcap, ГДД §3.3) ──
    # NULL = бан не активен. Конкретный datetime = soft-ban до этой точки.
    # Всегда timezone-aware (UTC). Гейт `AnticheatGuard` сравнивает
    # с `IClock.now()` — см. `is_anticheat_banned`.
    anticheat_ban_until: datetime | None = None

    @classmethod
    def new(
        cls,
        *,
        tg_id: int,
        username: Username | None,
        now: datetime,
    ) -> Player:
        """Свежезарегистрированный игрок (стартовое состояние ГДД §1.1)."""
        return cls(
            id=None,
            tg_id=tg_id,
            username=username,
            length=Length(cm=_INITIAL_LENGTH_CM),
            thickness=Thickness(level=_INITIAL_THICKNESS_LEVEL),
            title=None,
            name=None,
            status=PlayerStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            anticheat_ban_until=None,
        )

    @property
    def is_frozen(self) -> bool:
        return self.status is PlayerStatus.FROZEN

    def _ensure_active(self) -> None:
        if self.is_frozen:
            raise PlayerFrozenError(tg_id=self.tg_id)

    # ------- мутаторы (возвращают новый инстанс) -------

    def with_username(self, username: Username | None, *, now: datetime) -> Player:
        """Обновить текущий `@username` (Telegram позволяет менять)."""
        self._ensure_active()
        if username == self.username:
            return self
        return replace(self, username=username, updated_at=now)

    def with_length(self, length: Length, *, now: datetime) -> Player:
        """Установить новую длину (вызывается из RewardLength / GrantLength)."""
        self._ensure_active()
        return replace(self, length=length, updated_at=now)

    def with_thickness(self, thickness: Thickness, *, now: datetime) -> Player:
        """Установить новый уровень толщины (вызывается из UpgradeThickness)."""
        self._ensure_active()
        return replace(self, thickness=thickness, updated_at=now)

    def with_title(self, title: Title, *, now: datetime) -> Player:
        """Выдать титул. Идемпотентность повторной выдачи —
        ответственность use-case (см. Спринт 1.3.8 «первый лес»).
        """
        self._ensure_active()
        return replace(self, title=title, updated_at=now)

    def with_name(self, name: PlayerName, *, now: datetime) -> Player:
        """Установить новое имя (выбито в лесу). Старое перезаписывается."""
        self._ensure_active()
        return replace(self, name=name, updated_at=now)

    def without_name(self, *, now: datetime) -> Player:
        """Сбросить имя (выбросил предмет «Имя» из инвентаря)."""
        self._ensure_active()
        if self.name is None:
            return self
        return replace(self, name=None, updated_at=now)

    def freeze(self, *, now: datetime) -> Player:
        """Заморозить игрока. Идемпотентно: повторная заморозка — no-op."""
        if self.is_frozen:
            return self
        return replace(self, status=PlayerStatus.FROZEN, updated_at=now)

    def unfreeze(self, *, now: datetime) -> Player:
        """Разморозить игрока. Идемпотентно: уже активный — no-op."""
        if self.status is PlayerStatus.ACTIVE:
            return self
        return replace(self, status=PlayerStatus.ACTIVE, updated_at=now)

    def with_locale_override(self, locale_override: str | None, *, now: datetime) -> Player:
        """Переписать явный выбор языка игрока (Спринт 1.5.F, `/lang`).

        `None` — сбросить override и вернуться к `tg.language_code → DEFAULT`.
        Идемпотентно: если значение не меняется, возвращаем тот же инстанс (без буманого UPDATE-а).
        Допускается и для frozen-игроков: выбор языка — это интерфейсная настройка,
        а не игровое действие (они всё равно получают сообщение «аккаунт заморожен»).
        """
        if locale_override == self.locale_override:
            return self
        return replace(self, locale_override=locale_override, updated_at=now)

    # ── Anti-cheat (Спринт 1.6.A) ──

    def is_anticheat_banned(self, *, now: datetime) -> bool:
        """`True`, если игрок в активном soft-ban-е на момент `now`.

        Отдельный метод (а не свойство) — чтобы вызывающий явно передавал
        текущее время через `IClock.now()`. В domain недопустимы прямые
        обращения к системным часам.
        """
        if self.anticheat_ban_until is None:
            return False
        return now < self.anticheat_ban_until

    def with_anticheat_ban(self, *, until: datetime, now: datetime) -> Player:
        """Поставить или продлить soft-ban до `until` (UTC, timezone-aware).

        Trip-wire (Спринт 1.6.D) вызывает этот метод, когда rolling-сумма
        organic-длины превысила daily/weekly cap. Если уже стоит более
        поздний `until` — оставляем его (продлеваем монотонно вверх).
        Допускается и для frozen-игроков: бан — это сервисное состояние,
        не привязанное к статусу `ACTIVE/FROZEN`.

        `until` обязан быть timezone-aware и в будущем относительно `now`,
        иначе `ValueError`. Это спасает от накопления багов «забанили в
        прошлом» (которые потом не отрабатывают как бан).
        """
        if until.tzinfo is None:
            raise ValueError("anticheat_ban_until must be timezone-aware")
        if until <= now:
            raise ValueError("anticheat_ban_until must be in the future relative to now")
        if self.anticheat_ban_until is not None and until <= self.anticheat_ban_until:
            return self
        return replace(self, anticheat_ban_until=until, updated_at=now)

    def with_anticheat_ban_lifted(self, *, now: datetime) -> Player:
        """Снять soft-ban (используется в `/anticheat_unban`, Спринт 1.6.G).

        Идемпотентно: если бан и так снят — возвращаем тот же инстанс,
        не дёргая UPDATE и не пишем audit-no-op.
        """
        if self.anticheat_ban_until is None:
            return self
        return replace(self, anticheat_ban_until=None, updated_at=now)
