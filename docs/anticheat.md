# Анти-чит и хардкап (Спринт 1.6)

> **Контекст.** ГДД §3.3 «Анти-чит» + §18.6 «Audit и AML».
> Закрывающий план: `docs/development_plan.md` §4 (Спринт 1.6,
> ПД 1.6.1 — 1.6.10).

Этот документ — onboarding для разработчика, который подключается
к проекту после Спринта 1.6 и должен уметь:
1. Понять, как устроен hardcap и trip-wire.
2. Добавить новый источник прибавки длины (`AuditSource`).
3. Вручную снять soft-ban игроку.

## 1. Архитектурный обзор

### Единая точка прибавки длины — `progression.add_length`

Любая прибавка длины игроку проходит через
[`AddLength`](../src/pipirik_wars/application/progression/add_length.py)
(реализация порта
[`ILengthGranter`](../src/pipirik_wars/domain/progression/length_granter.py)).

Прямые `player.with_length(...)` + `repo.save(player)` вне `AddLength`
запрещены — `tests/unit/architecture/test_length_granter_only.py`
сканит `src/` и заставляет CI падать на любой обход. Architecture-
guard добавлен в Спринт 1.6.F.

Ambient-UoW: caller обязан открыть `async with uow:` сам, потом
звать `await length_granter.grant(...)`. `AddLength.grant(...)` без
открытого `IUnitOfWork`-контекста бросает `RuntimeError`. Это нужно,
чтобы вся прибавка (mutate + audit + trip-wire) и «бизнес-вставки»
вызывающего use-case-а (`oracle_invocations.add(...)`,
`forest_runs.save(...)`) были в одной транзакции.

### Алгоритм `AddLength.grant(...)`

Внутри открытого `IUnitOfWork`-контекста:

1. **Валидация входа.**
   - `source = AuditSource.UNKNOWN` → `LengthDeltaInvalidError`
     (backfill-маркер, не реальный источник).
   - `delta_cm = 0` → `LengthDeltaInvalidError`.
   - `delta_cm < 0` для не-`admin_refund` → `LengthDeltaInvalidError`.
   - `delta_cm > 0` для `admin_refund` → `LengthDeltaInvalidError`
     (refund — это сторно, должно быть отрицательным).
2. **Идемпотентность.** Если `idempotency_key` передан и виден
   `IIdempotencyKey` → no-op (`applied_delta_cm=0`,
   `triggered_soft_ban=False`).
3. **Загрузка игрока.** `players.get_by_id(...)` →
   `PlayerNotFoundError`, если нет.
4. **Soft-ban-гейт.** `player.is_anticheat_banned(now)` →
   `AnticheatSoftBanError`. Транзакция откатывается.
5. **Clamp (только для organic).** `daily =
   anticheat.sum_organic_in_window(since=now-24h, ...)`,
   `weekly = anticheat.sum_organic_in_window(since=now-7d, ...)`,
   `remaining = min(daily.remaining_cap_cm(daily_cap),
   weekly.remaining_cap_cm(weekly_cap))`,
   `applied = min(delta, remaining)`. Donate / `admin_refund` —
   passthrough.
6. **Mutate.** `player.with_length(length + applied)` →
   `players.save(...)`.
7. **Audit `LENGTH_GRANT`.** `AuditEntry(action=LENGTH_GRANT,
   source=source, delta_cm=applied, clamped_from=clamped_from, ...)`.
8. **Idempotency-mark.** Если `idempotency_key` есть.
9. **Trip-wire** (только organic + `applied > 0`). Рекомпьют
   `daily_after` / `weekly_after` (включая только что записанный
   delta — `SqlAlchemyAuditLogger.flush()` делает это видимым в той
   же транзакции). Если `is_exceeded(cap)` → `player.with_anticheat_ban(
   until=now + soft_ban_duration_days)` + `players.save(...)` +
   audit `ANTICHEAT_DAILY_CAP_EXCEEDED` /
   `ANTICHEAT_WEEKLY_CAP_EXCEEDED` + alert админу через
   `IAnticheatAdminAlerter`.

### Конфигурация

