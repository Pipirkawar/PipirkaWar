"""Domain-ошибки каравана (Спринт 3.2-A, ГДД §9).

Все ошибки наследуются от общей `CaravanError`, чтобы handler-ы
бот-слоя могли через `except CaravanError` поймать любую доменную
проблему и отдать пользователю общий ответ. Конкретные подклассы
выкидываются use-case-ами в Спринтах 3.2-B / 3.2-C.

В Спринте 3.2-A ошибок ещё никто не бросает — это только справочник
для будущих use-case-ов.
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class CaravanError(DomainError):
    """Базовая ошибка домена «Караван»."""


class CaravanNotFoundError(CaravanError):
    """`caravans` не содержит записи с таким `id`.

    Бросает `FinishCaravanBattle` (3.2-C), когда APScheduler-job
    стрельнул на несуществующий `caravan_id`.
    """

    __slots__ = ("caravan_id",)

    def __init__(self, *, caravan_id: int) -> None:
        super().__init__(f"caravan id={caravan_id} not found")
        self.caravan_id = caravan_id


class AlreadyInCaravanError(CaravanError):
    """Игрок уже участвует в активном караване.

    Бросает `CreateCaravan` / `JoinCaravanLobby` (3.2-B), когда
    `activity_lock` на `(player, CARAVAN)` уже взят. Сюда же —
    попытка вступить в качестве защитника, будучи уже караванщиком.
    """

    __slots__ = ("player_id",)

    def __init__(self, *, player_id: int) -> None:
        super().__init__(f"player_id={player_id} is already in a caravan")
        self.player_id = player_id


class CaravanCooldownError(CaravanError):
    """Клан в кулдауне между караванами (ГДД §9.3: 12 ч между караванами клана).

    Бросает `CreateCaravan` (3.2-B). `actual_remaining_seconds` — сколько
    секунд осталось до конца кулдауна; handler в боте маппит на
    локализованное сообщение «попробуй через X мин».
    """

    __slots__ = ("actual_remaining_seconds", "clan_id")

    def __init__(self, *, clan_id: int, actual_remaining_seconds: int) -> None:
        super().__init__(
            f"clan_id={clan_id} caravan cooldown not yet expired, "
            f"remaining {actual_remaining_seconds}s"
        )
        self.clan_id = clan_id
        self.actual_remaining_seconds = actual_remaining_seconds


class CaravanRoleConflictError(CaravanError):
    """Игрок не может выбрать заявленную роль (ГДД §9.4).

    Покрывает три случая:

    1. **Член клана-отправителя пытается стать `RAIDER`.** Запрещено
       таблицей §9.4: рейдером может быть только не-член обоих кланов.
    2. **Член клана-получателя пытается стать `RAIDER`.** То же.
    3. **Не-член обоих кланов пытается стать `CARAVANEER` или
       `DEFENDER`.** Запрещено: караванщик — только клан-отправитель,
       защитник — только клан-получатель.

    `attempted_role` — какую роль выбрал игрок. `reason` —
    машинное описание причины (для bot-handler-а в 3.2-D).
    """

    __slots__ = ("attempted_role", "player_id", "reason")

    def __init__(self, *, player_id: int, attempted_role: str, reason: str) -> None:
        super().__init__(f"player_id={player_id} cannot take role {attempted_role!r}: {reason}")
        self.player_id = player_id
        self.attempted_role = attempted_role
        self.reason = reason


class CaravanRequirementError(CaravanError):
    """Игрок не соответствует требованиям ГДД §9 для входа в караван.

    Поля для маппинга на bot-локали:
    - `requirement="thickness"` — минимальный уровень (`leader=7`,
      `raider=5`, `caravaneer/defender=1`).
    - `requirement="length_total"` — минимальная общая длина (≥ 20 см).
    - `requirement="length_after_contribution"` — минимальная длина
      ПОСЛЕ внесения вклада (≥ 20 см); только для караванщиков.
    """

    __slots__ = ("actual", "player_id", "required", "requirement")

    def __init__(
        self,
        *,
        player_id: int,
        requirement: str,
        required: int,
        actual: int,
    ) -> None:
        super().__init__(
            f"player_id={player_id} fails caravan requirement {requirement!r}: "
            f"required>={required}, got {actual}"
        )
        self.player_id = player_id
        self.requirement = requirement
        self.required = required
        self.actual = actual


class CaravanLobbyClosedError(CaravanError):
    """Лобби каравана уже закрыто (`status != LOBBY`).

    Бросает `JoinCaravanLobby` / `LeaveCaravanLobby` (3.2-B), когда
    игрок попытался присоединиться / выйти после `LOBBY → IN_BATTLE`
    или после `CANCELLED`.
    """

    __slots__ = ("caravan_id", "status")

    def __init__(self, *, caravan_id: int, status: str) -> None:
        super().__init__(f"caravan id={caravan_id} lobby is closed, status={status!r}")
        self.caravan_id = caravan_id
        self.status = status


class CaravanCapacityExceededError(CaravanError):
    """Превышен предел участников по роли (ГДД §9.5).

    `RAIDER` ≤ ×4 от количества караванщиков. `DEFENDER` ≤ ×2 от
    количества караванщиков. Караванщиков (`CARAVANEER` + `LEADER`)
    предел не имеет (но clamp-имым общим лимитом по `MAX_PARTICIPANTS_TOTAL`
    из `CaravansConfig`).
    """

    __slots__ = ("caravan_id", "limit", "role")

    def __init__(self, *, caravan_id: int, role: str, limit: int) -> None:
        super().__init__(f"caravan id={caravan_id} role {role!r} capacity {limit} reached")
        self.caravan_id = caravan_id
        self.role = role
        self.limit = limit


class InvalidCaravanStateError(CaravanError):
    """Караван в неожиданном статусе для запрашиваемой операции.

    Бросает `FinishCaravanBattle` (3.2-C), когда APScheduler-job
    `caravan_battle_finish` стрельнул на караване в `LOBBY`-статусе
    (т.е. инвариант перехода `LOBBY → IN_BATTLE` нарушен — job на
    `battle_ends_at` не должен срабатывать без предварительного закрытия
    лобби). Это симптом баги шедулера / админ-вмешательства; ловится
    bot-handler-ом на верхнем уровне как «непредвиденное состояние».

    Идемпотентные no-op-ы (повторный вызов на `FINISHED`/`CANCELLED`)
    эту ошибку НЕ бросают — они выходят раньше с
    `was_already_finished=True`.
    """

    __slots__ = ("actual", "caravan_id", "expected")

    def __init__(self, *, caravan_id: int, expected: str, actual: str) -> None:
        super().__init__(
            f"caravan id={caravan_id} unexpected status: expected {expected!r}, got {actual!r}"
        )
        self.caravan_id = caravan_id
        self.expected = expected
        self.actual = actual


__all__ = [
    "AlreadyInCaravanError",
    "CaravanCapacityExceededError",
    "CaravanCooldownError",
    "CaravanError",
    "CaravanLobbyClosedError",
    "CaravanNotFoundError",
    "CaravanRequirementError",
    "CaravanRoleConflictError",
    "InvalidCaravanStateError",
]
