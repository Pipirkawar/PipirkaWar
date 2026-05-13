# 🤖 AGENT_HANDOFF.md — Спринт 4.1-N (sticky, удаляется в N.6)

> Этот файл — **sticky-handoff** между агентами в рамках одного PR. Создаётся в N.0, обновляется на контрольных точках, удаляется в N.6 (отдельным коммитом перед PR). См. `CONTRIBUTING.md` «Sticky-mode HANDOFF».

## Контекст сессии

- **Session URL:** https://app.devin.ai/sessions/dc53351a3caf438ea211fc897a110dc0
- **Активный спринт:** Спринт 4.1 «Монетизация и масштаб» (Фаза 4 ПД §7) — **финальный** PR этого спринта (закрывает задачу 4.1.15)
- **Активный PR:** 4.1-N «Бизнес-метрики Prometheus + панели Grafana»
- **Базовая ветка main:** `f43d7a3` (merge PR #141 «4.1-M ИИ-предсказания»)
- **Feature-ветка:** `devin/1778697415-sprint-4-1-N-business-metrics`

## Baseline CI (на `main = f43d7a3` post-4.1-M merge)

```
make ci → 7124 passed + 2 skipped + 95.37 % cov, 1024.46 с
4 import-linter contracts kept
```

## Что закрывает PR

Задача 4.1.15 из ПД §7 (вторая половина — бизнес-метрики). Первую половину (Redis-метрики + Grafana-стек) закрыл PR #140 «4.1-L». После мерджа этого PR **Спринт 4.1 закрывается целиком**.

Бизнес-метрики, которые добавляются (формула «что важно для бизнес-borda и SRE-on-call»):

- **DAU** — `pipirik_dau_active_users` (gauge) — текущий DAU из существующего `IDauCounter.current()`-источника.
- **Караваны** — `pipirik_caravan_active_total` (gauge), `pipirik_caravan_outcomes_total{outcome}` (counter; ∈ {raiders_win, owner_win, draw, cancelled}).
- **Рейды** — `pipirik_raid_active_total` (gauge), `pipirik_raid_outcomes_total{outcome}` (counter; ∈ {raiders_win, boss_win, cancelled}).
- **Призовой пул per currency** — `pipirik_prize_pool_balance{currency}` (gauge; currency ∈ {stars, ton, usdt}).
- **Рулетка** — `pipirik_roulette_spins_total{kind, prize_class}` (counter; kind ∈ {free, paid}, prize_class ∈ {cm, length_bonus, blessed_scroll, crypto, ...}).
- **Дуэли** — `pipirik_duel_resolved_total{outcome}` (counter; outcome ∈ {p1_win, p2_win, draw, p1_afk, p2_afk}).
- **Forest-runs** — `pipirik_forest_run_started_total` + `pipirik_forest_run_finished_total{status}` (counter; status ∈ {success, drop, idle_timeout}).

## Архитектурные решения

1. **Порт `IBusinessMetrics`** живёт в `application/observability/business_metrics.py` (новый пакет `application/observability/`). Это **cross-cutting-port** — use-case-ы дёргают его при критических событиях. Без него use-case продолжает работать (`None`-default + null-object `NullBusinessMetrics`-fallback).
2. **Адаптер `PrometheusBusinessMetrics`** в `infrastructure/observability/business_metrics.py`. Использует тот же `CollectorRegistry`, что и `RedisMetrics` (общий `/metrics`-endpoint).
3. **Инструментация — точечная**: только в use-case-finish-методах (после successful UoW commit), чтобы метрики отражали реальные state-changes, а не пытаются. Не на _every_ DTO-success: например, `CreateCaravan.execute()` инкрементит `active_total++`, `FinishCaravanBattle.execute()` декрементит и инкрементит `outcomes_total{outcome=...}`.
4. **DAU-gauge** обновляется **не из use-case-а**, а из периодической background-task в `run()` (как `_ai_refresh_loop` из 4.1-M): раз в минуту вычитывает `IDauCounter.current()` → `gauge.set(value)`. Это снимает нагрузку с hot-path-а `RecordPlayerActivity`.
5. **Prize-pool gauge** обновляется в `RecordDonation` + `ClaimPrize` + `RefundLot` + `RegeneratePrizeLots` (точки изменения баланса).
6. **Grafana-дашборд** — отдельный JSON-файл `monitoring/grafana/dashboards/business-metrics.json` (рядом с `redis-metrics.json` из 4.1-L). Auto-provisioning уже настроен в `monitoring/grafana/provisioning/dashboards/dashboards.yml`.

## Чек-лист шагов

- [x] **N.0** — snapshot pivot `current_tasks.md` + этот sticky HANDOFF + baseline CI verified (7124 passed)
- [ ] **N.1** — порт `IBusinessMetrics` + `NullBusinessMetrics` + `PrometheusBusinessMetrics` адаптер
- [ ] **N.2** — точечная инструментация в use-case-ах (caravans/raids/duels/forest/monetization)
- [ ] **N.3** — wire-up в `bot/main.py`: `Container.business_metrics`, регистрация в общий registry, фоновый DAU-poller-таск
- [ ] **N.4** — `monitoring/grafana/dashboards/business-metrics.json` — 5 рядов × 8-10 панелей
- [ ] **N.5** — unit-тесты (fake `IBusinessMetrics` в use-case-тестах) + integration smoke (panel JSON-валидность)
- [ ] **N.6** — doc-sync (`docs/history.md` + `current_tasks.md` чек-лист `[x]`) + `git rm AGENT_HANDOFF.md` + PR + CI

## Если ты следующий агент

1. Прочитай `CONTRIBUTING.md` (7-шаговая приёмка).
2. `git fetch && git checkout devin/1778697415-sprint-4-1-N-business-metrics`.
3. Сверь свой `git log -10` с чек-листом выше — какие шаги уже сделаны.
4. Продолжи с первой `[ ]`-строки.
