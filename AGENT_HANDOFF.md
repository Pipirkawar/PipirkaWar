# 🤖 AGENT HANDOFF — Спринт 4.1-M «ИИ-предсказания/логи»

> **Назначение этого файла:** sticky-режим CONTRIBUTING.md — передача состояния
> между AI-агентами в рамках одного PR. Удаляется в M.8 отдельным коммитом
> перед мерджем.

---

## Текущая сессия

- **Session URL:** https://app.devin.ai/sessions/dc53351a3caf438ea211fc897a110dc0
- **Branch:** `devin/1778694020-sprint-4-1-M-ai-predictions`
- **Base commit:** `6c81a69` (main после merge PR #140 4.1-L)
- **Sprint:** **4.1-M** «Перевод предсказаний/логов на ИИ» (задача 4.1.13, опциональная)
- **Active PR:** *(пока не создан, будет в M.8)*

## Снимок прогресса (M.0 → M.8)

- [x] **M.0** — pivot `current_tasks.md` + sticky HANDOFF (этот файл); baseline CI: **7064 passed + 2 skipped + 95% cov, 519.96 с**.
- [x] **M.1** — Порт `IAiTextGenerator` + `AiGenerationError` + тип `DuelLogKind` в `application/ai/`.
- [x] **M.2** — Адаптер `OpenAiTextGenerator` (infrastructure/ai/openai_generator.py) + `AiSettings` (env-prefix `AI_`).
- [x] **M.3** — In-memory кэш через `_cache: dict[locale, tuple[Template]]` в AI-провайдерах (async refresh, не Redis — process-local достаточно).
- [x] **M.4** — `AiOracleTemplateProvider` (infrastructure/ai/oracle_provider.py) — обёртка вокруг static-fallback.
- [x] **M.5** — `AiForestLogTemplateProvider` + `AiDuelLogTemplateProvider` (последний делает 3 LLM-вызова на локаль — по одному на `RoundOutcomeKind`).
- [ ] **M.6** — Wire-up в `bot/main.py` (toggle `AI_ENABLED`) + background refresh-task.
- [ ] **M.7** — Unit/integration тесты (mock LLM, кэш, fallback, прогрев).
- [ ] **M.8** — Doc-sync (`docs/history.md`, `docs/current_tasks.md`) + remove HANDOFF + PR + CI green.

## Архитектурное решение

- AI-генерация запускается ТОЛЬКО при `AI_ENABLED=True` + валидный `AI_API_KEY`.
- Sync-порт `get_templates()` читает из in-memory dict, async-метод `refresh()` обновляет его через LLM. Background-task в bot/main вызывает `refresh()` периодически.
- При сбое LLM кэш не очищается; провайдер падает на static-fallback. Zero-downtime гарантирован.

## Не входит в скоуп

- AlertManager, production Grafana-инстанс (за рамками).
- Бизнес-метрики DAU/караваны/рейды/крипто-пул (отдельный спринт).
- OpenAI Moderation API (модель сама фильтрует unsafe-промпты через системную инструкцию).
- pyproject.toml пока НЕ добавляет `openai` SDK явно — у нас duck-typed `client: Any` в `OpenAiTextGenerator`. Реальная зависимость добавится в M.6 если используется.
