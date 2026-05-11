# AGENT_HANDOFF — Спринт 4.1-C «Лот-генератор + крипто-приз в рулетке»

> Sticky safety-net документ. Живёт в feature-ветке всё время активной работы.
> Обновляется **в том же коммите**, что и функциональные изменения (не отдельным `chore`-коммитом).
> Удаляется **отдельным коммитом** `chore: remove AGENT_HANDOFF before PR` **до** открытия PR.

## Состояние на этом коммите

- **Ветка:** `devin/1778438123-sprint-4-1-C-lot-generator` (от `main = 93148aa`, merge PR #130).
- **Активный шаг чек-листа:** **C.7.a** — `InMemoryFeeEstimator` (constants per currency: STARS = 0, TON_NANO ≈ 100_000_000 ≈ 0.1 TON, USDT_DECIMAL ≈ 1_000_000 = 1 USDT) + DI-проброс в `bot/main.py`. Сейчас `GeneratePrizeLots` принимает `IFeeEstimator` через ctor, но в composition root инжектируется заглушка/нет инжекта — нужно реализовать конкретный класс в `infrastructure/` и подключить в bot/main. Unit-тест `test_in_memory_fee_estimator.py` — 3 валюты, проверка возвращаемых значений.
- **Готовы:** C.0 (snapshot pivot + sticky HANDOFF), C.1 (Domain `PrizeLot` aggregate + VO `FeeBufferAmount` + ports + errors + 67 unit-тестов), C.2 (Application use-case `GeneratePrizeLots` + 41 unit-тестов + Alembic 0029 audit-source `prize_lot_generated`), C.3 (Alembic `0030_prize_lots` + `PrizeLotORM` + `SqlAlchemyPrizeLotRepository` + 33 integration-тестов), C.4 (`AuditAction.PRIZE_LOT_REFUNDED` + `AuditSource.PRIZE_LOT_REFUNDED` + Alembic `0031_audit_source_prize_lot_refunded`), C.5 (picker `active_lots: Sequence[PrizeLot]` + `RouletteOutcome.crypto_lot(lot_id)` + invariants `kind == CRYPTO_LOT ⇔ lot_id >= 1` + 25 новых unit-тестов + use-case-ы прокинуты с `active_lots=()` на C.5), C.6.a (`AuditAction.PRIZE_LOT_RESERVED` + `AuditSource.PRIZE_LOT_RESERVED` + Alembic `0032_audit_source_prize_lot_reserved`), C.6.b (DI-параметр `prize_lots: IPrizeLotRepository` в use-case-ы спинов + `list_active(STARS)` перед picker-ом + composition root через `SqlAlchemyPrizeLotRepository`), C.6.c (happy-path резервирования: если `outcome.kind is CRYPTO_LOT` → `update_status(lot_id, RESERVED)` в той же UoW что и спин + audit `PRIZE_LOT_RESERVED` с full shape по C.6.a — free и paid), C.6.d (race-fallback: `try/except PrizeLotStatusTransitionError` вокруг `update_status` → подмена outcome через `pick_length_only_outcome(length_buckets=..., random=...)` — новый public helper в `domain/roulette/services.py`. MVP-стратегия: **сразу LengthGain-fallback**, без retry-loop — детерминистично. `FakePrizeLotRepository.raise_status_transition_on_update: bool = False` — test hook. +2 unit-теста race-fallback в free/paid), **C.6.e** (integration-тест `TestSpinFreeRouletteCryptoLotReservation::test_crypto_lot_outcome_reserves_lot_in_db_with_audit` в `tests/integration/db/test_spin_free_roulette_use_case.py` — реальный `SqlAlchemyPrizeLotRepository`, seed STARS-лот, форсировать CRYPTO_LOT-исход → проверить `prize_lots.status = "reserved"` + audit `PRIZE_LOT_RESERVED` с правильным shape. Параллельно: синхронизирован `AuditLogORM.__table_args__` whitelist в `infrastructure/db/models/security.py` с whitelist-ом Alembic-миграции 0032 — добавлены `roulette_paid_reward`, `prize_pool_increment`, `prize_lot_generated`, `prize_lot_refunded`, `prize_lot_reserved` (был баг от 4.1-A: ORM-whitelist не обновлялся, но integration-тесты до 4.1-C audit-записей с новыми source не делали).
- **В работе:** —.
- **Дальше:** C.7.b — cron 1×/час scheduler entry-point `GeneratePrizeLots` per currency; C.7.c — триггер после крупного донат-зачисления (хук в `RecordDonation` или signal-poll, см. открытый вопрос); C.7.d — composition root smoke. Далее C.8—C.11 (см. `docs/current_tasks.md`).

## Что нужно знать следующему агенту, если меня прервёт

1. **Чек-лист C.0–C.11 в `docs/current_tasks.md`** — это **гипотеза** декомпозиции от предыдущего агента. Если у тебя есть лучший взгляд — пересмотри её под свой стиль. Главное — не пропустить ни одну из 4.1.7/4.1.8 задач плана.
2. **`make ci` зелёный** на `main = 93148aa`. После любого изменения — гонять `make ci` локально перед push-ем. Coverage gate ≥ 80%, mypy `--strict`, 4 import-linter contracts.
3. **Открытые решения** (см. блок «Известные блокеры» в `current_tasks.md`):
   - C.6 — retry vs fallback при race-резервировании лота двумя игроками.
   - C.7 — хук в `RecordDonation` vs независимый poll-worker для триггера лот-генератора.
4. **Pattern для domain-агрегата** (см. `domain/monetization/entities.py::PrizePool`):
   - `@dataclass(frozen=True, slots=True)` + invariants в `__post_init__`.
   - Иммутабельный `with_*` / `apply_*` метод возвращает **новый** инстанс (старый не мутируется).
   - Errors наследуют `MonetizationDomainError` из `domain/monetization/errors.py`.
5. **Pattern для use-case** (см. `application/monetization/record_donation.py`):
   - DI-конструктор через `__init__(*, ...)` (keyword-only), все зависимости — порты.
   - `__slots__` обязательно.
   - **Не открывать UoW самим** — caller отвечает за `async with uow:`.
6. **Pattern для persistence** (см. `infrastructure/db/repositories/prize_pool.py`):
   - ORM-модель + Alembic-миграция с initial-seed.
   - Атомарные `UPDATE ... WHERE id = :id` + `SELECT *` после.
   - DB-CHECK как last-line-of-defense для domain-invariants.
7. **Pattern для audit-source расширения** (см. Alembic `0028`, `0029`):
   - Расширяй `AuditSource` enum в `domain/shared/ports/audit.py`.
   - Отдельная миграция `*_audit_source_*` через `op.batch_alter_table` (SQLite-совместимо).
   - Обнови `_SOURCE_WHITELIST` и `_PREV_SOURCE_WHITELIST` в миграции.
   - Обнови `tests/unit/domain/shared/ports/test_audit_source.py` (`_load_migration_whitelist` указывает на последнюю расширяющую миграцию).
   - Обнови `tests/integration/db/test_migrations.py` (`test_<NNNN>_descends_from_<NNNN-1>` + `test_versions_dir_lists_only_known_files`).
8. **Pattern для picker крипто-приза** (см. `domain/roulette/services.py`):
   - `pick_paid_outcome(*, config, random, active_lots: Sequence[PrizeLot])` и `pick_roulette_outcome(*, config, random, active_lots)` — `crypto_pool_empty` был заменён на `len(active_lots) == 0` в C.5.
   - Если weighted-choice выбрал `CRYPTO_LOT`: helper `_roll_crypto_lot(active_lots, random)` выбирает лот через `random.choice(active_lots)` и возвращает `RouletteOutcome.crypto_lot(lot_id=chosen.id)`. Если `chosen.id is None` (нарушен контракт `IPrizeLotRepository.list_active`) — `InvalidRouletteConfigError`.
   - Если `active_lots` пуст: `CRYPTO_LOT` исключается из взвешенного выбора через `_roll_kind` (вес перетекает в `LENGTH` — как в 4.1-A).
   - `RouletteOutcome` инварианты (`__post_init__`): `kind == CRYPTO_LOT ⇔ lot_id >= 1`, `kind == LENGTH ⇔ length_cm >= 1`, прочие kind-ы — `lot_id is None` и `length_cm is None`. Фабрика: `RouletteOutcome.crypto_lot(lot_id=...)`.
   - **C.6:** use-case `SpinPaidRoulette` / `SpinFreeRoulette` сейчас вызывают picker с `active_lots=()` (срабатывает fallback). В C.6 нужно прокинуть `IPrizeLotRepository.list_active(currency)` + после picker-а `update_status(lot_id, ACTIVE → RESERVED)` + audit `PRIZE_LOT_RESERVED`. Race-fallback — всё ещё открыт (retry vs LengthGain).
9. **C.2 итог** (готов в этом коммите):
   - `application/monetization/generate_prize_lots.py::GeneratePrizeLots` — use-case класс с DI-конструктором (`uow`, `prize_pool_repository`, `prize_lot_repository`, `fee_estimator`, `audit_logger`, `idempotency`, `clock`), `execute(GeneratePrizeLotsCommand)` → `GeneratePrizeLotsResult`. Открывает UoW самостоятельно (top-level, как `SpinPaidRoulette`).
   - Алгоритм: idempotency-root `prize_lot_generator:<currency>|<key>` → проверка `is_seen` → ранний выход с `idempotent=True`; иначе → читаем пул, выбираем `target_usd_native` (max если ≥ 10 USD, min если ≥ 1 USD, иначе `None`); estimate fee один раз; sanity check `fee >= target` → 0 лотов; while `free_balance ≥ lot_amount` → `PrizeLot.freshly_generated()` + repo.add + pool.apply_increment(-lot_amount) + audit (per lot, target_id = `<root>:lot:<idx>`); `mark` idempotency; commit UoW.
   - Константы: `_MIN_USD_NATIVE` / `_MAX_USD_NATIVE` MappingProxyType per currency (STARS=100/1000, TON_NANO=500_000_000/5_000_000_000, USDT_DECIMAL=1_000_000/10_000_000) — temporary; переедут в `balance.yaml` в 4.1-D.
   - `domain/shared/ports/audit.py::AuditAction.PRIZE_LOT_GENERATED` + `AuditSource.PRIZE_LOT_GENERATED` (значения `prize_lot_generated`).
   - Alembic `0029_audit_source_prize_lot_generated` — расширение whitelist `audit_log.source`. `down_revision = 0028`.
   - 41 unit-тест в `tests/unit/application/monetization/test_generate_prize_lots.py` (max/min режим, below-min, все 3 валюты, идемпотентность, fee буфер + sanity check, audit per lot, декремент пула, UoW commit, корректная конструкция PrizeLot).
   - Fake-инфраструктура: `tests/fakes/prize_lot_repo.py::FakePrizeLotRepository`, `tests/fakes/fee_estimator.py::FakeFeeEstimator` (с дефолтным `fee=0` и `factory`/`fees`-оверрайдами).

10. **C.5 итог** (готов в этом коммите):
   - `domain/roulette/entities.py::RouletteOutcome` — новое поле `lot_id: int | None = None`. Invariant в `__post_init__`: `kind == CRYPTO_LOT ⇒ lot_id >= 1` и `length_cm is None`; `kind == LENGTH ⇒ length_cm >= 1` и `lot_id is None`; прочие kind-ы — оба `None`. Фабрика `RouletteOutcome.crypto_lot(*, lot_id: int) -> Self`.
   - `domain/roulette/services.py` — `pick_roulette_outcome` / `pick_paid_outcome` приняли `active_lots: Sequence[PrizeLot]` вместо `crypto_pool_empty: bool` (`empty` теперь = `len(active_lots) == 0`). Новый helper `_roll_crypto_lot(*, active_lots, random)` вызывает `random.choice(active_lots)` и возвращает `RouletteOutcome.crypto_lot(lot_id=chosen.id)`. Если `chosen.id is None` (нарушен контракт `IPrizeLotRepository.list_active`) — `InvalidRouletteConfigError(reason="active_lots contained a non-persisted PrizeLot (id is None)")`.
   - `application/monetization/spin_paid_roulette.py::SpinPaidRoulette` + `application/roulette/spin_free_roulette.py::SpinFreeRoulette` — call-site picker-а переведён на `active_lots=()` (поведение совпадает с прежним `crypto_pool_empty=True`). В audit-payload `ROULETTE_SPIN.after` добавлено поле `lot_id` при `outcome.lot_id is not None` (на C.5 не срабатывает, но shape готов для C.6).
   - 25 новых unit-тестов в `tests/unit/domain/roulette/test_crypto_lot_picker.py` (3 валюты `STARS` / `TON_NANO` / `USDT_DECIMAL`, single-lot pool, multi-lot determinism, uniform distribution Bernoulli-bound, empty-pool fallback, non-persisted lot defence-in-depth, mixed-currency pool, factory shape consistency).
   - 8 новых invariant-тестов в `tests/unit/domain/roulette/test_entities.py::TestRouletteOutcomeCryptoLotInvariants` (lot_id required для CRYPTO_LOT, lot_id > 0 invariant, mutual exclusion с length_cm, lot_id запрещён для не-CRYPTO_LOT kind-ов, фабрика-classmethod).
   - Обновлены `tests/unit/domain/roulette/test_picker.py` + `test_paid_picker.py` (новый helper `_dummy_lot()`, переход с `crypto_pool_empty=...` на `active_lots=...`); `tests/unit/application/roulette/test_spin_free_roulette.py` (терминология `active_lots=()`); presenter-тесты `tests/unit/bot/presenters/test_roulette.py` + `test_roulette_paid.py` (CRYPTO_LOT-outcome теперь конструируется с `lot_id=1`).
   - `make ci` зелёный: ruff ok, mypy `--strict` 0 issues в 940 source files, import-linter 4/4 kept, pytest **5641 tests** passed, coverage maintained.

11. **C.4 итог** (готов из C.4-коммита):
   - `AuditAction.PRIZE_LOT_REFUNDED = "prize_lot_refunded"` и `AuditSource.PRIZE_LOT_REFUNDED = "prize_lot_refunded"` в `domain/shared/ports/audit.py` — размечены для будущего use-case-а `RefundPrizeLot` (C.6 race-fallback + 4.1-D `ClaimPrize` timeout-refund). `target_kind="prize_lot"`, `target_id="<lot_id>:refund"`, `after={lot_id, currency, amount_native, prev_status, pool_after_native, reason}`. Не входит ни в один из anticheat-source-вайтлистов.
   - Alembic-миграция `20260510_0031_audit_source_prize_lot_refunded.py` — расширяет `audit_log_source_whitelist` вводя `prize_lot_refunded`. `down_revision = 0030`. SQLite-совместимо через `op.batch_alter_table` (drop+create CHECK).
   - Обновлен `tests/unit/domain/shared/ports/test_audit_source.py` (`_load_migration_whitelist` указывает на 0031, docstring синк-либ).
   - Обновлен `tests/integration/db/test_migrations.py` (`test_0031_descends_from_0030` + `"0031_audit_source_prize_lot_refunded"` в `expected_revisions` + `"20260510_0031_audit_source_prize_lot_refunded.py"` в versions_dir-listing).

11. **C.3 итог** (готов из C.3-коммита):
   - Alembic-миграция `20260510_0030_prize_lots.py` — `CREATE TABLE prize_lots` со всеми CHECK-инвариантами (`currency` whitelist, `amount_native >= 1`, `fee_buffer_native >= 0`, `amount_native > fee_buffer_native`, `status` whitelist, `claimed_at IFF status='claimed'`) + индекс `ix_prize_lots_status_currency`. `down_revision = 0029`. Без initial-seed-а (лоты генерятся on-demand через `GeneratePrizeLots`).
   - `infrastructure/db/models/prize_lot.py::PrizeLotORM` — SQLAlchemy 2.x `Mapped`-маппинг таблицы. Identity по автоинкрементному `id`. `BigInteger().with_variant(Integer, 'sqlite')`.
   - `infrastructure/db/repositories/prize_lot.py::SqlAlchemyPrizeLotRepository` — реализация `IPrizeLotRepository`: `add(lot)` (`session.add` + `flush` для получения `id`), `get_by_id`, `list_active(currency)` (`ORDER BY id ASC`), `update_status(...)` через атомарный `UPDATE ... WHERE id=:id AND status IN (валидные source-статусы для new_status)`. `rowcount=0` → SELECT для различения `PrizeLotNotFoundError` vs `PrizeLotStatusTransitionError`. `_ensure_utc` нормализация TZ для aiosqlite-квирка (см. `_orm_to_payment` pattern).
   - 33 integration-теста в `tests/integration/db/test_prize_lot_repository.py` (round-trip, все 3 валюты, status-machine `ACTIVE → RESERVED → CLAIMED|REFUNDED`, `list_active` фильтрация по currency и status, double-reserve race → `PrizeLotStatusTransitionError`, ACTIVE→CLAIMED skip → ошибка, terminal-status guard, `PrizeLotNotFoundError`, `update_status(ACTIVE)` → `ValueError`, claimed_at-валидация, все 7 DB-CHECK-ограничений как last-line-of-defense).
   - Обновлены `tests/integration/db/test_migrations.py` (`test_0030_descends_from_0029`, expected_revisions, versions_dir-listing, expected-tables в smoke-тесте) + `tests/integration/db/conftest.py` (импорт `PrizeLotORM` для регистрации).

12. **C.1 итог** (готов из C.1-коммита):
   - `domain/monetization/value_objects.py::FeeBufferAmount` — frozen-VO с `>= 0`-invariant.
   - `domain/monetization/entities.py::PrizeLot` — `@dataclass(frozen=True, slots=True)` с полями `(id, currency, amount_native, fee_buffer_native, status, created_at, claimed_at)`, invariants `amount_native > fee_buffer_native >= 0`, TZ-aware datetime, `id ∈ {None} ∪ ℕ+`, `status == CLAIMED ⇔ claimed_at`.
   - `PrizeLotStatus` (StrEnum: `active|reserved|claimed|refunded`) + immutable transition-методы `reserve()` / `claim(claimed_at=...)` / `refund()`, машина состояний `ACTIVE → RESERVED|REFUNDED`, `RESERVED → CLAIMED|REFUNDED`, terminal `CLAIMED|REFUNDED`. Транзишены через приватный `_PRIZE_LOT_TRANSITIONS: MappingProxyType`.
   - `domain/monetization/errors.py`: `PrizeLotInvariantError`, `PrizeLotStatusTransitionError`, `PrizeLotNotFoundError`.
   - `domain/monetization/ports.py`: `IPrizeLotRepository` (`add` / `get_by_id` / `list_active(currency)` / `update_status(lot_id, new_status, claimed_at?)`) + `IFeeEstimator` (`estimate_fee(currency, target_amount_native) -> int`).
   - `domain/monetization/__init__.py` — ре-экспорт всех новых символов.
   - 67 unit-тестов в `tests/unit/domain/monetization/test_prize_lot.py` (VO/invariants/status-machine/errors/immutability).

## Принципы коммитов на этой ветке

- Каждый шаг C.X — отдельный коммит (если CI остаётся зелёным). Если шаг ломает CI на промежутке — объедини с зависимым (как сделано B.5+B.6 — в одном коммите чтобы CI оставался зелёным).
- В каждом коммите — обнови этот `AGENT_HANDOFF.md` (отметь готовые шаги, обнови «активный шаг»).
- В каждом коммите — обнови `docs/current_tasks.md` (`[ ] → [x]` готовых шагов, обнови «Последний коммит на ветке»).
- **Контрольные точки** — push на origin после каждого коммита (на случай обрыва токенов).

## Полезные ссылки

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — «Промпт-приёмка для нового агента» (7 шагов).
- [`docs/current_tasks.md`](docs/current_tasks.md) — чек-лист C.0–C.11 + Снимок состояния.
- [`docs/development_plan.md`](docs/development_plan.md) §7 — план Фазы 4 (4.1.7, 4.1.8).
- [`docs/game_design.md`](docs/game_design.md) §12.6 — призовой пул + лот-генератор + крипто-приз.
- [`docs/history.md`](docs/history.md) — журнал завершённых спринтов (последний — 4.1-B).