`balance.yaml` секция `anticheat`
([`BalanceConfig`](../src/pipirik_wars/domain/balance/config.py),
Спринт 1.6.B):

```yaml
anticheat:
  daily_cap_cm: 3000
  weekly_cap_cm: 14000
  soft_ban_duration_days: 14
  organic_sources:
    - forest
    - oracle
    - referral_signup
    - raid_reward
    - admin_grant
  donate_sources:
    - stars_payment
    - ton_payment
    - usdt_payment
```

Инварианты (`AnticheatConfig`-pydantic):
- `daily_cap_cm ≤ weekly_cap_cm`.
- `organic_sources ∩ donate_sources = ∅`.
- В каждом списке нет дублей.
- `unknown` запрещён в обоих.
- `admin_refund` запрещён в `organic_sources`.

Hot-reload через `/balance_reload` (super_admin) — изменение
`daily_cap_cm` без рестарта бота.

### Rolling-окно

`IAnticheatRepository.sum_organic_in_window(player_id, since,
organic_sources)` — один `SELECT` по `audit_log` с фильтром:
`target_kind='player' AND target_id=:pid AND source IN (...) AND
delta_cm > 0 AND occurred_at >= since`.

Используется rolling-окно (`since = now - 24h` / `now - 7d`), а не
календарный сброс в полночь. Это защищает от обхода через границу
суток («2999 в 23:59 → 2999 в 00:01 = 6000 за 2 минуты»).

### Trip-wire vs clamp

- **Clamp** — штатный путь. На каждом organic-grant-е читается
  `sum_organic_in_window`, дельта прижимается к
  `cap - already_consumed`. Игрок не замечает (получил «N см»).
- **Trip-wire** — «второй эшелон» защиты. Срабатывает, если в
  trip-wire-recompute суммарная organic-дельта **превысила** cap
  (например, на гонке нескольких параллельных grant-ов или
  при clamp-bug-е). Ставит soft-ban на 14 дней + audit
  `ANTICHEAT_*_CAP_EXCEEDED` + Telegram-alert админу.

Под Postgres + REPEATABLE READ + SELECT FOR UPDATE на user-row
(см. ниже §6) clamp + trip-wire вместе гарантируют «суточная сумма
≤ 3000» — это и есть acceptance ПД 1.6.9. Под SQLite (test-only)
clamp может проиграть гонку lost-update-у, но trip-wire всё равно
ставит ban.

### Snapshot-test инвариантов

- `tests/integration/load/test_anticheat_concurrent.py` —
  100 параллельных grant-ов одного игрока. Проверяет: либо clamp
  удержал в cap-е, либо trip-wire среагировал и записал `ANTICHEAT_
  DAILY_CAP_EXCEEDED` + Telegram-alert. Без assertion на «строгую
  сумму ≤ 3000» — это Postgres-only invariant.
- `tests/unit/application/progression/test_add_length.py` —
  21 юнит-тест (clamp, soft-ban, trip-wire, идемпотентность,
  edge-cases admin_refund / unknown).

## 2. Как добавить новый source

Допустим, добавляем `dungeon_reward` (organic-источник прибавки
из нового активити «подземелье»).

1. **Enum.** Добавь значение в
   [`AuditSource`](../src/pipirik_wars/domain/shared/ports/audit.py):

   ```python
   class AuditSource(StrEnum):
       ...
       DUNGEON_REWARD = "dungeon_reward"
   ```

2. **Миграция.** Расширь whitelist `audit_log.source` миграцией
   (см. `0007_anticheat_foundation` как образец). Создай новую
   `XXXX_extend_audit_source.py` с
   `op.execute("ALTER TABLE audit_log DROP CONSTRAINT
   audit_log_source_check")` + `CREATE CONSTRAINT ... CHECK (source
   IN (..., 'dungeon_reward'))`. Drift-тест в
   `tests/integration/db/test_migrations.py` сравнит enum vs
   whitelist миграции.

3. **Конфиг.** Реши: organic или donate. Для organic-источника
   добавь в `balance.yaml`:

   ```yaml
   anticheat:
     organic_sources:
       - forest
       - oracle
       - referral_signup
       - raid_reward
       - admin_grant
       - dungeon_reward  # ← новый
   ```

   Pydantic-инварианты не дадут добавить в обе списка одновременно
   или продублировать.

