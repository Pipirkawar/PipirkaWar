"""Аудит-лог админских мутаций (Спринт 2.5-A.1).

Отдельная таблица `admin_audit_log` (ГДД §18.6, ГДД §18.6.4) — у общего
`audit_log` нет обязательного `admin_id` и контекста команды (`tg_chat_id`,
`ip`, `source`), плюс /audit-листинг по админу будет частым и должен
ходить по узкому индексу. Запись делается **в той же транзакции**, что
и сама админ-мутация — это гарантирует, что «тихих» админ-действий не
бывает.

Поля `AdminAuditEntry`:

- `admin_id` — внутренний `Admin.id` (NOT `tg_id`), стабильный после
  ротации tg-id-ов;
- `action` — высокоуровневая категория (`AdminAuditAction`);
- `target_kind` / `target_id` — на что влияет мутация (например,
  `("player", "123")` или `("balance_key", "forest_run_base_reward_cm")`);
- `before` / `after` — JSON-снимки до/после (могут быть `None` для
  read-only-команд или для безопасных no-op-ов);
- `reason` — обязательный человекочитаемый комментарий админа;
- `idempotency_key` — для команд с TOTP (одна команда = один ключ);
- `source` — `bot` (Telegram) либо `web` (Спринт 4.5);
- `tg_chat_id` — id чата, в котором админ выполнил команду (только
  для `source=bot`);
- `ip` — IP-адрес запроса (только для `source=web`);
- `occurred_at` — timestamp (UTC, через `IClock`).

Whitelist `AdminAuditSource` дублируется в БД-CHECK-инвариант — это
last-line-of-defense против опечаток, по аналогии с `audit_log.source`.

Whitelist `AdminAuditAction` — закрытый перечень категорий админ-команд.
Расширяется по мере добавления новых команд (2.5-B / 2.5-C / 2.5-D).
"""

from __future__ import annotations

import abc
import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


class AdminAuditAction(str, enum.Enum):
    """Категории админ-аудит-событий.

    Перечень закрытый, новые значения добавляются вместе с новыми
    use-case-ами (2.5-B/C/D). Категории намеренно крупнее, чем имена
    конкретных команд — `reason` хранит человекочитаемый текст.
    """

    # ── Спринт 2.5-A (каркас) ──
    # Категории TOTP-подтверждения опасных команд. Применяются `RequestAdminConfirm` /
    # `VerifyAdminConfirm` независимо от конкретной команды (`ban`, `grant_*`, ...).
    ADMIN_CONFIRM_REQUESTED = "admin_confirm_requested"
    ADMIN_CONFIRM_VERIFIED = "admin_confirm_verified"
    ADMIN_CONFIRM_FAILED = "admin_confirm_failed"

    # ── Спринт 2.5-B (команды поддержки) ──
    # Read-side lookup: `/find_player`, `/player`. Пишем even-on-read,
    # чтобы super-admin в `/audit` видел, кто и кого «пробивал».
    ADMIN_PLAYER_LOOKUP = "admin_player_lookup"
    # Write-side, обратимые мутации (без TOTP).
    ADMIN_PLAYER_FROZEN = "admin_player_frozen"
    ADMIN_PLAYER_UNFROZEN = "admin_player_unfrozen"
    # Write-side, необратимый бан после успешной TOTP-проверки.
    ADMIN_PLAYER_BANNED = "admin_player_banned"
    # TOTP-подтверждение `/ban` провалилось (неверный код / просрочен и т.п.) —
    # сама `ConfirmAdminMismatchError` / `ConfirmCodeInvalidError` уже пишет
    # `ADMIN_CONFIRM_FAILED`, а `ADMIN_BAN_BLOCKED` маркирует, что именно
    # бан игрока не был выполнен (handler-у нужно понять, что он не должен
    # звать `BanPlayer.execute()`).
    ADMIN_BAN_BLOCKED = "admin_ban_blocked"

    # ── Спринт 2.5-C (команды экономики) ──
    # Write-side: ручной грант / отзыв длины (TOTP-обязательная). Положительная
    # дельта проходит через `AddLength` с `AuditSource.ADMIN_GRANT`, отрицательная —
    # с `AuditSource.ADMIN_REFUND`; обе попадают в anti-cheat rolling-окно
    # (ГДД §6 / table «положительные `LENGTH_DELTA`»).
    ADMIN_GRANT_LENGTH = "admin_grant_length"
    # Write-side: установка нового уровня толщины (TOTP-обязательная). НЕ дельта,
    # а абсолютное значение (ГДД §16). Не попадает в anti-cheat-окно (длина и
    # толщина — разные оси прогрессии, ГДД §3.2).
    ADMIN_GRANT_THICKNESS = "admin_grant_thickness"
    # Read-side чтение балансового ключа (`/balance_get`). Логируется по аналогии
    # с `ADMIN_PLAYER_LOOKUP` — super-admin в `/audit` должен видеть, кто
    # пробивал балансовые константы (ГДД §18.6.4).
    ADMIN_BALANCE_GET = "admin_balance_get"
    # Write-side: правка балансового ключа в `config/balance.yaml` (TOTP-обязательная).
    # Audit пишется ДО `IBalanceReloader.reload()` — иначе при сбое reload-а
    # мы бы потеряли запись о попытке. Откат YAML-файла при сбое reload-а — на
    # стороне `IBalanceWriter`-а (записывает atomic `tmp + os.replace`).
    ADMIN_BALANCE_SET = "admin_balance_set"

    # ── Спринт 2.5-D (read-side: /audit) ──
    # Read-side листинг `admin_audit_log`-а (`/audit`). Запись пишется
    # каждый раз, когда любой админ читает аудит-лог: super-admin должен
    # видеть, кто и какой срез аудита смотрел (ГДД §18.6.4).
    ADMIN_AUDIT_QUERIED = "admin_audit_queried"

    # ── Спринт 2.5-D (команды поддержки кланов) ──
    # Read-side lookup карточки клана (`/clan`, `/clan_daily_head_history`).
    # Пишем по аналогии с `ADMIN_PLAYER_LOOKUP` — каждая «пробивка» клана
    # тоже видна в `/audit`.
    ADMIN_CLAN_LOOKUP = "admin_clan_lookup"


