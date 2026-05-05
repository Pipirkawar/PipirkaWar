"""Use-case `UpgradeThickness` (Спринт 1.4.A, ГДД §3.2).

Игрок отправляет `/upgrade` и подтверждает через inline-кнопку.
Use-case:

1. Находит `Player` по `tg_id`. Нет — `PlayerNotFoundError`.
2. Считает стоимость следующего уровня по
   `progression.cost_for_upgrade(...)` через `balance.thickness.cost_*`.
3. Если в `input_dto.expected_cost_cm` передан ожидаемый UI-контракт
   и он не совпадает с актуальной стоимостью — `ConcurrencyError`
   (защита от рейс-кондишена «balance.yaml перегружен между показом
   и нажатием Подтвердить»).
4. Проверяет правило 20 см: `progression.require_spend(THICKNESS_UPGRADE)`.
5. Снимает стоимость через `Player.with_length(length - cost)`.
6. Поднимает уровень через `Player.with_thickness(level + 1)`.
7. Сохраняет в одной транзакции; пишет два аудит-события:
   * `LENGTH_REVOKE` с `reason="thickness_upgrade"` — для отслеживания
     списания (как и любая другая трата длины).
   * `THICKNESS_UPGRADE` с `reason="player_initiated"` и
     `idempotency_key=f"thickness_upgrade:{player_id}:{new_level}"`
     — повторный двойной клик не пройдёт дважды по уникальности
     ключа.

Транзакция: всё внутри одного `IUnitOfWork`. Любая ошибка откатывает
все мутации.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import UpgradeThicknessInput
from pipirik_wars.domain.anticheat import AnticheatGuard
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import (
    IPlayerRepository,
    Length,
    Player,
    Thickness,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression import (
    SpendAction,
    cost_for_upgrade,
    require_spend,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)
from pipirik_wars.shared.errors import ConcurrencyError


@dataclass(frozen=True, slots=True)
class ThicknessUpgraded:
    """Результат успешной прокачки.

    `cost_cm` — сколько списали. `new_thickness` — новый уровень
    (всегда `player_before.thickness.level + 1`). Handler-у нужны оба
    значения, чтобы показать «прокачано до N (списано XXXX см)».
    """

    player_before: Player
    player_after: Player
    cost_cm: int
    new_thickness: int


class UpgradeThickness:
    """Use-case «прокачать толщину на 1 уровень»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        balance: IBalanceConfig,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._balance = balance
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: UpgradeThicknessInput) -> ThicknessUpgraded:
        """Прокачать толщину. Бросает:

        - `PlayerNotFoundError` — игрока с таким `tg_id` нет;
        - `AnticheatSoftBanError` — игрок в активном soft-ban-е (Спринт 1.6.E);
        - `InsufficientLengthError` — не хватает длины (после списания < 20 см);
        - `ConcurrencyError` — `expected_cost_cm` не совпал с актуальной
          стоимостью (баланс перегружен).
        """
        async with self._uow:
            player = await self._players.get_by_tg_id(input_dto.tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=input_dto.tg_id)
            assert player.id is not None  # repo гарантирует id

            # Anti-cheat soft-ban gate (Спринт 1.6.E, ГДД §3.3.5):
            # пока активен soft-ban — нельзя ни получать длину (1.6.D),
            # ни тратить её (этот гейт здесь). Иначе читер мог бы
            # быстро спустить накопленное и обойти проверку.
            AnticheatGuard.require_unlocked(player, now=self._clock.now())

            cfg = self._balance.get()
            cost_cm = cost_for_upgrade(
                current_thickness=player.thickness.level,
                cost_base=cfg.thickness.cost_base,
                cost_exponent=cfg.thickness.cost_exponent,
            )
            if input_dto.expected_cost_cm is not None and input_dto.expected_cost_cm != cost_cm:
                raise ConcurrencyError(
                    f"thickness upgrade cost changed: UI showed "
                    f"{input_dto.expected_cost_cm} cm, current is {cost_cm} cm"
                )

            require_spend(
                length_cm=player.length.cm,
                cost_cm=cost_cm,
                action=SpendAction.THICKNESS_UPGRADE,
            )

            now = self._clock.now()
            new_length = Length(cm=player.length.cm - cost_cm)
            new_thickness = Thickness(level=player.thickness.level + 1)
            updated = player.with_length(new_length, now=now).with_thickness(new_thickness, now=now)
            saved = await self._players.save(updated)

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.LENGTH_REVOKE,
                    actor_id=player.tg_id,
                    target_kind="player",
                    target_id=str(player.id),
                    before={"length_cm": player.length.cm},
                    after={"length_cm": saved.length.cm},
                    reason="thickness_upgrade",
                    idempotency_key=(f"thickness_upgrade_spend:{player.id}:{new_thickness.level}"),
                    occurred_at=now,
                )
            )
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.THICKNESS_UPGRADE,
                    actor_id=player.tg_id,
                    target_kind="player",
                    target_id=str(player.id),
                    before={"thickness": player.thickness.level},
                    after={"thickness": saved.thickness.level},
                    reason="player_initiated",
                    idempotency_key=(f"thickness_upgrade:{player.id}:{new_thickness.level}"),
                    occurred_at=now,
                )
            )

        return ThicknessUpgraded(
            player_before=player,
            player_after=saved,
            cost_cm=cost_cm,
            new_thickness=saved.thickness.level,
        )


__all__ = [
    "ThicknessUpgraded",
    "UpgradeThickness",
]
