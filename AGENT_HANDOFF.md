# AGENT HANDOFF — Sprint 2.3.C (Daily Head use-cases)

**Дата:** 2026-05-06
**Ветка:** `devin/1778058870-sprint-2-3-c-daily-head-usecases`
**Базовая ветка:** `devin/1778051724-sprint-2-2-f-mass-duel-handlers` (где уже смержены #65, #66, #67, #68, #69)
**Предыдущие PR этой серии:** #68 (2.3.A — domain), #69 (2.3.B — persistence) — **смержены**.

## Что нужно сделать

Application use-cases поверх доменного сервиса 2.3.A и репозиториев 2.3.B:

1. **`RequestDailyHead`** (button-trigger) — игрок жмёт `/clan_head` или кнопку «🎲 Назначить главу дня» в клан-чате.
2. **`RunDailyHeadCron`** (cron-trigger) — APScheduler в `random_offset(0..24h)`-час с 00:00 МСК.

Оба идемпотентны по `(clan_id, moscow_date)` через `DailyHeadService.assign_or_get(...)`.

## Архитектура use-case-а (одинаково для обоих)

```python
async with self._uow:
    # 1. Резолв клана
    #    - RequestDailyHead: clan = await clans.get_by_chat_id(input.chat_id)
    #    - RunDailyHeadCron: clan = await clans.get_by_id(input.clan_id)
    #    Если None — ClanNotFoundError. Если is_frozen — ClanFrozenError.
    #
    # 2. Доменный сервис (preflight проверяет existing → возвращает с id если уже есть)
    assignment = await daily_head_service.assign_or_get(clan_id=clan.id, source=...)
    if assignment.id is not None:
        # Идемпотентный возврат — глава уже назначен сегодня
        # Получаем player snapshot для UI и возвращаемся БЕЗ side-effects
        player = await players.get_by_id(assignment.player_id)
        return DailyHeadResolved(assignment=assignment, was_new=False, ...)
    #
    # 3. Запись в `daily_heads`. Race-handling: если параллельная транзакция
    #    выиграла — DailyHeadAlreadyAssignedError → re-fetch winner.
    try:
        saved = await heads.add(assignment)  # id заполнится
    except DailyHeadAlreadyAssignedError:
        winner = await heads.get_by_clan_and_date(clan_id=clan.id, moscow_date=...)
        # Возвращаем как идемпотентный no-op
        return DailyHeadResolved(assignment=winner, was_new=False, ...)
    #
    # 4. Прибавка длины через ILengthGranter (anti-cheat clamp + audit LENGTH_GRANT)
    await length_granter.grant(
        player_id=saved.player_id,
        delta_cm=saved.bonus_cm,
        source=AuditSource.DAILY_HEAD,
        reason="daily_head",
        idempotency_key=f"add_length:daily_head:{clan.id}:{moscow_date.isoformat()}",
    )
    #
    # 5. Audit DAILY_HEAD_ASSIGN (отдельная категория сверх LENGTH_GRANT)
    await audit.record(AuditEntry(action=AuditAction.DAILY_HEAD_ASSIGN, ...))
    return DailyHeadResolved(assignment=saved, was_new=True, ...)
```

## Зависимости (что уже есть, что нужно создать)

✅ Уже в репо:
- `DailyHeadService.assign_or_get(clan_id, source)` — Спринт 2.3.A.
- `IDailyHeadRepository` / `IDailyActivityRepository` — 2.3.A.
- `SqlAlchemyDailyHeadRepository` / `SqlAlchemyDailyActivityRepository` — 2.3.B.
- `IClanRepository.get_by_chat_id` / `get_by_id` — основа.
- `ILengthGranter.grant` — добавляет длину + audit LENGTH_GRANT.
- `AuditAction.DAILY_HEAD_ASSIGN` — уже в enum.
- `IAuditLogger.record(AuditEntry)`.
- `IClock`, `IRandom`, `IUnitOfWork`.

❌ Нужно создать в этом PR:
- **`AuditSource.DAILY_HEAD = "daily_head"`** — новое значение enum + миграция `0014_audit_source_daily_head` (drop+recreate CHECK whitelist) + обновление `test_audit_source.py`.
- Добавить `daily_head` в `config/balance.yaml::anticheat.organic_sources` (premium-bonus считается organic для anti-cheat).
- DTO inputs `RequestDailyHeadInput` / `RunDailyHeadCronInput`.
- Use-cases `RequestDailyHead` / `RunDailyHeadCron`.
- DI-провязка в `bot/main.py::build_dispatcher`.
- Unit-тесты обоих use-case-ов (~12-16 шт.).

## Точки восстановления (commits)

- [x] #1 AGENT_HANDOFF.md создан + ветка отрезана от родителя.
- [ ] #2 Migration 0014 + AuditSource.DAILY_HEAD enum + test_audit_source.py + balance.yaml.
- [ ] #3 DTO inputs + RequestDailyHead use-case (+ DailyHeadResolved DTO).
- [ ] #4 RunDailyHeadCron use-case.
- [ ] #5 DI-провязка в bot/main.py + container.
- [ ] #6 Unit-тесты (~14 шт.).
- [ ] #7 docs/current_tasks.md + history.md.
- [ ] #8 make ci локально + push + PR + удалить HANDOFF.

## Команды

```bash
cd /home/ubuntu/repos/PipirkaWar
source .venv/bin/activate
make ci  # должен быть зелёным: 2510+ passed, coverage ≥95.85%
git add -A && git commit -m "..." && git push
```

## Что ИСКЛЮЧАЕТСЯ из этого PR

- Bot handler `/clan_head` + кнопка → 2.3.E.
- Каталог цитат (≥100 RU + ≥100 EN) → 2.3.D.
- APScheduler-cron с per-clan random offset → 2.3.F.
- Middleware `daily_active`-записи → 2.3.E.