4. **Use-case.** В новом use-case-е (`StartDungeonRun` →
   `FinishDungeonRun` / напрямую `GrantDungeonReward`) звани
   `length_granter.grant(...)`:

   ```python
   await self._length_granter.grant(
       player_id=player.id,
       delta_cm=reward_cm,
       source=AuditSource.DUNGEON_REWARD,
       reason=f"dungeon_run:{run_id}",
       idempotency_key=f"dungeon_reward:{run_id}",
   )
   ```

   ⚠️ Architecture-guard (1.6.F) **не разрешит** прямой
   `player.with_length(...)` + `repo.save(...)` в `src/` — CI упадёт
   на `tests/unit/architecture/test_length_granter_only.py`.

5. **Тесты.**
   - Юнит-тест на сам use-case (mocked `ILengthGranter`).
   - Параметризованный кейс в
     `tests/unit/application/progression/test_add_length.py` на
     новый source — проверить clamp-поведение для organic или
     passthrough для donate.

6. **Локализация.** Если нужны новые сообщения игроку (например,
   «Вы прошли подземелье и получили N см»), добавь ключи в
   `locales/{ru,en}.ftl` и используй через `IMessageBundle`-bundle
   (паттерн 1.5.B).

## 3. Как вручную снять soft-ban

### Через бот-команду (рекомендованный путь)

[`/anticheat_unban <tg_id> <reason>`](../src/pipirik_wars/bot/handlers/admin.py)
(Спринт 1.6.G). Только в ЛС, только активный `super_admin`.

```
/anticheat_unban 12345 false-positive: legitimate donate burst
```

Алгоритм
([`LiftAnticheatBan`](../src/pipirik_wars/application/anticheat/lift_ban.py)):
- Проверяет `Admin.can_lift_anticheat_ban()` (только super_admin) →
  `AuthorizationError` иначе.
- Грузит игрока по `tg_id` → `PlayerNotFoundError` иначе.
- Если бан уже не активен (None или истёк) — идемпотентный no-op
  без audit-записи (минимизируем шум в логе).
- Иначе: `player.with_anticheat_ban_lifted(now)` →
  `players.save(...)` → audit `ANTICHEAT_BAN_LIFTED` с
  `before/after.anticheat_ban_until`, `actor_id=admin.id`,
  `reason=<reason>`, `idempotency_key=anticheat_unban:<actor>:<target>:<ts>`.

⚠️ **`reason` обязателен** (требование ГДД §18.6 — каждый
admin-action оставляет след). Пустой reason → use-case бросит
`ValueError`, handler отрисует `anticheat-unban-usage`.

### Через прямой SQL (если бот лежит)

```sql
-- 1. Снимаем поле.
UPDATE users
SET anticheat_ban_until = NULL,
    updated_at          = NOW()
WHERE tg_id = <target_tg_id>;

-- 2. Записываем audit (НЕ ПРОПУСКАТЬ — ГДД §18.6 требует,
-- чтобы любое admin-действие оставляло audit-след).
INSERT INTO audit_log (
    occurred_at, action, actor_id, target_kind, target_id,
    before, after, reason, source, idempotency_key
)
VALUES (
    NOW(),
    'ANTICHEAT_BAN_LIFTED',
    <admin_id>,                                  -- из таблицы admins
    'player',
    (SELECT id::text FROM users WHERE tg_id = <target_tg_id>),
    jsonb_build_object('anticheat_ban_until', '<old_iso_ts>'),
    jsonb_build_object('anticheat_ban_until', NULL),
    '<reason>',
    'unknown',                                   -- backfill-маркер для ручного действия
    'manual_unban:<target_tg_id>:' || EXTRACT(EPOCH FROM NOW())::bigint
);
```

### Список забаненных игроков

```sql
SELECT id, tg_id, username, length_cm, anticheat_ban_until
FROM users
WHERE anticheat_ban_until > NOW()
ORDER BY anticheat_ban_until DESC;
```

