# AGENT HANDOFF — Спринт 2.2.B (Mass-PvP, чистый домен)

> **Назначение:** контекст и чек-лист для следующего агента, если текущая
> сессия прервётся посреди работы. Удалить **сразу после мержа PR** Спринта 2.2.B.

## Контекст

- **Репо:** `Pipirkawar/PipirkaWar` (Python 3.12, aiogram, SQLAlchemy, Mozilla Fluent).
- **Архитектура:** clean architecture 5-layer (domain → application → infrastructure → bot/presenters), `make ci` enforces import-linter contracts.
- **Базовая ветка:** `origin/main` после мержа PR #59 (фича `/clantop`) и PR #60 (docs cleanup).
- **Текущая ветка:** `devin/1778018942-sprint-2-2-b-mass-pvp-domain`.
- **Скоуп текущей задачи (2.2.B):** ровно по аналогии со Спринтом 2.1.A — **только чистый домен** массового PvP. Без БД, агрегата, use-cases, bot-handler-а, локалей. Только value-objects, чистые функции и balance-config.

## Цель

ГДД §7.2 / `development_plan.md` §6 / Спринт 2.2 → задачи 2.2.2–2.2.4:

- 2.2.2: Масс-PvP — вызов клан→клан, кулдаун 6 ч, авто-запись участников с длиной ≥ 20 см.
- 2.2.3: Игрок в обоих кланах — пропускается (юнит-тест).
- 2.2.4: Боевая механика N×M: 1 атака + 1 блок, случайные пары, **все удары за один тик**, ничья при 0 живых.

В Спринте 2.2.B покрываем **только** механику 2.2.4 на уровне чистого домена + balance-config. Кулдаун, авто-запись, дедупликация участников клан-↔-клан — это будущий 2.2.C (агрегат) / 2.2.D (use-cases).

## Архитектурные решения (приняты до старта)

1. **Один тик, не серия раундов.** «Все удары разрешаются за один тик» (ГДД §7.2 / 2.2.4). В отличие от 1×1 (3 раунда), масс-PvP — **одна резолюция за бой**. Внутри одной резолюции — N взаимодействий «атакующий-защитник», все одновременно по path-independent правилам.
2. **Pairing — биекция.** Каждый игрок клана A назначается атакующим против ровно одного игрока клана B. И наоборот. На уровне домена — **две независимые перестановки** (A→B и B→A), потому что атаки симметричные. RNG живёт в use-case (`IRandom` инжектится снаружи), но **в чистом домене 2.2.B** мы оставляем только функцию `pair_attackers(attackers, defenders, rng)`, которая вернёт `tuple[tuple[int, int], ...]` — пары `(attacker_id, defender_id)`.
3. **Уровень атаки/блока — той же оси.** Используем существующий `Position` enum (HIGH/MID/LOW) из `domain/pvp/entities.py`. Пробитие/блок — та же 3×3 матрица, та же чистая функция `_hit_blocked` / `_damage_cm`. **Никакого дублирования** — переиспользуем 1×1-движок там, где это естественно (в `resolve_mass_round` зовём `resolve_round` поштучно для каждой пары).
4. **`MassRoundChoice` отдельный VO.** Это «(player_id, attack, block)», в отличие от 1×1 `RoundChoice(attack, block)` — у нас несколько участников с одной стороны, и `player_id` нужен для связи «кто что выбрал».
5. **`hit_pct` берём общий с 1×1.** В `balance.pvp.duel_1v1.hit_pct=10`. Для массового боя нет смысла плодить второй параметр без явного game-design-обоснования.
6. **`min_length_cm` / `min_thickness_level`** — отдельные параметры в `balance.pvp.mass_duel`, чтобы можно было сделать массовый PvP «строже» по входу (например, ≥ 20 см длины + ≥ уровень 2 толщины из ГДД §7.2).
7. **`cooldown_hours: int = 6`** — отдельный параметр для масс-PvP (ГДД §7.2 / 2.2.2).
8. **Без `random` в чистом домене.** `pair_attackers` принимает `rng: IRandom` (это «снаружи»), но сама функция чистая — детерминирована по seed-у в тестах.

## План шагов (atomically commit-able)

