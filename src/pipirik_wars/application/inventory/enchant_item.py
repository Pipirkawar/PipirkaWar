"""Use-case `EnchantItem` (Спринт 3.4-C, ГДД §2.8).

Заточка одного предмета одним скроллом за один вызов:

1. Idempotency-check по ключу `enchant:{idempotency_key}` —
   повторный вызов с тем же ключом → no-op, возвращается результат
   с `idempotent=True` без побочных эффектов.
2. Загрузка `Item` (`IItemRepository.get`) → `ItemNotFoundError`.
3. Парсинг `scroll_id` → `Scroll`-VO (детерминирован, не лезет в БД).
4. Валидация `item.matches_scroll(scroll)` → `WrongScrollCategoryError`.
5. Списание скролла (`IScrollRepository.consume(qty=1)`) →
   `ScrollNotFoundError` / `ScrollOutOfStockError`.
6. Ролл исхода (`pick_enchant_outcome`, чистая функция):
   safe-zone forced-success / weighted choice по `EnchantmentConfig`.
7. Применение исхода:
   * `SUCCESS` / `SUCCESS_1` (+1) / `SUCCESS_2` (+2) → `update_enchant_level`;
   * `NO_EFFECT` → `enchant_level` не меняется (skip update);
   * `DROP` (-1) / `DROP_1` (-1) / `DROP_2` (-2) → `update_enchant_level`
     с clamp на `0` (`max(0, level - delta)`);
   * `DESTROY` → `IItemRepository.delete` (физическое удаление).
8. Audit `ITEM_ENCHANT_ATTEMPT` (target=player, after содержит
   `outcome` / `old_level` / `new_level` / `blessed` / `item_destroyed`).
9. `IIdempotencyKey.mark` (фиксация ключа в той же транзакции).
10. **Trip-wire анти-чита** (C.5): если попытка прошла на тире
    `+18 → +25` (по `old_level`) и оказалась успешной — читаем
    rolling-window последних 10 попыток на тех же тирах
    (`IEnchantHistoryReader`); если все 10 — успехи, пишем
    `ENCHANT_ANOMALY` audit-event (admin alert), `anomaly_detected=True`.

Применение исхода и `acquired_at` не меняются (заточка не «обновляет
дату приобретения»).

`delta_cm` в audit-записях `ITEM_ENCHANT_ATTEMPT`/`ENCHANT_ANOMALY`
**не** заполняется — заточка не меняет длину игрока (sink происходит
через расход скролла-стэка, не через длину).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pipirik_wars.domain.balance import IBalanceConfig
from pipirik_wars.domain.enchantment.entities import Scroll
from pipirik_wars.domain.inventory import (
    BlessedEnchantOutcome,
    IEnchantHistoryReader,
    IItemRepository,
    IScrollRepository,
    RegularEnchantOutcome,
    WrongScrollCategoryError,
    pick_enchant_outcome,
)
from pipirik_wars.domain.inventory.entities import MAX_ENCHANT_LEVEL
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IRandom,
    IUnitOfWork,
)

__all__ = [
    "ANOMALY_TIER_MAX",
    "ANOMALY_TIER_MIN",
    "ANOMALY_WINDOW_SIZE",
    "EnchantAttemptResult",
    "EnchantItem",
]


_IDEMPOTENCY_NAMESPACE: Final[str] = "enchant"
"""Namespace для `IIdempotencyKey`-меток use-case-а заточки."""


ANOMALY_TIER_MIN: Final[int] = 18
"""Минимальный `enchant_level` (до попытки), на котором trip-wire анти-чита
учитывает результаты. Ниже `+18` лестница успехов вероятна органически."""


ANOMALY_TIER_MAX: Final[int] = 25
"""Максимальный `enchant_level` (до попытки), на котором trip-wire учитывает
результаты. На `+26+` пытаются единицы — окно 10 попыток нерепрезентативно."""


ANOMALY_WINDOW_SIZE: Final[int] = 10
"""Сколько последних попыток на тирах `[ANOMALY_TIER_MIN, ANOMALY_TIER_MAX]`
проверяется на «все успехи» — порог trip-wire."""


@dataclass(frozen=True, slots=True)
class EnchantAttemptResult:
    """Результат одной попытки заточки (Спринт 3.4-C).

    `outcome` — конкретный enum-исход picker-а (`success` / `no_effect`
    / `drop` / `destroy` для regular; `success_1` / `success_2` /
    `no_effect` / `drop_1` / `drop_2` для blessed).

    `old_level` / `new_level` — уровень заточки **до** и **после**
    применения исхода. На `DESTROY` `new_level == 0` (предмет удалён,
    числовое значение — placeholder; используйте `item_destroyed`).

    `item_destroyed` — `True` для regular `DESTROY`-исхода (предмет
    удалён из инвентаря). `item_dropped` — `True` для всех
    `DROP*`-исходов (уровень понизился, но предмет остался). На
    `+0 → DROP` `new_level=0` (clamp), `item_dropped=True`.

    `idempotent` — `True`, если вызов был no-op'ом (ключ уже виден):
    скролл не списан повторно, audit не записан повторно, `outcome`
    в этом случае дефолтный (`NO_EFFECT`/`NO_EFFECT`-blessed),
    `old_level == new_level == текущий уровень предмета`.

    `anomaly_detected` — `True`, если этой попыткой замкнулось
    rolling-окно из 10 успехов на тирах `+18 → +25` (admin alert
    `ENCHANT_ANOMALY` уже записан в audit-лог).
    """

    outcome: RegularEnchantOutcome | BlessedEnchantOutcome
    old_level: int
    new_level: int
    item_destroyed: bool
    item_dropped: bool
    idempotent: bool = False
    anomaly_detected: bool = False


class EnchantItem:
    """Заточка предмета по выбранному скроллу (Спринт 3.4-C, ГДД §2.8)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_enchant_history",
        "_idempotency",
        "_item_repo",
        "_random",
        "_scroll_repo",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        item_repo: IItemRepository,
        scroll_repo: IScrollRepository,
        balance: IBalanceConfig,
        random: IRandom,
        audit: IAuditLogger,
        idempotency: IIdempotencyKey,
        clock: IClock,
        enchant_history: IEnchantHistoryReader,
    ) -> None:
        self._uow = uow
        self._item_repo = item_repo
        self._scroll_repo = scroll_repo
        self._balance = balance
        self._random = random
        self._audit = audit
        self._idempotency = idempotency
        self._clock = clock
        self._enchant_history = enchant_history

    async def __call__(
        self,
        *,
        player_id: int,
        item_id: str,
        scroll_id: str,
        idempotency_key: str,
    ) -> EnchantAttemptResult:
        """Выполнить попытку заточки.

        **Требует уже открытый `IUnitOfWork`-контекст у вызывающего**
        (`async with caller_uow:`); вложенный `async with self._uow:`
        запрещён контрактом `IUnitOfWork`. Прямой вызов вне открытого
        контекста → `RuntimeError`.

        Поднимает:
        - `ItemNotFoundError` — нет предмета у игрока;
        - `WrongScrollCategoryError` — категория скролла ≠ категория предмета;
        - `ScrollNotFoundError` — у игрока нет такого скролла в инвентаре;
        - `ScrollOutOfStockError` — есть скролл, но `qty < 1`;
        - `ValueError` — невалидный `scroll_id` (не парсится).
        """
        if not self._uow.is_active:
            raise RuntimeError(
                "EnchantItem requires an active IUnitOfWork context "
                "(caller must open `async with uow:` before invoking).",
            )

        full_key = f"{_IDEMPOTENCY_NAMESPACE}:{idempotency_key}"

        # 1. Idempotency: повторный вызов — no-op.
        if await self._idempotency.is_seen(full_key):
            current = await self._item_repo.get(player_id=player_id, item_id=item_id)
            scroll = Scroll.from_scroll_id(scroll_id)
            no_effect: RegularEnchantOutcome | BlessedEnchantOutcome = (
                BlessedEnchantOutcome.NO_EFFECT
                if scroll.blessed
                else RegularEnchantOutcome.NO_EFFECT
            )
            return EnchantAttemptResult(
                outcome=no_effect,
                old_level=current.enchant_level,
                new_level=current.enchant_level,
                item_destroyed=False,
                item_dropped=False,
                idempotent=True,
                anomaly_detected=False,
            )

        # 2. Загрузка предмета.
        item = await self._item_repo.get(player_id=player_id, item_id=item_id)

        # 3. Парсинг scroll_id → VO (выбрасывает ValueError на невалидном id).
        scroll = Scroll.from_scroll_id(scroll_id)

        # 4. Категория-mismatch.
        if not item.matches_scroll(scroll):
            raise WrongScrollCategoryError(
                scroll_category=scroll.category,
                item_category=item.category,
            )

        # 5. Списание скролла (qty -= 1).
        await self._scroll_repo.consume(
            player_id=player_id,
            scroll_id=scroll_id,
            qty=1,
        )

        # 6. Ролл исхода (чистая функция).
        old_level = item.enchant_level
        outcome = pick_enchant_outcome(
            level=old_level,
            blessed=scroll.blessed,
            config=self._balance.get().enchantment,
            random=self._random,
        )

        # 7. Применение исхода.
        new_level, item_destroyed, item_dropped = await self._apply_outcome(
            player_id=player_id,
            item_id=item_id,
            old_level=old_level,
            outcome=outcome,
        )

        # 8. Audit ITEM_ENCHANT_ATTEMPT (target=player, after — данные попытки).
        now = self._clock.now()
        is_success = _is_success_outcome(outcome)
        await self._audit.record(
            AuditEntry(
                action=AuditAction.ITEM_ENCHANT_ATTEMPT,
                actor_id=player_id,
                target_kind="player",
                target_id=str(player_id),
                before=None,
                after={
                    "item_id": item_id,
                    "scroll_id": scroll_id,
                    "outcome": outcome.value,
                    "old_level": old_level,
                    "new_level": new_level,
                    "blessed": scroll.blessed,
                    "item_destroyed": item_destroyed,
                    "item_dropped": item_dropped,
                    "success": is_success,
                },
                reason="enchant_attempt",
                idempotency_key=full_key,
                occurred_at=now,
            ),
        )

        # 9. Mark idempotency.
        await self._idempotency.mark(full_key, namespace=_IDEMPOTENCY_NAMESPACE)

        # 10. Trip-wire анти-чита (только для успехов на высоких тирах).
        anomaly_detected = False
        if is_success and ANOMALY_TIER_MIN <= old_level <= ANOMALY_TIER_MAX:
            recent = await self._enchant_history.get_recent_high_tier_outcomes(
                player_id=player_id,
                tier_min=ANOMALY_TIER_MIN,
                tier_max=ANOMALY_TIER_MAX,
                limit=ANOMALY_WINDOW_SIZE,
            )
            if len(recent) == ANOMALY_WINDOW_SIZE and all(recent):
                anomaly_detected = True
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.ENCHANT_ANOMALY,
                        actor_id=None,
                        target_kind="player",
                        target_id=str(player_id),
                        before=None,
                        after={
                            "tier_min": ANOMALY_TIER_MIN,
                            "tier_max": ANOMALY_TIER_MAX,
                            "window_size": ANOMALY_WINDOW_SIZE,
                            "trigger_old_level": old_level,
                        },
                        reason="enchant_anomaly_streak",
                        idempotency_key=None,
                        occurred_at=now,
                    ),
                )

        return EnchantAttemptResult(
            outcome=outcome,
            old_level=old_level,
            new_level=new_level,
            item_destroyed=item_destroyed,
            item_dropped=item_dropped,
            idempotent=False,
            anomaly_detected=anomaly_detected,
        )

    async def _apply_outcome(
        self,
        *,
        player_id: int,
        item_id: str,
        old_level: int,
        outcome: RegularEnchantOutcome | BlessedEnchantOutcome,
    ) -> tuple[int, bool, bool]:
        """Применить исход: вернуть `(new_level, item_destroyed, item_dropped)`.

        Подразумевает атомарность вызова в открытой транзакции.
        Делегирует БД через `IItemRepository.update_enchant_level`/`delete`.
        """
        delta = _OUTCOME_LEVEL_DELTA[outcome]
        if outcome is RegularEnchantOutcome.DESTROY:
            await self._item_repo.delete(player_id=player_id, item_id=item_id)
            return 0, True, False
        if delta == 0:
            return old_level, False, False
        new_level = max(0, min(MAX_ENCHANT_LEVEL, old_level + delta))
        await self._item_repo.update_enchant_level(
            player_id=player_id,
            item_id=item_id,
            new_level=new_level,
        )
        return new_level, False, delta < 0


