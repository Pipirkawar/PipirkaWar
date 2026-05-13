# AGENT HANDOFF — Sprint 4.5-A «Foundation: FastAPI + Telegram Login + TOTP»

> **Sticky baton.** Удалить через `git rm AGENT_HANDOFF.md` в финальном
> коммите PR-а Спринта 4.5-A (вместе с doc-sync). См. CONTRIBUTING.md §
> «Промпт-приёмка для нового агента».

## Состояние проекта на момент передачи (2026-05-13)

* **main:** `9163b9f` (после merge PR #143 — follow-up к Спринту 4.1-N).
* **Спринт 4.1 «Монетизация и масштаб»:** закрыт целиком (PR #138–#143).
  * 4.1.1–4.1.11 — монетизация (Stars / TON / USDT / Prize Pool)
  * 4.1.12 — Redis-миграция + load-test (4.1-G/H/I/J)
  * 4.1.13 — ИИ-предсказания (4.1-M, PR #141)
  * 4.1.14 — i18n PT/ES/TR/ID/FA/UK (4.1-K, PR #139)
  * 4.1.15 — Метрики + Grafana (4.1-L PR #140 + 4.1-N PR #142 + follow-up PR #143)
* **Baseline `make ci`:** 7184 passed + 2 skipped + 95.26 % cov, 533.39 с.
* **Open blockers:** нет.

## Активная задача

**Спринт 4.5 «Веб-админ-панель» (опц.), первый PR — 4.5-A «Foundation».**

* **Закрывает ПД-задачи:** 4.5.1 (FastAPI + TG Login), 4.5.3 (TOTP gate).
* **НЕ закрывает в этом PR:** 4.5.2 (RBAC), 4.5.4 (dashboard), 4.5.5–4.5.10.
* **Подробный план + тех-выборы + checklist реализации:** **[docs/sprint_4_5_A_plan.md](docs/sprint_4_5_A_plan.md)** (1100+ строк). Это **обязательное чтение** перед началом работы.

## Ветка для работы

Текущая ветка (этот коммит):
```
devin/1778702294-sprint-4-5-A-foundation-plan
```

**Следующий агент** имеет право:
* (A) Продолжить работу в этой ветке (более 1 коммита) и оформить PR оттуда.
* (B) Создать новую ветку от `main` (e.g. `devin/<ts>-sprint-4-5-A-impl`), забрав отсюда план как часть истории merge.

Рекомендуется **вариант B** для чистоты PR-а (план уже зафиксирован в этой ветке без PR — после merge implementation-ветки можно либо удалить эту планируящую ветку, либо слить её PR-ом отдельно для исторической записи).

## Краткий обзор технологических выборов

(Полное обоснование — в `docs/sprint_4_5_A_plan.md` §1.)

| Слой | Технология | Причина |
|---|---|---|
| HTTP-фреймворк | **FastAPI** ≥0.115 | async-native, pydantic-2 integration, OpenAPI |
| ASGI-сервер | **Uvicorn[standard]** | де-факто стандарт |
| Templates | **Jinja2 + HTMX (vendored)** | server-rendered, без SPA-overhead |
| Sessions | **`itsdangerous` signed cookies** | stateless, минимум deps |
| CSRF | **Custom HMAC middleware** | минимум deps, контроль |
| QR | **`qrcode[pil]`** | канонический Python QR-pkg |

**Новые prod-deps:** 5 (fastapi, uvicorn[standard], jinja2, itsdangerous, qrcode[pil]).
**Новые dev-deps:** 0 (httpx уже в prod-deps для TON-RPC).

## Что делать (high-level)

1. **Прочитать** `docs/sprint_4_5_A_plan.md` полностью (особенно §3 routes, §4 security, §5 composition root, §7 тест-план).
2. **Выбрать ветку** (A или B выше).
3. **Выполнить** A.1–A.8 (см. §8 «Implementation checklist» в плане).
4. **Создать PR** по template-у из §9 плана.
5. **CI green** → удалить `AGENT_HANDOFF.md` в финальном коммите → отчёт пользователю.

## Что НЕ делать в 4.5-A

* RBAC (4.5.2) — следующий PR (4.5-B).
* Реальные dashboard-виджеты с метриками — placeholder только.
* Player/Clan/Audit-разделы — следующие PR-ы.
* Balance-editor — 4.5-G.
* Production hardening (HSTS-rules, structured-logging-pipeline, deploy-manifests) — 4.5-H/I.
* Новые `AdminAuditAction`-enum-значения — отложено в 4.5-F (audit-log UI). См. план §10.4.

## Открытые вопросы для пользователя

См. план §10 — 6 пунктов, на которые следующий агент должен либо получить ответ, либо принять решение самостоятельно (с фиксацией в PR-описании).

Самые критичные:
1. **BOT_USERNAME для TG Login Widget** — взять из env (`BOT_USERNAME`) или запросить у пользователя.
2. **TOTP-setup в web без bootstrap-password** — если пароль не настроен в окружении, web-страница setup-а должна показать «обратитесь к super-admin через бот».
3. **Database URL** — `ADMIN_WEB_DATABASE_URL` приоритет, fallback на `DATABASE_URL`.

## Контакты + история

* **PR #142** (4.1-N): https://github.com/Pipirkawar/PipirkaWar/pull/142
* **PR #143** (follow-up): https://github.com/Pipirkawar/PipirkaWar/pull/143
* **ПД §7 «Спринт 4.5»:** `docs/development_plan.md:741-756`

## После завершения

* Update `docs/history.md` с записью 4.5-A.
* Update `docs/current_tasks.md`: 4.5.1 + 4.5.3 ⇒ `[x]`; 4.5.2 + 4.5.4–4.5.10 ⇒ `[ ]`.
* `git rm AGENT_HANDOFF.md`.
* Сообщить пользователю PR-ссылку + результаты CI + любые отклонения от плана.
