# AGENT_HANDOFF — Sprint 2.3.F (Daily Head: cron + activity middleware)

> **Ветка**: `devin/1778065078-sprint-2-3-f-cron-and-activity`
> **Базовая ветка**: `main` (commit `7e0a842` после PR #72)
> **Состояние коммитов на ветке** (последний → первый):
> - `b5c4811` Спринт 2.3.F.1 (шаг 2/2): DailyActivityMiddleware + DI + docs
> - `6ae09ea` Спринт 2.3.F.1 (шаг 1/2): record_active + use-case RecordPlayerActivity
>
> **Тесты**: ВСЕ зелёные локально на момент написания (9 middleware + 7 use-case + 4 integration). `make ci` lint+format+mypy+imports — зелёный (через pre-commit hook). Полный `make ci` (с pytest всего проекта) — НЕ запускался полностью, дотяни ниже.

---

## Что сделано (Sprint 2.3.F.1 «запись активности»)

### Domain
- `src/pipirik_wars/domain/daily_head/repositories.py` — `IDailyActivityRepository.record_active(*, user_id, last_at, moscow_date) -> None` (новый абстрактный метод).

### Infrastructure
- `src/pipirik_wars/infrastructure/db/repositories/daily_activity.py` — реализация `record_active` через `pg_insert.on_conflict_do_update` (PostgreSQL) и `sqlite_insert.on_conflict_do_update` (SQLite). UPSERT по PK `(date, user_id)` со `SET last_at = EXCLUDED.last_at`.

### Application
- `src/pipirik_wars/application/daily_head/record_activity.py` — use-case `RecordPlayerActivity(uow, players, daily_activity, clock)`. `execute(input_dto) -> bool`: lookup по `tg_user_id`; no-op (`False`) для unknown / no-id / FROZEN; иначе запись + `True`.
- `src/pipirik_wars/application/daily_head/__init__.py` — экспорт `RecordPlayerActivity`.
- `src/pipirik_wars/application/dto/inputs.py` — `RecordPlayerActivityInput(tg_user_id: PositiveTgId)`.

### Bot
- `src/pipirik_wars/bot/middlewares/daily_activity.py` — `DailyActivityMiddleware(use_case)`: только `Message` в group/supergroup; ловит `Exception` из use-case + `_log.warning(exc_info=True)`.
- `src/pipirik_wars/bot/middlewares/__init__.py` — `register_middlewares(...)` принимает опциональный `record_player_activity`; при наличии — `dp.message.middleware(DailyActivityMiddleware(...))`.
- `src/pipirik_wars/bot/main.py` — `Container.record_player_activity`, инстанс в `build_container`, проброс в `register_middlewares` + dispatcher workflow-data.

### Tests (все зелёные)
- `tests/integration/db/daily_head/test_daily_activity_repository.py::TestRecordActive` — 4 теста.
- `tests/unit/application/daily_head/test_record_player_activity.py` — 7 тестов.
- `tests/unit/bot/middlewares/test_daily_activity.py` — 9 тестов.
- `tests/unit/bot/test_composition_root.py` — обновлён под новое поле + middleware count = 5 у `dp.message`.
- `tests/fakes/daily_head.py::FakeDailyActivityRepository` — расширен `record_calls` + `activity` + `record_active` методом.

### Docs
- `docs/current_tasks.md` — строка `2.3.F.1` → 🟡 готово к ревью.

---

## Что ОСТАЛОСЬ для PR Sprint 2.3.F.1

1. **Обновить `docs/history.md`** — добавить запись 2.3.F.1 в стиле предыдущих:
   ```
   ## YYYY-MM-DD — Спринт 2.3.F.1 (запись активности игроков)

   - Расширен порт IDailyActivityRepository write-методом record_active(...)...
   - (детали из docs/current_tasks.md)
   ```
   (Можно скопировать описание из `docs/current_tasks.md` строка `2.3.F.1`.)

2. **Удалить этот HANDOFF** перед PR (но не делать `git rm`, см. ниже):
   ```bash
   rm AGENT_HANDOFF.md
   git add -A
   ```

3. **Прогнать полный `make ci`** локально:
   ```bash
   cd /home/ubuntu/repos/PipirkaWar
   export PATH="$PWD/.venv/bin:$PATH"
   make ci
   ```
   - Если упал — фиксить, **НЕ амендить коммиты** (новые коммиты).
   - Ожидаемое coverage: ≥ 95.5% (как было после 2.3.E).

4. **Закоммитить + push**:
   ```bash
   git add -A
   git commit -m "Спринт 2.3.F.1: docs/history.md + удалить HANDOFF"
   git push
   ```

5. **Создать PR**:
   ```python
   git_pr(action="fetch_template", repo="Pipirkawar/PipirkaWar", exec_dir="/home/ubuntu/repos/PipirkaWar")
   git_pr(action="create",
          repo="Pipirkawar/PipirkaWar",
          title="feat(middleware): daily_activity recording + RecordPlayerActivity (Спринт 2.3.F.1)",
          head_branch="devin/1778065078-sprint-2-3-f-cron-and-activity",
          base_branch="main",
          body="""<заполнить по шаблону>""")
   ```
   В теле PR-а:
   - Ссылки на ГДД §6.1.2 и ПД §5 (Спринт 2.3.7).
   - Список изменений по слоям (Domain / Infrastructure / Application / Bot / Tests / Docs).
   - Checklist: 4 integration + 7 use-case + 9 middleware + 6 composition-root = тестов добавлено.
   - Список оставшегося (2.3.F.2 — отдельный PR).

6. **Дождаться CI**:
   ```python
   git(action="pr_checks", repo="Pipirkawar/PipirkaWar", pull_number=<N>, wait_mode="all")
   ```

7. **Сообщить юзеру**: PR-ссылку + что 2.3.F.2 (cron) — дальше отдельным PR-ом.

---

## Sprint 2.3.F.2 — APScheduler cron (СЛЕДУЮЩИЙ PR, после мержа 2.3.F.1)

### Цель
Запуск use-case `RunDailyHeadCron` (он уже готов в Sprint 2.3.C) по APScheduler — раз в сутки на каждый клан с детерминированным `random_offset(0..24h)` от 00:00 МСК.

### План реализации

**1. Persistance: ничего нового** — `RunDailyHeadCron` уже идемпотентен через UNIQUE-индекс `daily_heads(clan_id, moscow_date)`.

**2. Скедулер (новый файл)**:
- `src/pipirik_wars/infrastructure/scheduler/daily_head_cron.py`:
  - Функция `compute_clan_offset_minutes(*, clan_id: int, moscow_date: date) -> int` — детерминированный hash:
    ```python
    import hashlib
    seed = f"{clan_id}:{moscow_date.isoformat()}".encode()
    digest = hashlib.sha256(seed).digest()
    minutes = int.from_bytes(digest[:4], "big") % (24 * 60)
    return minutes
    ```
  - Класс `DailyHeadCronScheduler(scheduler: AsyncIOScheduler, clans: IClanRepository, run_daily_head_cron: RunDailyHeadCron, clock: IClock)`:
    - `async def schedule_for_today() -> None`: листаем все `ClanStatus.ACTIVE` через `IClanRepository`; для каждого считаем offset; добавляем job_id `daily_head_cron:{clan_id}:{moscow_date}` (replace_existing=True); функция job-а:
      ```python
      async def _job(clan_id: int) -> None:
          await run_daily_head_cron.execute(RunDailyHeadCronInput(clan_id=clan_id))
      ```
    - `async def schedule_daily_seeder()`: добавляем cron-job на `00:01 МСК` который зовёт `schedule_for_today` каждые сутки.

**3. DI в `bot/main.py`**:
- Добавить `DailyHeadCronScheduler` в Container (опционально, или просто в `run()` запускать).
- Стартовать в `run()` после `await scheduler.start()` и `await daily_head_cron_scheduler.schedule_for_today()` + `schedule_daily_seeder()`.

**4. `IClanRepository.list_active(...)`** — есть ли уже метод?
```bash
grep -rn "list_active\|list_all\|find_all" src/pipirik_wars/domain/clans/
```
Если нет — добавить + реализовать в `SqlAlchemyClanRepository`.

**5. Тесты**:
- `tests/unit/infrastructure/scheduler/test_daily_head_cron.py`:
  - `test_offset_is_deterministic` — два вызова `compute_clan_offset_minutes(clan_id=1, moscow_date=date(2025,1,1))` дают одинаковое число.
  - `test_offset_in_range` — 0 ≤ offset < 24*60.
  - `test_different_clans_different_offsets` — два разных clan_id дают разные offset (статистически).
  - `test_schedule_for_today_adds_job_per_clan` — мокнуть `IClanRepository.list_active()` возвращающий 3 клана + AsyncIOScheduler-mock; проверить 3 add_job вызова.
  - `test_schedule_for_today_idempotent_on_replace` — replace_existing=True; повторный вызов не падает.
  - `test_schedule_daily_seeder` — добавляется cron-job на `00:01 МСК`.

- Integration-тест НЕ нужен (cron-trigger покрыт unit-тестами 2.3.C).

**6. Docs**:
- `docs/current_tasks.md` — добавить строку `2.3.F.2`.
- `docs/history.md` — добавить запись.

**7. PR**:
- Title: `feat(scheduler): cron RunDailyHeadCron per-clan deterministic offset (Спринт 2.3.F.2)`

---

## Текущая команда для быстрой проверки

```bash
cd /home/ubuntu/repos/PipirkaWar
export PATH="$PWD/.venv/bin:$PATH"

# Все три новые группы тестов:
pytest \
  tests/integration/db/daily_head/test_daily_activity_repository.py \
  tests/unit/application/daily_head/test_record_player_activity.py \
  tests/unit/bot/middlewares/test_daily_activity.py \
  tests/unit/bot/test_composition_root.py \
  --no-cov -v
```

Все должны быть зелёные.

---

## Контекст из прошлых сессий

- Sprint 2.3.E (`/clan_head` handler) уже смержен (PR #72, commit `7e0a842` на main).
- Все остальные Daily Head слои (2.3.A–D) тоже смержены.
- `RunDailyHeadCron` use-case уже написан в Sprint 2.3.C — НЕ нужно его переписывать, только запустить через scheduler.
- `RequestDailyHead` use-case — для button-trigger-а (handler `/clan_head`).
- Идемпотентность гарантируется UNIQUE-индексом `daily_heads(clan_id, moscow_date)`.
