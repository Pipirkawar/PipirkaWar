"""Audit-лог. Каждая мутация состояния пишется атомарно вместе с самой
операцией.

ГДД §0 (политика разработки) и §18.6.4 (безопасность админки) делают
аудит обязательным:

- любое изменение длины/толщины/титула игрока;
- любое назначение Главы клана дня;
- любое реферальное начисление;
- любая админ-команда (`/admin_*`).

Запись в `audit_log` идёт **в той же транзакции**, что и сама мутация
(см. `IUnitOfWork`). Это исключает «потерянный аудит» при сбое после
коммита бизнес-таблицы.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from datetime import datetime


class AuditAction(str, enum.Enum):
    """Категории аудит-событий.

    Расширяется по мере появления новых use-cases. Пока — только
    общие категории, конкретные `reason` передаются отдельным полем.
    """

    LENGTH_GRANT = "length_grant"
    LENGTH_REVOKE = "length_revoke"
    THICKNESS_UPGRADE = "thickness_upgrade"
    TITLE_GRANT = "title_grant"
    NAME_GRANT = "name_grant"
    DAILY_HEAD_ASSIGN = "daily_head_assign"
    REFERRAL_MILESTONE = "referral_milestone"
    PLAYER_REGISTER = "player_register"
    CLAN_REGISTER = "clan_register"
    CLAN_MIGRATE = "clan_migrate"
    CLAN_MEMBER_JOIN = "clan_member_join"
    CLAN_FREEZE = "clan_freeze"
    CLAN_UNFREEZE = "clan_unfreeze"
    BALANCE_RELOAD = "balance_reload"
    DAU_LIMIT_CHANGE = "dau_limit_change"
    DAU_THRESHOLD_REACHED = "dau_threshold_reached"
    PLAYER_QUEUED = "player_queued"
    PLAYER_PROMOTED = "player_promoted"
    PLAYER_LOCALE_SET = "player_locale_set"
    FOREST_RUN_STARTED = "forest_run_started"
    # ── Спринт 3.1-B (PvE: горы и данжон, ГДД §8) ──
    MOUNTAIN_RUN_STARTED = "mountain_run_started"
    MOUNTAIN_RUN_FINISHED = "mountain_run_finished"
    DUNGEON_RUN_STARTED = "dungeon_run_started"
    DUNGEON_RUN_FINISHED = "dungeon_run_finished"
    ADMIN_COMMAND = "admin_command"
    # ── Спринт 1.6 (anti-cheat hardcap, ГДД §3.3) ──
    ANTICHEAT_DAILY_CAP_EXCEEDED = "anticheat_daily_cap_exceeded"
    ANTICHEAT_WEEKLY_CAP_EXCEEDED = "anticheat_weekly_cap_exceeded"
    ANTICHEAT_BAN_LIFTED = "anticheat_ban_lifted"
    # ── Спринт 2.1 (PvP 1×1, ГДД §7.1) ──
    PVP_DUEL_CREATED = "pvp_duel_created"
    PVP_DUEL_ACCEPTED = "pvp_duel_accepted"
    PVP_DUEL_CANCELLED = "pvp_duel_cancelled"
    PVP_DUEL_COMPLETED = "pvp_duel_completed"
    # ── Спринт 2.1.F.2 (глобальное лобби PvP) ──
    PVP_LOBBY_ENQUEUED = "pvp_lobby_enqueued"
    PVP_LOBBY_MATCHED = "pvp_lobby_matched"
    PVP_LOBBY_ESCALATED = "pvp_lobby_escalated"
    PVP_LOBBY_EXPIRED = "pvp_lobby_expired"
    # ── Спринт 2.2 (масс-PvP клан×клан, ГДД §7.2) ──
    PVP_MASS_DUEL_CREATED = "pvp_mass_duel_created"
    PVP_MASS_DUEL_COMPLETED = "pvp_mass_duel_completed"
    PVP_MASS_DUEL_CANCELLED = "pvp_mass_duel_cancelled"
    # ── Спринт 2.4 (реферальная система, ГДД §13.1) ──
    REFERRAL_REGISTERED = "referral_registered"
    REFERRAL_RATE_LIMITED = "referral_rate_limited"
    # ── Спринт 3.2-B (караваны, ГДД §9) ──
    CARAVAN_CREATED = "caravan_created"
    CARAVAN_PLAYER_JOINED = "caravan_player_joined"
    CARAVAN_PLAYER_LEFT = "caravan_player_left"
    CARAVAN_LOBBY_CLOSED = "caravan_lobby_closed"
    # ── Спринт 3.2-C (караваны: бой + награды + отмена, ГДД §9.5–§9.6) ──
    CARAVAN_BATTLE_FINISHED = "caravan_battle_finished"
    CARAVAN_REWARDS_GRANTED = "caravan_rewards_granted"
    CARAVAN_CANCELLED = "caravan_cancelled"
    # ── Спринт 3.3-B (рейд-боссы: лобби, ГДД §10.1–§10.3) ──
    BOSS_FIGHT_SUMMONED = "boss_fight_summoned"
    BOSS_RAIDER_JOINED = "boss_raider_joined"
    BOSS_RAIDER_LEFT = "boss_raider_left"
    BOSS_FIGHT_STARTED = "boss_fight_started"
    # ── Спринт 3.3-C (рейд-боссы: бой + награды + отмена, ГДД §10.4–§10.6) ──
    BOSS_FIGHT_ROUND_RESOLVED = "boss_fight_round_resolved"
    BOSS_FIGHT_FINISHED = "boss_fight_finished"
    BOSS_REWARDS_GRANTED = "boss_rewards_granted"
    BOSS_FIGHT_CANCELLED = "boss_fight_cancelled"
    # Per-player scroll-drop из рейда (ГДД §2.8.5; Спринт 3.3-C / C.6).
    # До Спринта 3.4 «Заточка предметов» дроп-скроллов **только** в audit
    # пишется (не накапливается в инвентаре игрока) — see also `PveScrollDrop`
    # из Спринта 3.1-D. После 3.4 этот же event начнёт сопровождаться
    # реальной записью в `inventory.scrolls`.
    SCROLL_DROP = "scroll_drop"
    # ── Спринт 3.4-C (заточка предметов, ГДД §2.8) ──
    # Каждая попытка заточки `EnchantItem`-use-case-а (даже неуспешная)
    # пишется как audit-event с фиксацией исхода (`success` / `no_effect`
    # / `drop` / `destroy` / blessed-варианты) и `delta` уровня. `delta_cm`
    # не заполняется (заточка не меняет длину; sink происходит через
    # потерю скролла-стэка). Используется bot-handler-ом 3.4-D и
    # admin-просмотром истории заточек.
    ITEM_ENCHANT_ATTEMPT = "item_enchant_attempt"
    # Trip-wire анти-чита (Спринт 3.4-C / C.5; ГДД §2.8 + §3.3.4).
    # Пишется при детекции аномальной серии успехов на высоких тирах
    # (`+18 → +25`): rolling-window последних 10 попыток на этих тирах,
    # все 10 — `success`. Для admin-alert. Per-player target_id.
    ENCHANT_ANOMALY = "enchant_anomaly"
    # ── Спринт 3.5-C (free-to-play рулетка, ГДД §12.4) ──
    # Каждая прокрутка use-case-а `SpinFreeRoulette` пишется как audit-event
    # с `kind` исхода (`length` / `item` / `scroll_regular` / `scroll_blessed`
    # / `crypto_lot`) и `length_cm` для LENGTH-исхода. Сопровождается двумя
    # `LENGTH_GRANT`-ами c источниками `ROULETTE_FREE_COST` (delta=-100,
    # списание стоимости прокрутки) и (только для LENGTH-исхода)
    # `ROULETTE_FREE_REWARD` (delta=+roll, выдача награды). Оба length-source
    # **НЕ** входят в `anticheat.organic_sources` — рулетка не учитывается
    # в anti-cheat 24h/7d-окнах (это zero-sum/audit-only sink/source).
    ROULETTE_SPIN = "roulette_spin"
    # ── Спринт 4.1-A (Telegram Stars + платная рулетка, ГДД §12.5) ──
    # Каждое событие платежа (Stars / TON / USDT) пишется как audit-event
    # с `target_kind="payment"`, `target_id=<idempotency_key>`, `before=None`,
    # `after={"currency": ..., "amount_native": ..., "status": ...}` и
    # `source` — `STARS_PAYMENT` / `TON_PAYMENT` / `USDT_PAYMENT`. Аудит
    # **не** дублирует `payments`-таблицу (она — source of truth для
    # ledger-а), но даёт единый journal для admin-просмотра рядом с
    # бизнес-событиями (`ROULETTE_SPIN`, `LENGTH_GRANT`-reward, и т. п.).
    PAYMENT_RECORDED = "payment_recorded"
    # ── Спринт 4.1-B (призовой пул, ГДД §12.6.1) ──
    # Каждый успешный донат-инкремент пула пишется одной audit-записью
    # в той же транзакции UoW, что и `apply_increment(...)` на
    # `IPrizePoolRepository`. `target_kind="prize_pool"`,
    # `target_id="<idempotency_key>:donation"` (идемпотентен per-платёж),
    # `after={"currency": ..., "amount_native": "<delta>",
    # "pool_after_native": "<пул в этой валюте после инкремента>"}`. Парного
    # `before`-снапшота не пишем (delta + after однозначно восстанавливают
    # before). Источник — `AuditSource.PRIZE_POOL_INCREMENT`. На `applied=False`
    # (донат < 10 native-юнитов, no-op инкремент) audit **не** пишется —
    # инвариант «нет нулевых-дельт в audit-логе».
    PRIZE_POOL_INCREMENT = "prize_pool_increment"
    # ── Спринт 4.1-C (лот-генератор, ГДД §12.6.3) ──
    # Каждый свежесгенерированный `PrizeLot` пишется одной audit-записью
    # в той же транзакции UoW, что и `IPrizeLotRepository.add(lot)` +
    # `IPrizePoolRepository.apply_increment(currency, -lot.amount_native)`.
    # `target_kind="prize_lot"`, `target_id="<root_key>:lot:<idx>"`, `after={
    # "lot_id": <int>, "currency": ..., "amount_native": <gross>, "fee_buffer_native":
    # <int>, "net_amount_native": <gross-fee>, "pool_after_native": <остаток пула>}`.
    # Парного `before`-снапшота не пишем (delta + after однозначно
    # восстанавливают before). Источник — `AuditSource.PRIZE_LOT_GENERATED`.
    # Пишется use-case-ом `GeneratePrizeLots`.
    PRIZE_LOT_GENERATED = "prize_lot_generated"
    # ── Спринт 4.1-C (refund-flow лота, ГДД §12.6.4) ──
    # Каждый refund лота (`PrizeLot.status: ACTIVE|RESERVED → REFUNDED`)
    # пишется одной audit-записью в той же транзакции UoW, что и
    # `IPrizeLotRepository.update_status(lot_id, REFUNDED)` + `IPrizePoolRepository.
    # apply_increment(currency, +lot.amount_native)` (возврат средств в пул).
    # `target_kind="prize_lot"`, `target_id="<lot_id>:refund"`, `after={
    # "lot_id": <int>, "currency": ..., "amount_native": <gross>,
    # "prev_status": "active"|"reserved", "pool_after_native": <пул после возврата>,
    # "reason": "timeout"|"player_decline"|"admin"|"…"}`. Парного
    # `before`-снапшота не пишем. Источник — `AuditSource.PRIZE_LOT_REFUNDED`.
    # Пишется будущим use-case-ом `RefundPrizeLot` (запланировано
    # в 4.1-C / Шаг C.6 «race-резервирование + fallback» и 4.1-D /
    # `ClaimPrize` для timeout-refund-а).
    PRIZE_LOT_REFUNDED = "prize_lot_refunded"
    # ── Спринт 4.1-C (резервирование лота на спине, ГДД §12.6.5) ──
    # Каждое успешное резервирование лота (`PrizeLot.status: ACTIVE →
    # RESERVED`) пишется одной audit-записью в той же транзакции UoW,
    # что и `IPrizeLotRepository.update_status(lot_id, RESERVED)`. Зовётся
    # из `SpinPaidRoulette` / `SpinFreeRoulette`, когда picker рулетки
    # вернул `RouletteOutcome.crypto_lot(lot_id=...)`. `target_kind=
    # "prize_lot"`, `target_id="<lot_id>:reserved"`, `after={"lot_id":
    # <int>, "currency": ..., "amount_native": <gross>, "prev_status":
    # "active", "reserved_at": <utc-iso>, "player_id": <int>,
    # "spin_kind": "paid"|"free"}`. Парного `before`-снапшота не пишем
    # (prev_status однозначен — всегда `active`). Источник —
    # `AuditSource.PRIZE_LOT_RESERVED`. Пишется в C.6.c use-case-ами
    # спинов сразу после выпадения CRYPTO_LOT-исхода. При проигранном
    # race (другой игрок забронировал тот же лот первым) этой записи
    # НЕ будет — вместо неё use-case подменит outcome на LengthGain
    # (C.6.d).
    PRIZE_LOT_RESERVED = "prize_lot_reserved"
    # ── Спринт 4.1-D (выплата лота, ГДД §12.6.4) ──
    PRIZE_LOT_CLAIMED = "prize_lot_claimed"
    # ── Спринт 4.1-D (привязка кошелька, ГДД §12.6.4) ──
    WALLET_LINKED = "wallet_linked"


class AuditSource(str, enum.Enum):
    """Источник аудит-записи (ГДД §3.3.4 / development_plan.md §4 ПД 1.6.1).

    Anti-cheat hardcap различает «органические» источники (forest, oracle,
    referral_*) от «донатных» (stars/ton/usdt) и админских (admin_grant,
    admin_refund) — клампятся **только** organic-источники. Whitelist
    жёстко зашит здесь и в БД-CHECK-инвариант, чтобы случайная опечатка
    в `source="forst"` не вывалила запись из агрегации anti-cheat-окна.

    `UNKNOWN` — маркер для записей до Спринта 1.6.A; миграция backfill-ит
    им все исторические строки. Новые записи в норме должны указывать
    конкретный источник; сейчас (1.6.A) дефолт — `UNKNOWN`, чтобы старые
    use-cases работали без правок до миграции в Спринте 1.6.F.
    """

    FOREST = "forest"
    MOUNTAINS = "mountains"
    DUNGEON = "dungeon"
    ORACLE = "oracle"
    REFERRAL_SIGNUP = "referral_signup"
    REFERRAL_THICKNESS = "referral_thickness"
    PVP_REWARD = "pvp_reward"
    CARAVAN_REWARD = "caravan_reward"
    RAID_REWARD = "raid_reward"
    ADMIN_GRANT = "admin_grant"
    ADMIN_REFUND = "admin_refund"
    STARS_PAYMENT = "stars_payment"
    TON_PAYMENT = "ton_payment"
    USDT_PAYMENT = "usdt_payment"
    # ── Спринт 2.3 (Глава клана дня, ГДД §6.1) ──
    DAILY_HEAD = "daily_head"
    # ── Спринт 3.5-C (free-to-play рулетка, ГДД §12.4) ──
    # `ROULETTE_FREE_COST` (delta=-100) — списание стоимости прокрутки
    # рулетки игроку. `ROULETTE_FREE_REWARD` (delta=+roll) — выдача
    # length-награды (только при LENGTH-исходе). Оба источника
    # **НЕ** входят в `anticheat.organic_sources` (audit-only sink/source):
    # они пишутся в `audit_log` для целей аудита и админ-просмотра, но
    # не учитываются в rolling-окнах (24 ч / 7 дн) anti-cheat-хардкапа.
    # Семантически эта пара zero-sum-нейтральна (cost+reward для LENGTH-
    # исхода; cost-only для остальных), не должна влиять на органический
    # прирост длины.
    ROULETTE_FREE_COST = "roulette_free_cost"
    ROULETTE_FREE_REWARD = "roulette_free_reward"
    # ── Спринт 4.1-A (платная рулетка, ГДД §12.5) ──
    # `ROULETTE_PAID_REWARD` (delta=+roll) — выдача length-награды
    # за платную прокрутку (только при LENGTH-исходе; см. ГДД §12.5.2).
    # «Стоимость» платной прокрутки списывается в Telegram Stars
    # (через `IPaymentLedger.charge`), не в `length`-валюте; поэтому
    # парного `ROULETTE_PAID_COST`-source-а **нет** (cost-side событие
    # — это `AuditAction.PAYMENT_RECORDED` с `source=STARS_PAYMENT`).
    # Как и `ROULETTE_FREE_REWARD`, `ROULETTE_PAID_REWARD` **НЕ** входит
    # в `anticheat.organic_sources` — paid-рулетка не учитывается
    # в rolling-окнах anti-cheat-хардкапа (по тем же причинам, что и
    # free-вариант: zero-sum/audit-only source).
    ROULETTE_PAID_REWARD = "roulette_paid_reward"
    # ── Спринт 3.6-A (бонус-за-племена в /predict, ГДД §11.1) ──
    # Дополнительная проводка `LENGTH_GRANT` поверх базового `oracle`-розыгрыша:
    # `+min(n_active_tribes * cm_per_tribe, cap_cm)` см за активные племена,
    # где состоит игрок (ГДД §11.1; см. `OracleTribeBonusConfig`).
    # Источник специально вынесен из `oracle`, чтобы:
    # - не учитываться в anti-cheat-окнах 24h/7d (см. новый whitelist
    #   `anticheat.tribe_bonus_sources` в `balance.yaml`);
    # - сохранить отдельную статистику «сколько /predict-ов получили бонус
    #   и какой» в audit-логе и аналитике.
    # Аналогично паре `roulette_free_cost`/`roulette_free_reward` (Спринт 3.5-C).
    ORACLE_TRIBE_BONUS = "oracle_tribe_bonus"
    # ── Спринт 4.1-B (призовой пул, ГДД §12.6.1) ──
    # `PRIZE_POOL_INCREMENT` — донат-инкремент призового пула (10% от
    # подтверждённого платежа). Пишется в `audit_log` use-case-ом
    # `RecordDonation` сразу после `IPrizePoolRepository.apply_increment(...)`
    # внутри той же UoW. Парного «cost»-source-а нет: cost-сторона —
    # запись в `payments`-таблицу + `STARS_PAYMENT`/`TON_PAYMENT`/
    # `USDT_PAYMENT` audit-event (см. `PAYMENT_RECORDED`). `prize_pool_increment`
    # **НЕ** входит в `anticheat.organic_sources` / `donate_sources` /
    # `tribe_bonus_sources` (это пул-внутренний бухгалтерский маркер,
    # не length-source).
    PRIZE_POOL_INCREMENT = "prize_pool_increment"
    # ── Спринт 4.1-C (лот-генератор, ГДД §12.6.3) ──
    # `PRIZE_LOT_GENERATED` — source-маркер audit-записи «вырезали лот из пула».
    # Пишется use-case-ом `GeneratePrizeLots` внутри той же UoW, что и
    # `add(lot)` + `apply_increment(currency, -amount)`. Парного «cost»-source-а
    # нет (декремент пула — это уже интернальная проводка, безвыплаты игроку).
    # `PRIZE_LOT_GENERATED` **НЕ** входит в `anticheat.organic_sources` /
    # `donate_sources` / `tribe_bonus_sources` (не length-source, это
    # пул-внутренний бухгалтерский маркер). DB-whitelist (`audit_log_source_whitelist`)
    # расширен Alembic-миграцией `0029_audit_source_prize_lot_generated` (шаг C.2).
    PRIZE_LOT_GENERATED = "prize_lot_generated"
    # `PRIZE_LOT_REFUNDED` — source-маркер audit-записи «вернули лот в пул».
    # Пишется будущим use-case-ом `RefundPrizeLot` (запланирован в 4.1-C / Шаг C.6
    # «race-резервирование + fallback» и 4.1-D / `ClaimPrize` для timeout-refund-а)
    # внутри той же UoW, что и `update_status(lot_id, REFUNDED)` + `apply_increment(
    # currency, +amount)`. Парного «cost»-source-а нет (инкремент пула — внутренняя
    # проводка, без выплаты игроку). `PRIZE_LOT_REFUNDED` **НЕ** входит в
    # `anticheat.organic_sources` / `donate_sources` / `tribe_bonus_sources`
    # (не length-source, это пул-внутренний бухгалтерский маркер). DB-whitelist
    # (`audit_log_source_whitelist`) расширяется Alembic-миграцией
    # `0031_audit_source_prize_lot_refunded` (шаг C.4).
    PRIZE_LOT_REFUNDED = "prize_lot_refunded"
    # `PRIZE_LOT_RESERVED` — source-маркер audit-записи «зарезервировали лот
    # на спине». Пишется use-case-ами `SpinPaidRoulette` / `SpinFreeRoulette`
    # (C.6.c) внутри той же UoW, что и `IPrizeLotRepository.update_status(
    # lot_id, ACTIVE → RESERVED)`. Парного «cost»-source-а нет (декремент
    # пула уже произошёл в `GeneratePrizeLots`). `PRIZE_LOT_RESERVED` **НЕ**
    # входит в `anticheat.organic_sources` / `donate_sources` /
    # `tribe_bonus_sources` (не length-source, это статус-маркер).
    # DB-whitelist (`audit_log_source_whitelist`) расширяется Alembic-
    # миграцией `0032_audit_source_prize_lot_reserved` (шаг C.6.a).
    PRIZE_LOT_RESERVED = "prize_lot_reserved"
    # ── Спринт 4.1-D (выплата лота, ГДД §12.6.4) ──
    PRIZE_LOT_CLAIMED = "prize_lot_claimed"
    # ── Спринт 4.1-D (привязка кошелька, ГДД §12.6.4) ──
    WALLET_LINKED = "wallet_linked"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Запись аудит-лога.

    `before`/`after` хранятся как сериализуемые dict-ы (или None для
    «не применимо»). Реализация конвертирует их в JSONB-колонку.

    `source` — добавлен в Спринте 1.6.A (anti-cheat hardcap). Дефолт
    `AuditSource.UNKNOWN` — для бэк-совместимости со старыми вызовами;
    в Спринте 1.6.F все use-cases будут переведены на явное указание
    источника через `progression.add_length(...)`.

    `clamped_from` — `None`, если дельта не клампилась; число (исходная
    запрошенная дельта в см), если `progression.add_length` подрезал
    её под `daily_cap_cm` / `weekly_cap_cm`. Заполняется только в
    Спринте 1.6.D; до этого всегда `None`.

    `delta_cm` — фактически применённая дельта длины (знаковая, в см).
    `None` для не-длиновых событий (`clan_register`, `balance_reload`,
    `player_locale_set` и т. п.). Anti-cheat rolling-окно (Спринт 1.6.C)
    суммирует `delta_cm > 0` с фильтром по `source IN organic_sources`.
    Заполняется в Спринте 1.6.D через `progression.add_length`; до того
    момента старые `LENGTH_GRANT`-вызовы в `RegisterPlayer`/`InvokeOracle`/
    `FinishForestRun` явно прокидывают `delta_cm` для интеграции с anti-cheat.
    """

    action: AuditAction
    actor_id: int | None
    target_kind: str
    target_id: str
    before: dict[str, object] | None
    after: dict[str, object] | None
    reason: str
    idempotency_key: str | None
    occurred_at: datetime
    source: AuditSource = AuditSource.UNKNOWN
    clamped_from: int | None = None
    delta_cm: int | None = None


class IAuditLogger(abc.ABC):
    """Интерфейс аудит-логгера."""

    @abc.abstractmethod
    async def record(self, entry: AuditEntry) -> None:
        """Записать одно событие.

        Вызывается из use-case **внутри** транзакции (`IUnitOfWork`).
        Любая ошибка записи аудита откатывает всю операцию — это by design.
        """
