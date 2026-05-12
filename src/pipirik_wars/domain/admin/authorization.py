"""RBAC-политика админ-команд (Спринт 2.5-D.8, ГДД §18.6.2).

Каждая admin-команда привязана к одному `AdminCommandKind`. Перед
выполнением use-case проверяет: «может ли роль текущего админа дёргать
эту команду?». Проверку делает `IAdminAuthorizationPolicy` —
доменный порт; реализация по умолчанию (`RoleBasedAdminAuthorizationPolicy`)
держит матрицу `(role × command_kind) → allow/deny` в одном месте,
чтобы при добавлении новой команды не размазывать `if`-ы по всему коду.

Политика — чистая функция: ни I/O, ни обращений в БД. Принимает уже
загруженный `Admin` (из `IAdminRepository.get_by_tg_id`) и константу
`AdminCommandKind`. Возвращает `True/False`. Use-case сам решает, что
делать с отказом (бросить `AdminAuthorizationDeniedError`, записать
`ADMIN_AUTHORIZATION_DENIED` в admin-аудит).

Иерархия ролей (ГДД §18.6.2):

* `READ_ONLY`   — только read-side (lookup-команды, /audit, /balance_get).
* `SUPPORT`     — операционка над игроками/кланами (freeze/unfreeze/ban),
                  плюс всё read-only.
* `ECONOMIST`   — read-side + правки баланса (/grant_*, /balance_set,
                  /balance_reload). Не имеет прав на ban/freeze игроков
                  (это саппорт-функция).
* `SUPER_ADMIN` — всё, включая выдачу/отзыв админов (/admin_setup_totp),
                  снятие anti-cheat бана (/anticheat_unban), broadcast
                  (/announce), runtime-настройки (/set_max_dau).

Whitelist `AdminCommandKind` — закрытый: новые команды добавляются
вместе с матрицей, чтобы случайно не оставить команду «без правила»
(дефолт — fail-closed: команда без правила всегда отказывает).
"""

from __future__ import annotations

import abc
import enum

from pipirik_wars.domain.admin.entities import Admin, AdminRole
from pipirik_wars.shared.errors import DomainError


class AdminCommandKind(str, enum.Enum):
    """Закрытый whitelist команд админ-интерфейса.

    Каждая команда привязана к одному значению; политика смотрит на
    `(admin.role, command_kind)` и решает «можно/нельзя».

    При добавлении новой команды в `bot/handlers/admin_*.py`:
    1. Добавь значение сюда.
    2. Добавь правило в `RoleBasedAdminAuthorizationPolicy._matrix`.
    3. Покрой тестом `tests/unit/domain/admin/test_authorization.py`.
    """

    # ── Read-side lookup (доступно всем активным админам) ──
    FIND_PLAYER = "find_player"
    GET_PLAYER_CARD = "get_player_card"
    GET_CLAN_CARD = "get_clan_card"
    GET_CLAN_DAILY_HEAD_HISTORY = "get_clan_daily_head_history"
    GET_BALANCE_VALUE = "get_balance_value"
    GET_ADMIN_AUDIT_TRAIL = "get_admin_audit_trail"
    ADMIN_STATS = "admin_stats"

    # ── Поддержка (SUPPORT+) ──
    FREEZE_PLAYER = "freeze_player"
    UNFREEZE_PLAYER = "unfreeze_player"
    BAN_PLAYER = "ban_player"
    FREEZE_CLAN = "freeze_clan"
    UNFREEZE_CLAN = "unfreeze_clan"

    # ── Экономика (ECONOMIST+) ──
    GRANT_LENGTH = "grant_length"
    GRANT_THICKNESS = "grant_thickness"
    SET_BALANCE_VALUE = "set_balance_value"
    RELOAD_BALANCE = "reload_balance"

    # ── Только super-admin ──
    LIFT_ANTICHEAT_BAN = "lift_anticheat_ban"
    SET_MAX_DAU = "set_max_dau"
    BROADCAST_ANNOUNCEMENT = "broadcast_announcement"
    SETUP_TOTP = "setup_totp"
    # ---- Prize-pool admin (4.1-E, ГДД §12.6.6) ----
    GET_PRIZE_POOL = "get_prize_pool"
    REFUND_LOT = "refund_lot"
    FREEZE_PAYOUTS = "freeze_payouts"
    UNFREEZE_PAYOUTS = "unfreeze_payouts"

    # ── Инфраструктурные (TOTP-confirm flow, доступно тем, кто и саму команду
    #    может вызвать; политика смотрит на сам confirm-flow как на «можно»
    #    для всех активных админов с настроенным TOTP — фактическая команда
    #    переcпросит авторизацию в момент выполнения после verify). ──
    REQUEST_ADMIN_CONFIRM = "request_admin_confirm"
    VERIFY_ADMIN_CONFIRM = "verify_admin_confirm"


