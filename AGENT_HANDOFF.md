# AGENT_HANDOFF — Sprint 2.3.B (Daily Head Persistence)

**Дата:** 2026-05-06
**Автор HANDOFF-а:** Devin (агент `urbanviola`, session `devin-007958f77ad24c8897dfb2465709905f`)
**Цель этого файла:** дать следующему агенту достаточно контекста, чтобы продолжить работу с любого этапа без перечитывания всей истории сессии. Этот файл **должен быть удалён** перед мержем PR.

---

## TL;DR — что сделать

1. Открыть эту ветку: `devin/1778057764-sprint-2-3-b-daily-head-persistence` (база — `devin/1778051724-sprint-2-2-f-mass-duel-handlers`).
2. Прочитать раздел **«Текущее состояние»** ниже — он отражает реальный статус на момент последнего коммита.
3. Дочинить недоделанные шаги из чек-листа (раздел **«Чек-лист»**), коммитя после каждого.
4. Запустить `make ci` локально (см. **«Как тестировать»**), убедиться что зелёный.
5. **Удалить `AGENT_HANDOFF.md`** последним коммитом.
6. Если PR ещё не создан: `git_pr` инструмент с `action="fetch_template"` → `action="create"`. Заголовок: `feat(daily_head): persistence (миграция 0012 + ORM + репозитории + integration) [Спринт 2.3.B]`. База: `devin/1778051724-sprint-2-2-f-mass-duel-handlers`.
7. Дождаться CI зелёным (`git pr_checks wait_mode="all"`).
8. Сообщить пользователю с PR-линком.

---

## Контекст серии PR-ов

Серия Спринт 2.3 — «Глава клана дня 👑» (ГДД §6.1, ПД §5). Режется на 6 PR-ов:

| PR | Статус | Содержимое |
|---|---|---|
| **2.3.A** | ✅ #68 смержен | Доменный слой: VO, ports, `DailyHeadService.assign_or_get` (47 тестов). |
| **2.3.B** (этот) | 🔄 в работе | Persistence: миграция `0012_daily_heads` + (опционально) `0013_daily_active` + ORM + `SqlAlchemyDailyHeadRepository` + `SqlAlchemyDailyActivityRepository` + integration-тесты. |
| 2.3.C | ⚪ ждёт | Use-cases `RequestDailyHead` + `RunDailyHeadCron` через UoW + `add_length(reason="daily_head")` + audit. |
| 2.3.D | ⚪ ждёт | Catalog цитат `templates/clan_quotes_{ru,en}.json` (≥ 100 каждый) + `IClanQuoteProvider`. |
| 2.3.E | ⚪ ждёт | Bot: `/clan_head` + кнопка + локали `clan-head-*` RU+EN. |
| 2.3.F | ⚪ ждёт | APScheduler-cron: per-clan `random_offset(0..24h)` через `IRandom.deterministic_uint(seed=f"{clan_id}:{moscow_date}", 24*3600)` + DI всего. |

---

## Текущее состояние

### Где база лежит

