"""Domain-ошибки рейд-боссов (Спринт 3.3-A, ГДД §10).

Все ошибки наследуются от общей `BossError`, чтобы handler-ы бот-слоя
могли через `except BossError` поймать любую доменную проблему и отдать
пользователю общий ответ. Конкретные подклассы выкидываются use-case-ами
в Спринтах 3.3-B / 3.3-C.

В Спринте 3.3-A ошибок ещё никто не бросает — это только справочник
для будущих use-case-ов.
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class BossError(DomainError):
    """Базовая ошибка домена «Рейд-боссы»."""


class BossFightNotFoundError(BossError):
    """`boss_fights` не содержит записи с таким `id`.

    Бросает `RunBossRound` / `FinishBossFight` (3.3-C), когда
    APScheduler-job стрельнул на несуществующий `boss_fight_id`.
    """

    __slots__ = ("boss_fight_id",)

    def __init__(self, *, boss_fight_id: int) -> None:
        super().__init__(f"boss_fight id={boss_fight_id} not found")
        self.boss_fight_id = boss_fight_id


class BossSummonOnGlobalCooldownError(BossError):
    """Глобальный кулдаун призыва ещё не истёк (ГДД §10.1: 1/4 ч глобально).

    Бросает `SummonBoss` (3.3-B). Кулдаун — **глобальный на проект**:
    один призыв в 4 часа на весь сервер. Это распределённый lock через
    `boss_fights.started_at`-запрос (`get_last_global_started_at`).
    `actual_remaining_seconds` — сколько секунд осталось до конца кулдауна;
    handler в боте маппит на локализованное сообщение «попробуй через X мин».
    """

    __slots__ = ("actual_remaining_seconds",)

    def __init__(self, *, actual_remaining_seconds: int) -> None:
        super().__init__(
            f"boss summon global cooldown not yet expired, remaining {actual_remaining_seconds}s"
        )
        self.actual_remaining_seconds = actual_remaining_seconds


class AlreadyInBossFightError(BossError):
    """Игрок уже участвует в активном рейд-бое.

    Бросает `SummonBoss` / `JoinBossLobby` (3.3-B), когда `activity_lock`
    на `(player, BOSS_FIGHT)` уже взят. Случай: рейдер пытается вступить
    во второй рейд, пока в первом ещё лобби / бой.
    """

    __slots__ = ("player_id",)

    def __init__(self, *, player_id: int) -> None:
        super().__init__(f"player_id={player_id} is already in a boss fight")
        self.player_id = player_id


class BossFightRequirementError(BossError):
    """Игрок не соответствует требованиям ГДД §10.1 для входа в рейд.

    Поля для маппинга на bot-локали:
    - `requirement="thickness"` — минимальный уровень (`summoner=9`,
      `raider=4`).
    - `requirement="length_total"` — минимальная общая длина (≥ 20 см).

    Бросает `SummonBoss` / `JoinBossLobby` (3.3-B).
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
            f"player_id={player_id} fails boss-fight requirement {requirement!r}: "
            f"required>={required}, got {actual}"
        )
        self.player_id = player_id
        self.requirement = requirement
        self.required = required
        self.actual = actual


class BossFightLobbyClosedError(BossError):
    """Лобби рейд-боя уже закрыто (`status != LOBBY`).

    Бросает `JoinBossLobby` / `LeaveBossLobby` (3.3-B), когда игрок
    попытался присоединиться / выйти после `LOBBY → IN_BATTLE` или
    после `CANCELLED`.
    """

    __slots__ = ("boss_fight_id", "status")

    def __init__(self, *, boss_fight_id: int, status: str) -> None:
        super().__init__(f"boss_fight id={boss_fight_id} lobby is closed, status={status!r}")
        self.boss_fight_id = boss_fight_id
        self.status = status


class NotInBossFightError(BossError):
    """Игрок не является участником этого рейд-боя.

    Бросает `LeaveBossLobby` (3.3-B), когда не-участник попытался
    выйти. Также `RunBossRound` (3.3-C), когда игрок прислал ход,
    не будучи саммонером (только саммонер управляет боссом / своей
    атакой) или рейдером.
    """

    __slots__ = ("boss_fight_id", "player_id")

    def __init__(self, *, boss_fight_id: int, player_id: int) -> None:
        super().__init__(f"player_id={player_id} is not in boss_fight id={boss_fight_id}")
        self.boss_fight_id = boss_fight_id
        self.player_id = player_id


class BossPlayerPoolEmptyError(BossError):
    """Пул кандидатов в боссы (топ-30 игроков по длине) пуст.

    Бросает `SummonBoss` (3.3-B), когда после фильтрации топ-30 игроков
    не осталось ни одного валидного кандидата (например, все заморожены
    через клан / в активной активности / это сам саммонер). Реалистично
    редкий случай (нужны < 30 игроков всего на сервере), но возможный
    на ранних стадиях проекта.

    `pool_size` — фактический размер top-N пула (обычно 30, но
    конфигурируемо через `BossesConfig.top_n_pool`).
    """

    __slots__ = ("pool_size",)

    def __init__(self, *, pool_size: int) -> None:
        super().__init__(f"boss player pool is empty (pool_size={pool_size})")
        self.pool_size = pool_size


class InvalidBossFightStateError(BossError):
    """Рейд-бой в неожиданном статусе для запрашиваемой операции.

    Бросает `FinishBossFight` (3.3-C), когда APScheduler-job
    `boss_lobby_close` стрельнул на бое в `IN_BATTLE`-статусе (т.е.
    инвариант перехода `LOBBY → IN_BATTLE` нарушен). Также `RunBossRound`,
    если бой уже `FINISHED`/`CANCELLED`. Это симптом баги шедулера /
    админ-вмешательства; ловится bot-handler-ом на верхнем уровне
    как «непредвиденное состояние».

    Идемпотентные no-op-ы (повторный вызов на `FINISHED`/`CANCELLED`)
    эту ошибку НЕ бросают — они выходят раньше с
    `was_already_finished=True`.
    """

    __slots__ = ("actual", "boss_fight_id", "expected")

    def __init__(self, *, boss_fight_id: int, expected: str, actual: str) -> None:
        super().__init__(
            f"boss_fight id={boss_fight_id} unexpected status: "
            f"expected {expected!r}, got {actual!r}"
        )
        self.boss_fight_id = boss_fight_id
        self.expected = expected
        self.actual = actual


__all__ = [
    "AlreadyInBossFightError",
    "BossError",
    "BossFightLobbyClosedError",
    "BossFightNotFoundError",
    "BossFightRequirementError",
    "BossPlayerPoolEmptyError",
    "BossSummonOnGlobalCooldownError",
    "InvalidBossFightStateError",
    "NotInBossFightError",
]