class AdminAuditSource(str, enum.Enum):
    """Источник админ-команды.

    На текущей фазе допустимы только `BOT` (Telegram) и `WEB`
    (опциональная панель из Спринта 4.5). Если появится третий канал
    (например, CLI для оператора), он добавляется здесь и в БД-CHECK
    одной миграцией.
    """

    BOT = "bot"
    WEB = "web"


@dataclass(frozen=True, slots=True)
class AdminAuditEntry:
    """Одна запись `admin_audit_log`.

    Иммутабельна — UoW сохраняет её атомарно вместе с мутацией. Для
    `source=BOT` валидно только `tg_chat_id`; `ip` остаётся `None` (и
    наоборот — для `WEB` валиден `ip`, а `tg_chat_id` не имеет смысла).
    Дополнительной валидации в домене нет: контекст приходит из
    конкретного канала и заполняется на уровне use-case-а.
    """

    admin_id: int
    action: AdminAuditAction
    target_kind: str
    target_id: str
    before: dict[str, object] | None
    after: dict[str, object] | None
    reason: str
    idempotency_key: str | None
    source: AdminAuditSource
    tg_chat_id: int | None
    ip: str | None
    occurred_at: datetime


class IAdminAuditLogger(abc.ABC):
    """Порт записи в `admin_audit_log`.

    Реализации:

    - `infrastructure.db.services.SqlAlchemyAdminAuditLogger` (production);
    - `tests.fakes.FakeAdminAuditLogger` (in-memory для unit-тестов).

    Запись идёт **внутри** контекста `IUnitOfWork` — отдельная
    транзакция не открывается. Любая ошибка записи откатывает всю
    операцию (ГДД §0: «без аудита операция не считается выполненной»).
    """

    @abc.abstractmethod
    async def record(self, entry: AdminAuditEntry) -> None:
        """Записать одно событие админ-аудит-лога."""


@dataclass(frozen=True, slots=True)
class AdminAuditRecord:
    """Запись `admin_audit_log` для read-side листинга (`/audit`, ГДД §18.6.4).

    В отличие от `AdminAuditEntry` (write-VO), `AdminAuditRecord`
    содержит публичный идентификатор админа — `actor_tg_id` —
    чтобы handler-у `/audit` не приходилось делать второй round-trip
    в `IAdminRepository` для каждой записи. Само сопоставление
    `admin_id ↔ tg_id` делает реализация порта (JOIN с `admins`).

    Дополнительно хранится `id` из БД (PK `admin_audit_log.id`) —
    используется в выдаче для cite-по-номеру и для будущей пагинации.
    """

    id: int
    actor_admin_id: int
    actor_tg_id: int
    action: AdminAuditAction
    target_kind: str
    target_id: str
    before: dict[str, object] | None
    after: dict[str, object] | None
    reason: str
    idempotency_key: str | None
    source: AdminAuditSource
    tg_chat_id: int | None
    ip: str | None
    occurred_at: datetime


class IAdminAuditQuery(abc.ABC):
    """Read-side порт `admin_audit_log` (Спринт 2.5-D.5).

    Отделён от `IAdminAuditLogger` по ISP: `record(...)` нужен внутри
    каждой админ-мутации, `list_recent(...)` — только handler-у `/audit`.
    Реализация (`SqlAlchemyAdminAuditQuery`) делает один SELECT с JOIN
    к `admins`, чтобы handler получил `actor_tg_id` без отдельных
    запросов на каждую строку.

    Запросы исполняются внутри контекста `IUnitOfWork` — отдельная
    транзакция не открывается; результат — упорядочённый по
    `occurred_at DESC` срез последних `limit` записей.
    """

    @abc.abstractmethod
    async def list_recent(
        self,
        *,
        limit: int,
        target_admin_id: int | None = None,
        action: AdminAuditAction | None = None,
    ) -> Sequence[AdminAuditRecord]:
        """Последние `limit` записей админ-аудит-лога с опц. фильтрами.

        Параметры:

        - `limit` — верхняя граница (use-case ограничивает её сверху,
          репо не накладывает свой кап).
        - `target_admin_id` — если задан, только записи этого админа
          (по внутреннему `Admin.id`, не `tg_id`).
        - `action` — если задан, только записи этой категории.

        Сортировка: `occurred_at DESC, id DESC` (свежие — сверху, при
        равенстве timestamp-а ID-ы тоже идут сверху-вниз, чтобы
        результат был детерминированным даже на нашем sub-millisecond
        потоке записи).
        """


__all__ = [
    "AdminAuditAction",
    "AdminAuditEntry",
    "AdminAuditRecord",
    "AdminAuditSource",
    "IAdminAuditLogger",
    "IAdminAuditQuery",
]
