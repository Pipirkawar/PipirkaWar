# AGENT_HANDOFF — Спринт 2.2.E (mass-PvP use-cases)

> Файл создан по запросу @shirline89 на случай если у текущего агента
> закончатся токены посреди работы. **Удалить, как только перестанет
> быть нужным** (коммит будет включать удаление этого файла).

## Контекст

PR #63 (Спринт 2.2.D — persistence-слой массового PvP) **уже смержен** в `main`. Текущая ветка: `devin/1778048689-sprint-2-2-e-mass-duel-usecases`, базируется на свежем `main` после мержа #63.

## Скоуп 2.2.E

**Application-слой для mass-PvP**, по аналогии с тем, что сделано для 1×1-PvP в `application/pvp/` (challenge_duel/accept_duel/submit_move/resolve_afk_round/cancel_duel/apply_outcome).

**В скоуп входит:**
1. ✅ Расширить `IMassDuelRepository` методом `find_most_recent_for_clan(clan_id) → MassDuel | None` (для cooldown-проверки 6h в `StartMassDuel`).
2. ✅ Добавить DTO-входы в `application/dto/inputs.py` (5 классов).
3. ✅ Реализовать use-case-ы в `application/pvp/`:
   - `StartMassDuel` — eligibility (length≥20, thickness≥2, не в обоих кланах) + cooldown-check (6h) + activity-locks на всех участников + `MassDuel.create_battle(...)` + audit `PVP_MASS_DUEL_CREATED`.
   - `SubmitMassMove` — load + `MassDuel.submit_move(...)` + save (не резолвит — резолв отдельно).
   - `ResolveMassDuel` — load + `MassDuel.resolve(...)` + save + `apply_mass_duel_outcome` + release locks + audit.
   - `ForceResolveMassDuel` — AFK-фоллбэк: load + `force_submit_missing(...)` (с RNG-fallback choices) + `resolve` + save + apply outcome + release locks + audit.
   - `CancelMassDuel` — load + `cancel(...)` + save + release locks + audit.
4. ✅ Helper `apply_mass_duel_outcome` в `application/pvp/apply_mass_outcome.py` (по аналогии с `apply_outcome.py`, но N×M участников).
5. ✅ Новые `AuditAction`-ы: `PVP_MASS_DUEL_CREATED` / `PVP_MASS_DUEL_COMPLETED` / `PVP_MASS_DUEL_CANCELLED` (и плюс per-participant grant/revoke по аналогии с 1×1).
6. ✅ DI-провязка в `bot/main.py`: `mass_duels = SqlAlchemyMassDuelRepository(uow=uow)` + factory-функции `make_start_mass_duel`, `make_submit_mass_move`, `make_resolve_mass_duel`, `make_force_resolve_mass_duel`, `make_cancel_mass_duel`.
7. ✅ Fakes: расширить `FakeMassDuelRepository.find_most_recent_for_clan(...)`.
8. ✅ Unit-тесты для каждого use-case-а (mock-fakes-style, ~5-10 тестов на use-case).
9. ✅ Integration-тест на `find_most_recent_for_clan` в `tests/integration/db/pvp/test_pvp_mass_duel_repository.py`.
10. ✅ Обновить `docs/current_tasks.md` (новая строка 2.2.E) и `docs/history.md`.

**В скоуп НЕ входит** (это 2.2.F):
- Bot handlers (`/clan_attack`, inline-кнопки).
- Локали (`locales/ru/pvp.ftl`, `locales/en/pvp.ftl`).
- Presenter-ы.
- APScheduler-провязка для AFK-таймеров (port `IDelayedJobScheduler.schedule_mass_duel_afk_resolution(...)`).
- Cooldown-индикатор в `/clantop` или отдельной команде.

## Что уже сделано (если агент сменился)

См. последние коммиты в ветке (`git log --oneline main..HEAD`). Каждый шаг коммитится отдельно — смотри логи, чтобы понять, на каком шаге остановился предыдущий агент.

## Шаблоны для копирования

### DTO-стиль (`application/dto/inputs.py`)
Смотри `ChallengeDuelInput` / `SubmitMoveInput` / `CancelDuelInput` — pydantic, frozen, strict, с `model_validator` если есть зависимости между полями.

### Use-case-стиль (`application/pvp/*.py`)
Смотри `challenge_duel.py` / `submit_move.py` / `cancel_duel.py` — class с `__slots__`, конструктор с keyword-only DI-портами, `async def execute(self, input_dto)`, ambient `IUnitOfWork`, `audit.record(...)` на финале, idempotency-keys через `f"...:{duel.id}"`.

### Тест-стиль (`tests/unit/application/pvp/test_*.py`)
Смотри существующие тесты `test_challenge_duel.py` / `test_submit_move.py` (если они есть) — fakes-based, по одному тесту на каждый ветвь логики. Используй `FakeMassDuelRepository` из `tests/fakes/mass_duel_repo.py`.

### Apply-outcome стиль (`application/pvp/apply_outcome.py`)
Это точная модель для `apply_mass_outcome.py`. Внутренне циклит по участникам, для каждого с delta>0 → `length_granter.grant(source=PVP_REWARD)`, для delta<0 → прямой `players.save(player.with_length(...))` + audit `LENGTH_REVOKE`. Idempotency-keys: `f"add_length:pvp_mass_duel:{duel_id}:{player_id}"` и `f"pvp_mass_duel_loss_revoke:{duel_id}:{player_id}"`.

## Команды

```bash
cd /home/ubuntu/repos/PipirkaWar
git status
git log --oneline main..HEAD  # что уже закоммичено в текущей ветке
make ci                       # lint + typecheck + tests
git diff                       # текущие незакоммиченные изменения

# Перед PR:
# 1. убедиться что AGENT_HANDOFF.md удалён
# 2. убедиться что docs/current_tasks.md и docs/history.md обновлены
# 3. убедиться что make ci зелёный

git add ...
git commit -m "feat(pvp): mass-duel use-cases ... [Спринт 2.2.E]"
git push
```

## Финал

- Удали `AGENT_HANDOFF.md` (`git rm AGENT_HANDOFF.md`) перед созданием PR.
- Создай PR через `git_pr(action="fetch_template")` затем `git_pr(action="create")`. Title: `feat(pvp): mass-duel use-cases (Start/Submit/Resolve/Cancel + AFK + apply_outcome) [Спринт 2.2.E]`.
- Жди CI через `git(action="pr_checks", wait_mode="all")`.
- Сообщи пользователю с PR-ссылкой.
