# AGENT_HANDOFF — Спринт 4.1-C «Лот-генератор + крипто-приз в рулетке»

> Sticky safety-net документ. Живёт в feature-ветке всё время активной работы.
> Обновляется **в том же коммите**, что и функциональные изменения (не отдельным `chore`-коммитом).
> Удаляется **отдельным коммитом** `chore: remove AGENT_HANDOFF before PR` **до** открытия PR.

## Состояние на этом коммите

- **Ветка:** `devin/1778438123-sprint-4-1-C-lot-generator` (от `main = 93148aa`, merge PR #130).
- **Активный шаг чек-листа:** **C.0** — `current_tasks.md` под старт 4.1-C + создание этого `AGENT_HANDOFF.md`.
- **Готовы:** -.
- **В работе:** C.0 (планирование + snapshot pivot).
- **Дальше:** C.1 — Domain `PrizeLot` aggregate + VO `FeeBufferAmount` + ports + errors.

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
7. **Pattern для audit-source расширения** (см. Alembic `0028`):
   - Расширяй `AuditSource` enum в `domain/shared/ports/audit.py`.
   - Отдельная миграция `0030_audit_source_prize_lot_*` через `op.batch_alter_table` (SQLite-совместимо).
   - Обнови `_SOURCE_WHITELIST` и `_PREV_SOURCE_WHITELIST` в миграции.
8. **Pattern для picker крипто-приза** (см. `domain/roulette/services.py`):
   - `pick_paid_outcome(*, config, random, crypto_pool_empty)` — сейчас `crypto_pool_empty=True` всегда.
   - В 4.1-C нужно превратить `bool` в реальный сигнал: `crypto_pool_empty = not active_lots_for(currency)`.
   - Или ввести `active_lots: Sequence[PrizeLot]` параметр и возвращать `RouletteOutcome(kind=CRYPTO_LOT, lot_id=...)`. **Открытый вопрос.**

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
