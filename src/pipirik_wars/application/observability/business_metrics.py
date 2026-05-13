"""Порт `IBusinessMetrics` (Спринт 4.1-N, шаг N.1).

Cross-cutting cross-process *доменно-агностичный* контракт, который дёргают
use-case-ы при критических state-change-ах. Реальная реализация
(`PrometheusBusinessMetrics`) живёт в `infrastructure/observability/`.

Для unit-тестов use-case-ов и для production-сборки без Redis
(`AI_ENABLED=False`-режим из 4.1-J/4.1-M) используется null-object
`NullBusinessMetrics` — no-op-реализация без зависимостей.

Семантика лейблов нормализована в Literal-типы:

* `BusinessMetricsCurrency` ∈ `{"stars", "ton", "usdt"}` — соответствует
  `Currency`-StrEnum из `domain/monetization/value_objects.py` (`STARS`,
  `TON_NANO`, `USDT_DECIMAL`), но в lowercase short-form (Prometheus-label
  convention: `[a-z][a-z0-9_]*`).
* `CaravanOutcome` ∈ `{"raiders_win", "owner_win", "draw", "cancelled"}`.
* `RaidOutcome` ∈ `{"raiders_win", "boss_win", "cancelled"}`.
* `DuelResolvedOutcome` ∈ `{"p1_win", "p2_win", "draw", "p1_afk", "p2_afk"}`.
* `ForestRunOutcome` ∈ `{"success", "drop", "idle_timeout", "cancelled"}`.
* `RouletteKind` ∈ `{"free", "paid"}`.

Use-case → label-mapping реализуется на стороне use-case-а (или в
helper-методах), чтобы порт оставался lower-bound-decoupled от
доменных enum-ов.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

BusinessMetricsCurrency = Literal["stars", "ton", "usdt"]
CaravanOutcome = Literal["raiders_win", "owner_win", "draw", "cancelled"]
RaidOutcome = Literal["raiders_win", "boss_win", "cancelled"]
DuelResolvedOutcome = Literal["p1_win", "p2_win", "draw", "p1_afk", "p2_afk"]
ForestRunOutcome = Literal["success", "drop", "idle_timeout", "cancelled"]
RouletteKind = Literal["free", "paid"]


class IBusinessMetrics(ABC):
    """Контракт сбора бизнес-метрик.

    Все методы — синхронные no-throw: реализация не должна выбрасывать
    исключения при ошибках Prometheus-counter-операций (метрики — это
    observability, не critical-path). Production-адаптер при сбое
    inc/set-операции логирует warning и возвращает None.

    Методы разбиты на 5 групп по «доменам»: активность (DAU + active
    counters), монетизация (prize pool gauges), рулетка, дуэли, лес.
    """

    @abstractmethod
    def set_dau(self, value: int) -> None:
        """Установить gauge `pipirik_dau_active_users` в текущее значение.

        Вызывается из background-polling-таска в `bot/main.py::run()`
        раз в минуту. Hot-path use-case `RecordPlayerActivity` НЕ
        инструментирован (snapshot быстрее, чем counter-инкремент на
        каждый message). См. ГДД §0 «DAU Gate».
        """

    @abstractmethod
    def inc_caravan_active(self) -> None:
        """Karavan создан и стартовал — gauge `pipirik_caravan_active` +1."""

    @abstractmethod
    def dec_caravan_active(self) -> None:
        """Karavan завершился (любой outcome) — gauge `pipirik_caravan_active` −1."""

    @abstractmethod
    def inc_caravan_outcome(self, outcome: CaravanOutcome) -> None:
        """Counter `pipirik_caravan_outcomes_total{outcome=...}` +1."""

    @abstractmethod
    def inc_raid_active(self) -> None:
        """Рейд призван — gauge `pipirik_raid_active` +1."""

    @abstractmethod
    def dec_raid_active(self) -> None:
        """Рейд завершился — gauge `pipirik_raid_active` −1."""

    @abstractmethod
    def inc_raid_outcome(self, outcome: RaidOutcome) -> None:
        """Counter `pipirik_raid_outcomes_total{outcome=...}` +1."""

    @abstractmethod
    def set_prize_pool_balance(self, currency: BusinessMetricsCurrency, amount: float) -> None:
        """Gauge `pipirik_prize_pool_balance{currency=...}` := `amount`.

        Вызывается из `RecordDonation` / `ClaimPrize` / `RefundLot` /
        `RegeneratePrizeLots` — точки изменения баланса пула. `amount` —
        число в base-units конкретной валюты:

        * `currency="stars"` → integer Stars (1.0 = 1 ⭐).
        * `currency="ton"` → float TON (1.0 = 1 TON, после `/1e9` из
          `ton_nano`).
        * `currency="usdt"` → float USDT (1.0 = 1 USDT, после `/1e6` из
          `usdt_decimal`).
        """

    @abstractmethod
    def inc_roulette_spin(self, kind: RouletteKind, prize_class: str) -> None:
        """Counter `pipirik_roulette_spins_total{kind, prize_class}` +1.

        `prize_class` — короткий tag-ярлык категории приза (например,
        `"cm"`, `"length_bonus"`, `"blessed_scroll"`, `"crypto"`,
        `"empty"`). См. ГДД §12.4.2, §12.5.2.
        """

    @abstractmethod
    def inc_duel_resolved(self, outcome: DuelResolvedOutcome) -> None:
        """Counter `pipirik_duel_resolved_total{outcome=...}` +1.

        Вызывается из `ApplyOutcome` / `ApplyMassOutcome` /
        `ResolveAfkRound` — финализаторы дуэлей.
        """

    @abstractmethod
    def inc_forest_started(self) -> None:
        """Counter `pipirik_forest_run_started_total` +1."""

    @abstractmethod
    def inc_forest_finished(self, outcome: ForestRunOutcome) -> None:
        """Counter `pipirik_forest_run_finished_total{outcome=...}` +1."""


class NullBusinessMetrics(IBusinessMetrics):
    """No-op-реализация (null-object).

    Default-значение для use-case-конструкторов и для unit-тестов: позволяет
    избавиться от условных проверок `if metrics is not None: metrics.inc(...)`
    в каждом use-case-е.

    Production-сборка перетирает default на `PrometheusBusinessMetrics`
    в композиционном корне (см. `bot/main.py::build_container`).
    """

    def set_dau(self, value: int) -> None:
        """No-op."""

    def inc_caravan_active(self) -> None:
        """No-op."""

    def dec_caravan_active(self) -> None:
        """No-op."""

    def inc_caravan_outcome(self, outcome: CaravanOutcome) -> None:
        """No-op."""

    def inc_raid_active(self) -> None:
        """No-op."""

    def dec_raid_active(self) -> None:
        """No-op."""

    def inc_raid_outcome(self, outcome: RaidOutcome) -> None:
        """No-op."""

    def set_prize_pool_balance(self, currency: BusinessMetricsCurrency, amount: float) -> None:
        """No-op."""

    def inc_roulette_spin(self, kind: RouletteKind, prize_class: str) -> None:
        """No-op."""

    def inc_duel_resolved(self, outcome: DuelResolvedOutcome) -> None:
        """No-op."""

    def inc_forest_started(self) -> None:
        """No-op."""

    def inc_forest_finished(self, outcome: ForestRunOutcome) -> None:
        """No-op."""
