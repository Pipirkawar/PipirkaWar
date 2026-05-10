# AGENT_HANDOFF — Спринт 4.1-C «Лот-генератор + крипто-приз в рулетке»

> Sticky safety-net документ. Живёт в feature-ветке всё время активной работы.
> Обновляется **в том же коммите**, что и функциональные изменения (не отдельным `chore`-коммитом).
> Удаляется **отдельным коммитом** `chore: remove AGENT_HANDOFF before PR` **до** открытия PR.

## Состояние на этом коммите

- **Ветка:** `devin/1778438123-sprint-4-1-C-lot-generator` (от `main = 93148aa`, merge PR #130).
- **Активный шаг чек-листа:** **C.3** — Persistence `prize_lots` + Alembic 0030 + ORM + repo + integration-тесты.
- **Готовы:** C.0 (snapshot pivot + sticky HANDOFF), C.1 (Domain `PrizeLot` aggregate + VO `FeeBufferAmount` + ports + errors + 67 unit-тестов), C.2 (Application use-case `GeneratePrizeLots` + 41 unit-тестов + Alembic 0029 audit-source `prize_lot_generated`).
- **В работе:** —.
- **Дальше:** C.3 — ORM-модель + Alembic-миграция `0030_prize_lots` (таблица `prize_lots` с CHECK-инвариантами) + `SqlAlchemyPrizeLotRepository` + integration-тесты.

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
   - `pick_paid_outcome(*, config, random, crypto_pool_empty)` — сейчас `crypto_pool_empty=True` всегда.
   - В 4.1-C нужно превратить `bool` в реальный сигнал: `crypto_pool_empty = not active_lots_for(currency)`.
   - Или ввести `active_lots: Sequence[PrizeLot]` параметр и возвращать `RouletteOutcome(kind=CRYPTO_LOT, lot_id=...)`. **Открытый вопрос.**
9. **C.2 итог** (готов в этом коммите):
   - `application/monetization/generate_prize_lots.py::GeneratePrizeLots` — use-case класс с DI-конструктором (`uow`, `prize_pool_repository`, `prize_lot_repository`, `fee_estimator`, `audit_logger`, `idempotency`, `clock`), `execute(GeneratePrizeLotsCommand)` → `GeneratePrizeLotsResult`. Открывает UoW самостоятельно (top-level, как `SpinPaidRoulette`).
   - Алгоритм: idempotency-root `prize_lot_generator:<currency>|<key>` → проверка `is_seen` → ранний выход с `idempotent=True`; иначе → читаем пул, выбираем `target_usd_native` (max если ≥ 10 USD, min если ≥ 1 USD, иначе `None`); estimate fee один раз; sanity check `fee >= target` → 0 лотов; while `free_balance ≥ lot_amount` → `PrizeLot.freshly_generated()` + repo.add + pool.apply_increment(-lot_amount) + audit (per lot, target_id = `<root>:lot:<idx>`); `mark` idempotency; commit UoW.
   - Константы: `_MIN_USD_NATIVE` / `_MAX_USD_NATIVE` MappingProxyType per currency (STARS=100/1000, TON_NANO=500_000_000/5_000_000_000, USDT_DECIMAL=1_000_000/10_000_000) — temporary; переедут в `balance.yaml` в 4.1-D.
   - `domain/shared/ports/audit.py::AuditAction.PRIZE_LOT_GENERATED` + `AuditSource.PRIZE_LOT_GENERATED` (значения `prize_lot_generated`).
   - Alembic `0029_audit_source_prize_lot_generated` — расширение whitelist `audit_log.source`. `down_revision = 0028`.
   - 41 unit-тест в `tests/unit/application/monetization/test_generate_prize_lots.py` (max/min режим, below-min, все 3 валюты, идемпотентность, fee буфер + sanity check, audit per lot, декремент пула, UoW commit, корректная конструкция PrizeLot).
   - Fake-инфраструктура: `tests/fakes/prize_lot_repo.py::FakePrizeLotRepository`, `tests/fakes/fee_estimator.py::FakeFeeEstimator` (с дефолтным `fee=0` и `factory`/`fees`-оверрайдами).

10. **C.1 итог** (готов из C.1-коммита):
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