class AdminAuthorizationDeniedError(DomainError):
    """У админа недостаточно прав на запрошенную команду.

    Поднимается use-case-ом ПОСЛЕ записи `ADMIN_AUTHORIZATION_DENIED`
    в `admin_audit_log` — handler ловит её и показывает
    локализованное сообщение «недостаточно прав» (без раскрытия
    структуры RBAC, чтобы не подсказывать, какую роль нужно
    запросить).

    `requirement` — имя команды (строка из `AdminCommandKind`);
    `actor_role` — реальная роль админа на момент попытки;
    `detail` — человекочитаемая фраза для логов / тестов.
    """

    def __init__(
        self,
        *,
        command_kind: AdminCommandKind,
        actor_role: AdminRole,
        detail: str,
    ) -> None:
        super().__init__(
            f"admin authorization denied: command={command_kind.value} "
            f"role={actor_role.value} ({detail})",
        )
        self.command_kind = command_kind
        self.actor_role = actor_role
        self.detail = detail


class IAdminAuthorizationPolicy(abc.ABC):
    """Порт RBAC-политики.

    Реализация — чистая функция, без I/O. Принимает уже загруженный
    `Admin` (use-case держит его после `IAdminRepository.get_by_tg_id`)
    и константу `AdminCommandKind`. Возвращает `True/False`.

    Use-case при `False` обязан:
    1. Записать `ADMIN_AUTHORIZATION_DENIED` в `admin_audit_log`.
    2. Бросить `AdminAuthorizationDeniedError`.

    Прокси-реализации (для тестов/спецификаций) допустимы — главное,
    чтобы не было побочных эффектов.
    """

    @abc.abstractmethod
    def is_authorized(self, admin: Admin, command_kind: AdminCommandKind) -> bool:
        """Может ли `admin` выполнить команду `command_kind`?

        Контракт:

        * Если `admin.is_active is False` — всегда `False` (даже если
          по матрице роль подходит). Реализация может предполагать,
          что use-case уже проверил `is_active` и не зовёт policy для
          неактивных, но fail-closed-проверка тут — last-line-of-defense.
        * Если `command_kind` не покрыт матрицей — `False`. Это
          намеренно: добавление новой команды без правила должно
          сразу отказывать в production, а не «случайно» разрешать.
        """