_OUTCOME_LEVEL_DELTA: Final[dict[RegularEnchantOutcome | BlessedEnchantOutcome, int]] = {
    RegularEnchantOutcome.SUCCESS: 1,
    RegularEnchantOutcome.NO_EFFECT: 0,
    RegularEnchantOutcome.DROP: -1,
    RegularEnchantOutcome.DESTROY: 0,  # не используется — handled outside
    BlessedEnchantOutcome.SUCCESS_1: 1,
    BlessedEnchantOutcome.SUCCESS_2: 2,
    BlessedEnchantOutcome.NO_EFFECT: 0,
    BlessedEnchantOutcome.DROP_1: -1,
    BlessedEnchantOutcome.DROP_2: -2,
}
"""Целочисленный delta `enchant_level`-а для каждого исхода (clamp на
`[0, MAX_ENCHANT_LEVEL]` делается отдельно). `DESTROY` обрабатывается
отдельной веткой (предмет удаляется, новый уровень не используется)."""


def _is_success_outcome(
    outcome: RegularEnchantOutcome | BlessedEnchantOutcome,
) -> bool:
    """`success` / `success_1` / `success_2` → True; всё остальное → False."""
    return outcome in (
        RegularEnchantOutcome.SUCCESS,
        BlessedEnchantOutcome.SUCCESS_1,
        BlessedEnchantOutcome.SUCCESS_2,
    )