- [x] Шаг 0: создание branch + AGENT_HANDOFF.md (этот коммит).
- [ ] Шаг 1: balance-config — добавить `pvp.mass_duel` секцию в `config/balance.yaml` + `MassDuelConfig` Pydantic-модель в `domain/balance/config.py` + расширить `PvpConfig.mass_duel` + +-tests на pydantic-валидаторы (range, errors). **Один коммит.**
- [ ] Шаг 2: VOs в `domain/pvp/mass.py` — `MassRoundChoice(player_id, attack, block)`, `MassPairing` (tuple of `(attacker_id, defender_id)`), `MassDamageEntry(attacker_id, defender_id, damage_cm, blocked: bool)`, `MassRoundOutcome(damage_entries, p1_clan_total_dealt, p2_clan_total_dealt)`, `MassDuelOutcome(...)`, `MassDuelWinner` enum (`CLAN1 / CLAN2 / DRAW`). + `__init__.py` экспорты. **Один коммит.**
- [ ] Шаг 3: pure `pair_attackers(*, attackers: Sequence[int], defenders: Sequence[int], rng: IRandom) -> tuple[tuple[int, int], ...]`. Использует `IRandom.shuffle` (если такого метода нет — добавить в порт + RealRandom + FakeRandom; ScriptedRandom обновить в test-helpers). Логика: длина выхода = `max(|A|, |B|)`, неравные стороны → меньшая сторона **переиспользует defender-ов по mod-cycle** (детерминированно: `defenders[i % len(defenders)]` после shuffle). +-тесты: симметрия, неравные размеры, пустые кланы → ValueError, детерминированность по seed. **Один коммит.**
- [ ] Шаг 4: `resolve_mass_round(*, clan1_choices, clan2_choices, clan1_initial_lengths, clan2_initial_lengths, hit_pct, rng)`. Логика: сделать `pair_attackers(clan1, clan2, rng)` для атак из A в B, симметрично `pair_attackers(clan2, clan1, rng)` — атаки из B в A. Для каждой пары вызвать существующую `_hit_blocked`/`_damage_cm` (или `resolve_round`-style helpers). Сложить ущерб per-defender, выдать `MassRoundOutcome`. + ~30 тестов (1×1 reduce-case, 2×2 happy, 3×1 unequal, draw сразу, large случаи с seed-determinism). **Один коммит.**
- [ ] Шаг 5: `resolve_mass_duel` — обёртка над `resolve_mass_round` с расчётом winner (CLAN1 / CLAN2 / DRAW по тоталам), zero-sum дельты per-clan. + path-independence-тест + zero-sum invariant. **Один коммит.**
- [ ] Шаг 6: `make ci` зелёный → push → PR через `git_pr` (fetch_template + create) → `git pr_checks wait_mode=all`. **PR-коммит = head ветки.**
- [ ] Шаг 7: после мержа — отдельный PR (или в составе следующего 2.2.C) удалить `AGENT_HANDOFF.md` + обновить `docs/current_tasks.md` (добавить 2.2.B как ✅ смержено).

## Критерии «готово» для 2.2.B

- `make ci` зелёный (lint + mypy strict + import-linter + pytest).
- Coverage ≥ 80% на `src/pipirik_wars/domain/balance/config.py` (новые поля), `domain/pvp/mass.py`, `domain/pvp/mass_services.py` (или куда положим pure-функции).
- ВСЕ value-objects — `frozen=True, slots=True`.
- Никаких импортов из `application/`, `infrastructure/`, `bot/` в новый код домена (import-linter ловит автоматически).
- Никаких `random.*` напрямую — только через `IRandom`.
- Тесты покрывают: pydantic-валидаторы (out-of-range, отрицательные значения), pairing (детерминизм, неравные стороны, пустые кланы), resolve_mass_round (одиночный пробив, блок, симметрия), resolve_mass_duel (zero-sum, draw, winner-determination, path-independence).

## Ссылки на существующие паттерны (для копирования)

- 1×1 чистый домен (mirror): `src/pipirik_wars/domain/pvp/entities.py`, `services.py`.
- Balance-config паттерн: `src/pipirik_wars/domain/balance/config.py::PvpDuel1v1Config`, `PvpConfig`.
- Pydantic Field-валидаторы: те же `Field(ge=..., le=...)`.
- Тесты pydantic-балансов: `tests/unit/domain/balance/test_pvp_config.py`.
- Тесты resolve-функций: `tests/unit/domain/pvp/test_services.py`.
- IRandom port: `src/pipirik_wars/domain/shared/ports/random.py`.
- FakeRandom: `tests/fakes/random.py`.

## Если агент прерывается посреди шага

- Закоммить прогресс **что есть**, даже если не зелёный. Это спасает от потери работы. В commit-message: `wip(...): ... [Спринт 2.2.B шаг N — partial]`.
- Обнови этот HANDOFF (отметь, до какого шага дошёл, какие ошибки висят).
- Запушь ветку. Следующий агент возьмёт оттуда.