class RoleBasedAdminAuthorizationPolicy(IAdminAuthorizationPolicy):
    """Реализация по матрице `(role × command_kind) → allow`.

    Матрица собрана как `dict[AdminCommandKind, frozenset[AdminRole]]` —
    в каждой ячейке указаны роли, которым команда разрешена. Команда
    без явного правила всегда отказывает (fail-closed).

    Иерархия не «суперсетная» (super_admin не получает команду
    автоматически — его роль явно перечислена в каждой ячейке, где
    разрешена). Это намеренно: при добавлении новой команды
    разработчик должен явно указать, кому она разрешена, и не
    забыть про super-admin.
    """

    __slots__ = ("_matrix",)

    def __init__(self) -> None:
        self._matrix: dict[AdminCommandKind, frozenset[AdminRole]] = {
            # ── Read-side: все активные админы ──
            AdminCommandKind.FIND_PLAYER: frozenset(AdminRole),
            AdminCommandKind.GET_PLAYER_CARD: frozenset(AdminRole),
            AdminCommandKind.GET_CLAN_CARD: frozenset(AdminRole),
            AdminCommandKind.GET_CLAN_DAILY_HEAD_HISTORY: frozenset(AdminRole),
            AdminCommandKind.GET_BALANCE_VALUE: frozenset(AdminRole),
            AdminCommandKind.GET_ADMIN_AUDIT_TRAIL: frozenset(AdminRole),
            AdminCommandKind.ADMIN_STATS: frozenset(AdminRole),
            # ── Confirm-flow: те, кто в принципе могут дёрнуть мутацию (то есть
            #    все, кроме READ_ONLY). Сама команда после verify ещё раз
            #    проверит, разрешена ли роли её command_kind. ──
            AdminCommandKind.REQUEST_ADMIN_CONFIRM: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.ECONOMIST, AdminRole.SUPPORT},
            ),
            AdminCommandKind.VERIFY_ADMIN_CONFIRM: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.ECONOMIST, AdminRole.SUPPORT},
            ),
            # ── Поддержка (SUPPORT + SUPER_ADMIN) ──
            AdminCommandKind.FREEZE_PLAYER: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.SUPPORT},
            ),
            AdminCommandKind.UNFREEZE_PLAYER: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.SUPPORT},
            ),
            AdminCommandKind.BAN_PLAYER: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.SUPPORT},
            ),
            AdminCommandKind.FREEZE_CLAN: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.SUPPORT},
            ),
            AdminCommandKind.UNFREEZE_CLAN: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.SUPPORT},
            ),
            # ── Экономика (ECONOMIST + SUPER_ADMIN) ──
            AdminCommandKind.GRANT_LENGTH: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.ECONOMIST},
            ),
            AdminCommandKind.GRANT_THICKNESS: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.ECONOMIST},
            ),
            AdminCommandKind.SET_BALANCE_VALUE: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.ECONOMIST},
            ),
            AdminCommandKind.RELOAD_BALANCE: frozenset(
                {AdminRole.SUPER_ADMIN, AdminRole.ECONOMIST},
            ),
            # ── Только super-admin ──
            AdminCommandKind.LIFT_ANTICHEAT_BAN: frozenset({AdminRole.SUPER_ADMIN}),
            AdminCommandKind.SET_MAX_DAU: frozenset({AdminRole.SUPER_ADMIN}),
            AdminCommandKind.BROADCAST_ANNOUNCEMENT: frozenset({AdminRole.SUPER_ADMIN}),
            AdminCommandKind.SETUP_TOTP: frozenset({AdminRole.SUPER_ADMIN}),
            AdminCommandKind.GET_PRIZE_POOL: frozenset({AdminRole.SUPER_ADMIN}),
            AdminCommandKind.REFUND_LOT: frozenset({AdminRole.SUPER_ADMIN}),
            AdminCommandKind.FREEZE_PAYOUTS: frozenset({AdminRole.SUPER_ADMIN}),
            AdminCommandKind.UNFREEZE_PAYOUTS: frozenset({AdminRole.SUPER_ADMIN}),
        }

    def is_authorized(self, admin: Admin, command_kind: AdminCommandKind) -> bool:
        if not admin.is_active:
            return False
        allowed_roles = self._matrix.get(command_kind)
        if allowed_roles is None:
            # fail-closed: команда без явного правила всегда отказывает.
            return False
        return admin.role in allowed_roles


__all__ = [
    "AdminAuthorizationDeniedError",
    "AdminCommandKind",
    "IAdminAuthorizationPolicy",
    "RoleBasedAdminAuthorizationPolicy",
]