### История trip-wire-событий игрока

```sql
SELECT occurred_at, action, source, delta_cm, clamped_from, reason
FROM audit_log
WHERE target_kind = 'player'
  AND target_id   = (SELECT id::text FROM users WHERE tg_id = <target_tg_id>)
  AND action IN (
      'ANTICHEAT_DAILY_CAP_EXCEEDED',
      'ANTICHEAT_WEEKLY_CAP_EXCEEDED',
      'ANTICHEAT_BAN_LIFTED'
  )
ORDER BY occurred_at DESC;
```

## 4. Локализация (Спринт 1.6.D / 1.6.G)

Все игрок-видимые сообщения — через `IMessageBundle.format(...)`.

- `anticheat-soft-ban-active` — игрок в soft-ban-е («Вы временно
  ограничены до {banned-until}, обратитесь к админам»).
- `anticheat-cap-clamped-daily` — clamp по суточному cap-у.
- `anticheat-cap-clamped-weekly` — clamp по недельному cap-у.
- `anticheat-unban-usage` / `-not-authorized` / `-player-not-found`
  / `-not-banned` / `-success` — ответы `/anticheat_unban`-handler-а
  (Спринт 1.6.G).

Telegram-alert админу при срабатывании trip-wire — пока через
[`StructlogAnticheatAdminAlerter`](../src/pipirik_wars/infrastructure/anticheat/admin_alerter.py)
(пишет structlog-event). Когда появится Telegram-канал админ-алёртов
— перевести на `TelegramAnticheatAdminAlerter` + ключ
`anticheat-admin-alert` в `.ftl`.

## 5. Связанная история

- **1.6.A** (PR #34) — миграция `0007_anticheat_foundation`, enum
  `AuditAction.ANTICHEAT_*`, поля `users.anticheat_ban_until` /
  `audit_log.source` / `clamped_from`, domain-методы `Player.with_anticheat_ban`.
- **1.6.B** (PR #35) — `AnticheatConfig` в `balance.yaml`.
- **1.6.C** (PR #36) — `IAnticheatRepository` + миграция
  `0008_audit_log_delta_cm`.
- **1.6.D** (PR #37) — `AddLength` use-case + clamp + trip-wire.
- **1.6.E** (PR #39) — `AnticheatGuard` для «спендалок» (`/upgrade`).
- **1.6.F** (PR #42) — миграция `FinishForestRun` / `InvokeOracle`
  на `ILengthGranter` + architecture-guard.
- **1.6.G** (PR #43) — `/anticheat_unban` admin-команда +
  `LiftAnticheatBan` use-case.
- **1.6.H** (текущий PR) — нагрузочный race-test + этот документ.

## 6. Известные ограничения / TODO

- **Snapshot isolation в SQLite-тестах.** Под SQLite + aiosqlite
  параллельные `AddLength.grant(...)`-вызовы могут проиграть
  lost-update-гонку на `users.length_cm` (BEGIN DEFERRED + читают
  один и тот же snapshot). На проде (Postgres + REPEATABLE READ +
  `SELECT … FOR UPDATE` на `users`-row) это не проблема. Если
  переключаемся на Postgres-integration-тесты — `SELECT FOR UPDATE`
  на `players.get_by_id` нужно явно добавить в
  `SqlAlchemyPlayerRepository`.
- **Authz transaction.** `SetMaxDau` и `ReloadBalance` (Спринт 1.5)
  делают `admins.get_by_tg_id(...)` ДО `async with self._uow:`. На
  проде это упадёт на `RuntimeError("UnitOfWork is not entered")` —
  `SqlAlchemyAdminRepository.get_by_tg_id` тянет `uow.session`. В
  `LiftAnticheatBan` (1.6.G) UoW открыт первой строкой; существующие
  use-cases оставлены как есть. Тикет-преемник: «починить admin
  authz-flow для SqlAlchemy-репозитория».
- **`anticheat-admin-alert` локаль.** Зарезервирована, но пока не
  используется (`StructlogAnticheatAdminAlerter` не локализуется).
  Будет добавлена при появлении Telegram-канала админ-алёртов.
