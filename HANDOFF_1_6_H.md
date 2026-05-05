# HANDOFF: Спринт 1.6.H (load-test + docs/anticheat.md)

> **Для следующего агента.** Этот файл создан на ветке
> `devin/1777992466-sprint-1-6h-load-test`. Удали его в финальном
> коммите перед открытием PR (см. `Заключительные шаги` в конце).

---

## 1. Контекст

PR #43 (Спринт **1.6.G** — `/anticheat_unban`) смержён в `main`.
Это **последний открытый сабспринт** анти-чит-эпика 1.6 — задачи
1.6.9 + 1.6.10 из `docs/development_plan.md` §4. После него закрывается
весь Спринт 1.6 и можно переходить к Спринту 1.7 (см. `current_tasks.md`,
строка с `1.6.H ⚪ бэклог`).

Ветка `devin/1777992466-sprint-1-6h-load-test` отбита от `main` (после
PR #43 merge); пока в ней пусто, кроме этого HANDOFF-файла. Все 1451
тестов (`pytest tests/unit -q --no-cov` + `pytest tests/integration -q
--no-cov`) на main зелёные.

## 2. Что нужно сделать

### 2.1. Интеграционный нагрузочный тест (ПД 1.6.9)

**Файл:** `tests/integration/load/test_anticheat_concurrent.py`

**Цель.** Проверить, что 100 параллельных `progression.add_length(...)`
для одного игрока с organic-источником **не пробивают `daily_cap_cm`** —
либо clamp-логика прижимает суммарную дельту к 3000, либо trip-wire
ставит soft-ban и последующие grant-ы получают `AnticheatSoftBanError`.

**Acceptance (ПД §4 → 1.6.9):** «суточная сумма ≤ 3000, ни одна транзакция
не «прорывает» лимит».

**Эталон-фикстура.** `tests/integration/load/conftest.py` уже даёт
`shared_session_maker` поверх **файлового** SQLite + `timeout=30s`
для aiosqlite — каждая корутина получает свой `SqlAlchemyUnitOfWork`,
БД одна. Не дёргай `:memory:` через `StaticPool` (сейчас у нас
есть это для других целей в `tests/integration/db/conftest.py`,
но это маскирует race-условия — все сессии видят одну транзакцию).

**Эталон-тест.** `tests/integration/load/test_forest_concurrent.py`
(Спринт 1.4.D, ПД 1.4.7). Скопируй его структуру:

- `_seed_player(...)` — заводит одного player-а в отдельном UoW.
- `_build_use_case(uow)` — фабрика свежего use-case-а под собственный
  UoW, чтобы каждая корутина имитировала отдельный bot-update.
- Класс `TestAnticheatConcurrentLoad` помечен `@pytest.mark.slow` и
  `@pytest.mark.asyncio` (фикстуры `shared_session_maker`).

### 2.2. Сборка `AddLength` для load-теста

`AddLength` (см. `src/pipirik_wars/application/progression/add_length.py`)
требует:

```python
AddLength(
    uow=uow,
    players=SqlAlchemyPlayerRepository(uow=uow),
    anticheat=SqlAlchemyAnticheatRepository(uow=uow),
    audit=SqlAlchemyAuditLogger(uow=uow),
    balance=balance,                  # см. ниже
    clock=RealClock(),
    idempotency=SqlAlchemyIdempotencyKey(uow=uow),
    admin_alerter=admin_alerter,      # см. ниже
)
```

**Balance-config.** Можно взять `FakeBalanceConfig(build_valid_balance())`
из `tests/unit/domain/balance/factories.py` — там уже корректный
`anticheat`-блок: `daily_cap_cm=3000`, `weekly_cap_cm=14000`,
`organic_sources` включает `forest` / `oracle` / `referral_signup` /
`raid_reward` / `admin_grant`, `donate_sources` — `stars_payment` и др.

**`admin_alerter`.** Бери `tests.fakes.FakeAnticheatAdminAlerter`
(он накапливает `events`-list — пригодится для assert-а). НЕ
используй `StructlogAnticheatAdminAlerter` — он шумит в test-output
и не даёт ассертить факт алёрта.

**`SqlAlchemyAuditLogger`.** ⚠️ В `add_length.py` есть зависимость от
`audit_log` ↔ `anticheat_repo` для trip-wire-recompute. Проверь,
что `SqlAlchemyAuditLogger` **сразу** (в той же транзакции) делает
`session.flush()` перед записью audit-события — иначе trip-wire
рекомпьют не увидит только что записанную дельту. Юнит-тесты используют
`_LinkedAuditLogger`-обёртку, которая делает то же самое в памяти
(см. `tests/unit/application/progression/test_add_length.py`, строки
86-121). Скорее всего `SqlAlchemyAuditLogger.record(...)` уже flush-ит;
если нет — это будет проявляться как «trip-wire не срабатывает на load-
тесте». Не патчь это в скоупе 1.6.H — отдельный тикет.

### 2.3. Тест-кейсы

Минимум **два** теста в классе:

#### `test_100_parallel_grants_for_same_player_do_not_break_daily_cap`

```text
- Seed: 1 player с length=100, тест-clock = NOW (фикс).
- Action: 100 корутин делают grant(player_id=1, delta_cm=50,
  source=AuditSource.FOREST, reason="forest-load-test").
- Использовать `await asyncio.gather(*[attempt() for _ in range(100)])`,
  каждая корутина получает свой UoW.
- Каждая корутина внутри открывает `async with uow:` и зовёт
  `await use_case.grant(...)`, ловит `AnticheatSoftBanError` →
  возвращает «soft_banned».
- Ожидаем: total_applied = sum(r.applied_delta_cm for r in results)
  ДОЛЖЕН быть ≤ 3000. Если в результатах есть `triggered_soft_ban=True`
  — это нормальное поведение (trip-wire сработал, последующие grant-ы
  отбиты на soft-ban-гейте).
- Проверка БД: SELECT SUM(delta_cm) FROM audit_log WHERE
  action='LENGTH_GRANT' AND target_id='<pid>' AND source='forest'
  → должен быть ≤ 3000.
- Проверка player.length: SELECT length_cm FROM users WHERE id=<pid>
  → length = 100 + total_applied ≤ 3100.
- Проверка: либо нет ANTICHEAT_DAILY_CAP_EXCEEDED audit-записи (clamp
  отработал чисто), либо ровно одна (trip-wire сработал один раз —
  на момент превышения cap-а).
```

#### `test_100_parallel_grants_for_different_players_each_get_full_delta`

Контрольный сценарий: 100 разных игроков, каждый делает 1 grant
delta=50 → у каждого total_applied=50, никаких clamp/ban. Проверяет,
что cap считается per-player, а не глобально.

```text
- Seed: 100 игроков (tg_id=1000..1099).
- Action: 100 корутин, у каждой свой UoW + свой use-case.
- Ожидаем: 100 успехов, у каждого результата `applied_delta_cm=50`,
  `triggered_soft_ban=False`, `clamped_from=None`.
- Проверка БД: 100 LENGTH_GRANT-записей (по одной на игрока).
```

### 2.4. `docs/anticheat.md` (ПД 1.6.10)

**Цель.** Onboarding-документ для нового разработчика. Минимум
3 раздела:

1. **Архитектурный обзор.** `AddLength` (`ILengthGranter`) — единая
   точка прибавки длины. Clamp по `daily_cap_cm` / `weekly_cap_cm`.
   Trip-wire после save: рекомпьют окна, при превышении — soft-ban
   на 14 дней + audit `ANTICHEAT_*_CAP_EXCEEDED` + alert админу.
   Ссылки на:
   - `src/pipirik_wars/application/progression/add_length.py`
   - `src/pipirik_wars/domain/progression/length_granter.py`
   - `src/pipirik_wars/domain/anticheat/`
   - ГДД §3.3 / §18.6, `development_plan.md` §4 (1.6.1–1.6.10).

2. **Как добавить новый source.** Шаги:
    1. Добавить значение в `AuditSource`-enum в
       `src/pipirik_wars/domain/shared/ports/audit.py`.
    2. Добавить значение в whitelist миграции
       `0007_anticheat_foundation` (или новая миграция, если уже
       выкачено в прод).
    3. Решить: organic или donate. Добавить в
       `balance.yaml::anticheat.organic_sources` или `donate_sources`
       (см. `BalanceConfig`-инварианты в 1.6.B: пересечение запрещено,
       `unknown` запрещён в обоих, `admin_refund` запрещён в organic).
    4. Все use-cases прибавки должны звать `progression.add_length(...)`
       с новым `source`. Architecture-guard (Спринт 1.6.F) автоматически
       заблокирует прямые `player.with_length(...)` + save в src/.
    5. Тест: добавить в `tests/unit/application/progression/test_add_length.py`
       параметризованный кейс на новый source (clamp-поведение для organic
       или passthrough для donate).

3. **Как вручную снять soft-ban.** Спринт 1.6.G — `/anticheat_unban
   <tg_id> <reason>`:
    - Только активный `super_admin` (см. `Admin.can_lift_anticheat_ban`).
    - Reason обязателен (попадает в `audit_log.reason`).
    - Если бан уже не активен — идемпотентный no-op без audit-записи.
    - Алгоритм пишет audit `ANTICHEAT_BAN_LIFTED` с
      `before/after.anticheat_ban_until`, `actor_id=admin.id`,
      `idempotency_key=anticheat_unban:<actor>:<target>:<ts>`.
    - Через SQL (если бот лежит): `UPDATE users SET anticheat_ban_until=NULL
      WHERE tg_id=<...>` + ручная INSERT-запись в `audit_log` с
      action=`ANTICHEAT_BAN_LIFTED` (см. ГДД §18.6 — все админ-действия
      должны оставлять audit-след).

**README.** Добавь короткий блок в README.md (раздел «Архитектура»
или «Эпики»):

```markdown
### Анти-чит (Спринт 1.6)

См. подробности в [docs/anticheat.md](docs/anticheat.md). Кратко:
- Все use-cases прибавки длины проходят через `progression.add_length`.
- Hard-cap: 3000 cm/сутки + 14000 cm/неделю по rolling-окну
  (защищает от обхода через границу суток).
- Soft-ban на 14 дней при пробое cap-а; снимается автоматически
  по истечении или вручную через `/anticheat_unban` (super_admin).
```

## 3. Финальные проверки

```bash
# Свежие тесты
pytest tests/integration/load -q --no-cov -m slow
pytest tests/unit -q --no-cov
pytest tests/integration -q --no-cov

# Pre-commit (запускается на коммите автоматически)
pre-commit run --all-files

# Покрытие (CI требует ≥80% общего и ≥90% на новых файлах согласно DoD 1.6)
pytest --cov
```

Все 1451 + новые тесты должны проходить.

## 4. Заключительные шаги

1. **Коммиты** (используй явные пути, не `git add .`):
   - `git add tests/integration/load/test_anticheat_concurrent.py &&
     git commit -m "1.6.H: integration load test for AddLength clamp + trip-wire"`
   - `git add docs/anticheat.md README.md &&
     git commit -m "1.6.H: docs/anticheat.md + README pointer"`
   - Обнови `docs/current_tasks.md` (строка 1.6.H → ✅ смержено после
     merge) и `docs/history.md` (новая запись «2026-05-XX — Спринт 1.6.H»),
     закоммить.
   - **Удали этот HANDOFF-файл:** `git rm HANDOFF_1_6_H.md && git commit
     -m "1.6.H: drop handoff after completion"`.
2. `git push origin devin/1777992466-sprint-1-6h-load-test`.
3. `git_pr(action="fetch_template")` → `git_pr(action="create")` в репу
   `Pipirkawar/PipirkaWar`. Title: `Sprint 1.6.H: anticheat load test +
   docs/anticheat.md`.
4. `git(action="pr_checks", wait_mode="all")` — дождись зелёного CI.
5. После merge — обнови `docs/current_tasks.md` локально на main
   (статус 1.6.H → ✅ смержено + PR-ссылка), запиши в `docs/history.md`
   итоговый блок Спринта 1.6 («все 8 сабспринтов 1.6.A–H закрыты,
   эпик готов»).

## 5. Ловушки / нюансы

- **`@pytest.mark.slow`.** Уже зарегистрирован в `pyproject.toml`,
  load-тесты исключены из дефолтного запуска CI (см. `pytest.ini`/
  `pyproject.toml::tool.pytest.ini_options.addopts`). Перед коммитом
  убедись, что новый тест помечен — иначе он будет блокировать tight
  TDD-loop разработчиков.
- **SQLite vs Postgres.** Под SQLite файловой блокировки достаточно
  для serialization, но READS могут видеть stale snapshot. На Postgres
  REPEATABLE READ + SELECT FOR UPDATE на user-row решило бы это
  жёстче. Если SQLite-тест периодически флешит — это нормальный сигнал,
  что cap-protection работает только с trip-wire-ом, а не на чистом
  clamp-е.
- **Идемпотентность.** Не передавай `idempotency_key` в load-тесте,
  иначе все 100 grant-ов схлопнутся в no-op после первого.
- **Reason всё ещё обязателен.** В `LiftAnticheatBan`, не в `AddLength`.
  В `AddLength.grant(...)` reason — обычная строка без валидации
  пустоты на use-case-стороне (см. контракт `ILengthGranter`).
- **`audit_log.delta_cm`.** Введён в Спринт 1.6.C (миграция
  `0008_audit_log_delta_cm`). Trip-wire-аггрегация
  `sum_organic_in_window` фильтрует `delta_cm > 0` — отрицательные
  записи (`admin_refund`) и NULL-старые (`backfill='unknown'`)
  игнорируются. Не путай с `before/after.length_cm` — это разные
  поля, оба пишутся.
- **Анти-чит-конфиг.** Если 1.6.H провалится в CI на Python 3.11 vs
  3.12 — глянь `tests/unit/domain/balance/factories.py` и убедись,
  что `build_valid_balance()` всё ещё возвращает корректный YAML.

## 6. Полезные ссылки

- ГДД: `docs/Game design document.md` §3.3 (Анти-чит), §18.6 (Audit
  и AML), §0 (SOLID/Security check).
- Development plan: `docs/development_plan.md` §4 «Спринт 1.6 — Анти-
  чит и хардкап» (ПД 1.6.1–1.6.10).
- Текущие задачи: `docs/current_tasks.md` строка `1.6.H`.
- История: `docs/history.md` блоки `1.6.A` … `1.6.G`.
- Архитектура — pre-1.6.H state: PR #34 (1.6.A) → #35 → #36 → #37 →
  #39 → #42 → #43 (1.6.G).

Удачи. После 1.6.H закрывается весь Спринт 1.6 — бутылка шампанского.
