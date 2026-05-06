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
from dataclasses import dataclass
from datetime import datetime


class AdminAuditAction(str, enum.Enum):
    """Категории админ-аудит-событий.

    Перечень закрытый, новые значения добавляются вместе с новыми
    use-case-ами (2.5-B/C/D). Категории намеренно крупнее, чем имена
    конкретных команд — `reason` хранит человекочитаемый текст.
    """

    # ── Спринт 2.5-A (каркас) ──
    # Использования пока нет — категории нужны, чтобы integration-тесты
    # `IAdminAuditLogger` могли вставить хотя бы одну валидную запись
    # без ожидания закрытия 2.5-B/C/D. Категории будут переиспользованы
    # в следующих PR-ах спринта 2.5.
    ADMIN_CONFIRM_REQUESTED = "admin_confirm_requested"
    ADMIN_CONFIRM_VERIFIED = "admin_confirm_verified"
    ADMIN_CONFIRM_FAILED = "admin_confirm_failed"


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


__all__ = [
    "AdminAuditAction",
    "AdminAuditEntry",
    "AdminAuditSource",
    "IAdminAuditLogger",
]