- **Репо:** `Pipirkawar/PipirkaWar` на `/home/ubuntu/repos/PipirkaWar`.
- **Текущая ветка:** `devin/1778057764-sprint-2-3-b-daily-head-persistence`.
- **База:** `devin/1778051724-sprint-2-2-f-mass-duel-handlers` (это PR #65; в неё уже смержены #66, #67, #68 — все Sprint 2.2.x + 2.3.A).
- **`main` ещё не получал ничего из 2.2.F+** — после мержа PR #65 в `main` все дочерние PR-ы автоматически переориентируются.

### Что уже сделано (и закоммичено)

- Создан этот `AGENT_HANDOFF.md`. _(Последнее обновление: после первого коммита.)_

### Что ещё не сделано

Полный список — в разделе **«Чек-лист»** ниже.

---

## Архитектурные решения для 2.3.B

### Что хранить в БД

1. **`daily_heads`** (новая таблица, миграция `0012_daily_heads`):
   - `id BigSerial PK`
   - `clan_id BigInt FK → clans.id ON DELETE CASCADE`
   - `player_id BigInt FK → users.id ON DELETE CASCADE`
   - `moscow_date Date NOT NULL`
   - `source VarChar(8) NOT NULL` (CHECK ∈ {`button`, `cron`})
   - `bonus_cm Int NOT NULL` (CHECK > 0)
   - `assigned_at DateTime(tz=True) NOT NULL`
   - **UNIQUE `(clan_id, moscow_date)`** — last-line-of-defense от race кнопка+cron. Идемпотентность доменного `DailyHeadService.assign_or_get` сначала проверяет существование, но если две таски параллельно провалили проверку — UNIQUE-constraint в БД защитит от дубля. Конвертация `IntegrityError` → `DailyHeadAlreadyAssignedError` на уровне репо.
   - **Index `(clan_id, assigned_at DESC, id DESC)`** — для `list_recent_for_clan` (anti-repeat-фильтр).

2. **Активность игроков** — нужно **выбрать подход**:

   **Вариант 1 (рекомендуемый):** Таблица `daily_active(date, user_id, last_at_utc, PK (date, user_id))`. Дешёвый upsert на каждое сообщение через middleware. Запрос «активные за 7 дней» = `SELECT user_id WHERE date >= today - INTERVAL '7 days'`. Plan §5 строка 166 указывает именно эту таблицу.

   **Вариант 2:** Колонка `users.last_seen_at` + индекс. Проще миграция, но конфликтует с DAU-логикой (она использует in-memory `IDauCounter` и не пишет в БД).

   **Решение для 2.3.B:** Вариант 1 (новая таблица). Миграция `0013_daily_active`. Recorder-middleware появится в 2.3.E (когда мы будем привязывать handler-ы); пока что для unit/integration-тестов достаточно `SqlAlchemyDailyActivityRepository` который читает из таблицы (без записывающей middleware — это для следующего PR).

   ❗ **Альтернативный безопасный путь** (если ОЧЕНЬ ограничены по времени): для 2.3.B можно сделать только `daily_heads` миграцию + репо, а `IDailyActivityRepository` реализовать как заглушку или отложить целиком до 2.3.C. Но интеграционный smoke не получится.

### Где код должен лежать

```
src/pipirik_wars/infrastructure/db/
├── migrations/versions/
│   └── 20260506_0012_daily_heads.py            ← новая
│   └── 20260506_0013_daily_active.py           ← новая (если делаем daily_active)
├── orm/
│   └── daily_head.py                           ← новая (DailyHeadAssignmentORM)
│   └── daily_active.py                         ← новая (если делаем daily_active)
└── repositories/
    └── daily_head.py                           ← новая (SqlAlchemyDailyHeadRepository)
    └── daily_activity.py                       ← новая (если делаем daily_active)

tests/integration/db/daily_head/
├── __init__.py
├── test_daily_head_repository.py               ← integration (round-trip, UNIQUE, list_recent)
└── test_daily_activity_repository.py           ← integration (если делаем daily_active)
```

### Существующие ORM/migrations паттерны

**ORM-модели** живут в `src/pipirik_wars/infrastructure/db/orm/` (например `pvp_mass_duel.py`, `clan.py`). Используют `Mapped[...]` (full-typing), `MappedAsDataclass`, импорты из `pipirik_wars.infrastructure.db.orm.base.Base`.

**Репозитории** живут в `src/pipirik_wars/infrastructure/db/repositories/`. Шаблон:

```python
@dataclass
class SqlAlchemyDailyHeadRepository(IDailyHeadRepository):
    session: AsyncSession

    async def get_by_clan_and_date(self, *, clan_id: int, moscow_date: date) -> DailyHeadAssignment | None:
        stmt = select(DailyHeadAssignmentORM).where(
            DailyHeadAssignmentORM.clan_id == clan_id,
            DailyHeadAssignmentORM.moscow_date == moscow_date,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def add(self, assignment: DailyHeadAssignment) -> DailyHeadAssignment:
        orm = DailyHeadAssignmentORM(...)  # без id (Auto-PK)
        self.session.add(orm)
        try:
            await self.session.flush()
        except SaIntegrityError as exc:
            raise DailyHeadAlreadyAssignedError(
                clan_id=assignment.clan_id,
                moscow_date=assignment.moscow_date,
            ) from exc
        return _to_domain(orm)

    async def list_recent_for_clan(self, *, clan_id: int, limit: int) -> Sequence[DailyHeadAssignment]:
        stmt = (
            select(DailyHeadAssignmentORM)
            .where(DailyHeadAssignmentORM.clan_id == clan_id)
            .order_by(DailyHeadAssignmentORM.assigned_at.desc(), DailyHeadAssignmentORM.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return tuple(_to_domain(orm) for orm in result.scalars().all())
```

**Маппер `_to_domain` / `_to_orm`** — pure-функции в том же файле (или в `orm/daily_head.py`).

**Реги ORM-моделей**: добавить в `tests/integration/db/conftest.py` импорт нового ORM-класса (чтобы `Base.metadata.create_all` подхватил таблицу). Также в `tests/integration/db/test_migrations.py` обновить:
- `EXPECTED_HEAD_REVISION = "0013_daily_active"` (или `"0012_daily_heads"` если без активности)
- `EXPECTED_TABLES` — добавить новую/новые

### Integration-тесты — паттерны

**Базовый `conftest.py`** уже есть в `tests/integration/db/conftest.py`. Создаёт `engine` (sqlite в памяти), session, выполняет миграции через alembic. Каждый тест получает свежую сессию.

Шаблон теста:

```python
@pytest.mark.asyncio
async def test_round_trip(self, async_session: AsyncSession) -> None:
    # arrange: создай игрока + клан в БД (через ORM)
    repo = SqlAlchemyDailyHeadRepository(session=async_session)
    assignment = DailyHeadAssignment(
        id=None, clan_id=1, player_id=1,
        moscow_date=date(2026, 5, 6),
        source=DailyHeadSource.BUTTON,
        bonus_cm=10,
        assigned_at=datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc),
    )

    # act
    saved = await repo.add(assignment)
    fetched = await repo.get_by_clan_and_date(clan_id=1, moscow_date=date(2026, 5, 6))

    # assert
    assert saved.id is not None
    assert fetched == saved
```

См. `tests/integration/db/pvp/test_pvp_mass_duel_repository.py` как самый свежий референс.

---

## Чек-лист

- [x] Создать `AGENT_HANDOFF.md` (этот файл) и закоммитить — **точка восстановления #1**.
- [ ] **Миграция `0012_daily_heads`** (см. шаблон в `20260505_0005_oracle_invocations.py` — он самый похожий: per-player + moscow_date + UNIQUE).
  - revision: `"0012_daily_heads"`
  - down_revision: `"0011_pvp_mass_duels"`
  - Колонки: `id`, `clan_id`, `player_id`, `moscow_date`, `source`, `bonus_cm`, `assigned_at`.
  - PK on `id`.
  - FKs: `clan_id → clans.id` и `player_id → users.id` (CASCADE).
  - CHECKs: `bonus_cm > 0`, `source IN ('button', 'cron')`.
  - UNIQUE `(clan_id, moscow_date)`.
  - INDEX `(clan_id, assigned_at DESC, id DESC)` для list_recent.
  - Закоммитить → **точка восстановления #2**.
- [ ] **Миграция `0013_daily_active`** (опциональная — см. раздел архитектура).
  - Колонки: `date Date NOT NULL`, `user_id BigInt NOT NULL FK users.id CASCADE`, `last_at DateTime(tz=True) NOT NULL`.
  - PK `(date, user_id)`.
  - INDEX `(user_id, date DESC)` для запроса «по конкретному игроку, последние N дней».
  - Закоммитить → **точка восстановления #3**.
- [ ] **ORM-модели**:
  - `src/pipirik_wars/infrastructure/db/orm/daily_head.py` — `DailyHeadAssignmentORM` (зеркало миграции).
  - `src/pipirik_wars/infrastructure/db/orm/daily_active.py` — `DailyActiveORM` (если делаем).
  - Добавить импорты в `tests/integration/db/conftest.py` чтобы `Base.metadata.create_all` подхватил.
  - Закоммитить → **точка восстановления #4**.
- [ ] **Репозитории**:
  - `src/pipirik_wars/infrastructure/db/repositories/daily_head.py` — `SqlAlchemyDailyHeadRepository` (3 метода).
  - `src/pipirik_wars/infrastructure/db/repositories/daily_activity.py` — `SqlAlchemyDailyActivityRepository.list_active_member_ids(*, clan_id, within_days)` через JOIN `daily_active × clan_members × users` (status='active').
  - Закоммитить → **точка восстановления #5**.
- [ ] **Integration-тесты**:
  - `tests/integration/db/daily_head/test_daily_head_repository.py` (round-trip add/get, UNIQUE-violation на дубль, list_recent с tie-breaker, FK CASCADE).
  - `tests/integration/db/daily_head/test_daily_activity_repository.py` (если делаем).
  - Закоммитить → **точка восстановления #6**.
- [ ] **`tests/integration/db/test_migrations.py`** — обновить `EXPECTED_HEAD_REVISION` + `EXPECTED_TABLES`.
- [ ] **`docs/current_tasks.md`** + **`docs/history.md`** — добавить запись 2.3.B.
- [ ] **Удалить `AGENT_HANDOFF.md`** + закоммитить с `[handoff cleanup]`.
- [ ] `make ci` локально → всё зелёное.
- [ ] `git push origin devin/1778057764-sprint-2-3-b-daily-head-persistence`.
- [ ] Создать PR через `git_pr(action="fetch_template")` → `git_pr(action="create")`.
- [ ] `git pr_checks wait_mode="all"` → дождаться зелёного CI.
- [ ] Сообщить пользователю с PR-линком.

---

## Как тестировать локально

```bash
cd /home/ubuntu/repos/PipirkaWar
source .venv/bin/activate

# Полный CI:
make ci

# Только daily_head:
pytest tests/unit/domain/daily_head tests/integration/db/daily_head -v

# Только новая миграция:
pytest tests/integration/db/test_migrations.py -v

# Lint:
ruff check . && ruff format --check .

# Typecheck:
mypy

# Import-contract:
lint-imports
```

**Ожидаемый результат:** `2483+N passed, 1 skipped, coverage ≥ 95.8%`. Где `N` = количество новых integration-тестов (≥ 10, ожидаю 12-18).

---

## Важные оговорки

- ❗ **НЕ менять домен `daily_head` 2.3.A** — он уже смержен в #68. Только дополнять persistence.
- ❗ **НЕ ломать существующие миграции** — добавлять только новые с правильным `down_revision`.
- ❗ **НЕ удалять и НЕ переименовывать существующие тесты** — добавлять новые.
- ❗ **`/home/ubuntu/repos/PipirkaWar/.venv` уже есть** — все зависимости установлены, ничего ставить не нужно.
- ⚠️ **`make ci` может занимать ~60 секунд** — это нормально.
- ⚠️ **Перед мержем удалить `AGENT_HANDOFF.md`** — это файл для агента, не для прода.

---

## Ссылки

- PR #68 (2.3.A, базовый домен): https://github.com/Pipirkawar/PipirkaWar/pull/68
- PR #67 (2.2.G, /clan_history): https://github.com/Pipirkawar/PipirkaWar/pull/67
- ГДД: `pipirik_wars_plan.md` §6.1 «Глава клана дня».
- ПД: `docs/development_plan.md` Спринт 2.3 (задачи 2.3.1–2.3.8).
- Доменный слой 2.3.A: `src/pipirik_wars/domain/daily_head/` (5 файлов).
- Тесты домена 2.3.A: `tests/unit/domain/daily_head/` (3 файла, 47 тестов).
- Фейки: `tests/fakes/daily_head.py`.
