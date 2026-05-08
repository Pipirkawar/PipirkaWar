"""VO домена «Караван» (Спринт 3.2-A, ГДД §9 «Караваны»).

Каркас доменных VO без бизнес-логики бой-механики и use-case-ов
(они приходят в Спринтах 3.2-B и 3.2-C соответственно).

Ключевые VO:

- **`CaravanRole`** — три роли участников (ГДД §9.4):
    `LEADER` (создатель, обязательный участник; всегда `caravaneer`),
    `CARAVANEER` (обычный караванщик из клана-отправителя),
    `DEFENDER` (защитник из клана-получателя),
    `RAIDER` (нападающий извне обоих кланов).
- **`CaravanStatus`** — состояния каравана: `LOBBY` (20 мин сбора),
    `IN_BATTLE` (60 мин путь + бой), `FINISHED` (исход применён),
    `CANCELLED` (лидер отменил / клан подвергся заморозке посреди
    лобби и т. п.).
- **`CaravanContribution`** — VO «вклад в караван»: целое число см > 0.
    Каждый караванщик должен после взноса иметь ≥ `min_length_after_cm`
    (по конфигу). На уровне VO мы валидируем только `contribution_cm > 0`
    (правило «20 см остаётся» — на уровне use-case, потому что зависит
    от `Length` игрока в момент создания).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class CaravanRole(str, enum.Enum):
    """Роль участника в караване (ГДД §9.4).

    `LEADER` — создатель каравана. Всегда сразу же зачисляется как
    `CARAVANEER` + получает бонус ×4 при победе. **Лидер — всегда
    караванщик**, никогда не защитник и не рейдер.

    `CARAVANEER` — обычный участник из клана-отправителя.

    `DEFENDER` — защитник из клана-получателя. Если игрок состоит в
    обоих кланах одновременно (см. ГДД §9.4 таблица), он может выбрать
    либо `CARAVANEER`, либо `DEFENDER` — но не обе роли (одна
    активность за раз через `activity_lock`).

    `RAIDER` — рейдер. Может им быть **только тот, кто НЕ состоит
    ни в клане-отправителе, ни в клане-получателе** (ГДД §9.4).
    """

    LEADER = "leader"
    CARAVANEER = "caravaneer"
    DEFENDER = "defender"
    RAIDER = "raider"


class CaravanStatus(str, enum.Enum):
    """Жизненный цикл каравана (ГДД §9.3 / §9.5 / §9.6).

    `LOBBY` — после `/caravan_create`: лидер пришёл, в чате клана
    объявление, идёт сбор участников (20 мин). Кулдаун клана 12 ч
    стартует с момента входа в `LOBBY`. На переходе `LOBBY → IN_BATTLE`
    проверяются минимальные условия (ГДД §9.3: «минимум 1 — лидер»;
    де-факто всегда выполняется, потому что лидер — обязательный
    участник).

    `IN_BATTLE` — бой 60 мин (ГДД §9.5). Участники добавляться больше
    не могут — лобби закрыто. Активный лок взят на всех. APScheduler-job
    `caravan_battle_finish` запланирован на `started_at + 60 мин`.

    `FINISHED` — `FinishCaravanBattle` применил исход (длина изменена,
    клан-получатель получил +1 см, лидер успешного каравана получил
    `Атаман`-титул, audit записан). Идемпотентность повторного финиша —
    на уровне use-case через `was_already_finished`.

    `CANCELLED` — лобби закрыто без боя. Возможные причины:
    — лидер вышел из лобби до 20 мин и других караванщиков не было;
    — клан-отправитель / клан-получатель заморозился посреди лобби;
    — миграция group → supergroup сменила chat_id посреди лобби.
    Активный лок снят, кулдаун клана **сохраняется** (ГДД §9.3,
    кулдаун начинается с попытки создать караван, не с успешного
    завершения).
    """

    LOBBY = "lobby"
    IN_BATTLE = "in_battle"
    FINISHED = "finished"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class CaravanContribution:
    """Вклад караванщика в караван (ГДД §9.2).

    Целое число см, строго > 0. Хранится в БД на уровне записи
    `caravan_participants` (один игрок — один вклад в один караван).

    Доменное правило «после взноса остаётся ≥ 20 см» проверяется
    на уровне use-case `JoinCaravanLobby` (зависит от `Length`
    игрока в момент вступления + конфига `min_length_after_cm`).
    """

    cm: int

    def __post_init__(self) -> None:
        if not isinstance(self.cm, int) or isinstance(self.cm, bool):
            raise TypeError(f"CaravanContribution.cm must be int, got {type(self.cm).__name__}")
        if self.cm <= 0:
            raise ValueError(f"CaravanContribution.cm must be > 0, got {self.cm}")


__all__ = [
    "CaravanContribution",
    "CaravanRole",
    "CaravanStatus",
]
