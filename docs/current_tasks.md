# 🍆 Пипирик Варс — Текущие задачи

> Этот файл описывает **только то, что в работе сейчас**: активная feature-ветка, активный спринт/PR, чек-лист текущих шагов и их статусы. По мере выполнения шаги отмечаются `[x]`; после мерджа PR-а соответствующая запись переносится в [`history.md`](history.md), а файл обновляется под следующий спринт.
>
> **Длинный план** (фазы / спринты A→Z) — в [`development_plan.md`](development_plan.md).
> **Игровая спецификация** (механики, формулы, баланс) — в [`game_design.md`](game_design.md).
> **Журнал завершённых работ** — в [`history.md`](history.md).
> **Правила работы с документацией + протокол передачи задач между агентами** — в [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
>
> ⚠️ **Перед каждым коммитом** обнови чек-лист ниже (отметь готовые шаги, обнови «текущая позиция»). Это нужно для непрерывности при смене агентов — следующий агент должен знать, где ты остановился.

---

## 📸 Снимок состояния проекта

> Эта секция отражает состояние проекта **на момент последнего обновления этого файла**. Она нужна для того, чтобы новый агент за 30 секунд понял, что происходит. Обновляй её при старте/завершении каждого PR-а.

**На `main`:** последний смерженный спринт — **2.3.F.2** (PR #74) «Per-clan APScheduler-cron Главы клана дня»; затем серия docs-PR-ов #75/#76/#77 (реструктуризация документации + протокол передачи работы между агентами + расширения и дефолты ГДД). Завершены Фазы 0, 1 (MVP), 1.6 (анти-чит) полностью; из Фазы 2 закрыты 2.1 (PvP 1×1), 2.2 (масс-PvP + клановые механики), 2.3 (Глава клана дня). Идёт **Спринт 2.4 — Реферальная система и шеринг**.

**Активная feature-ветка:** `devin/1778068742-sprint-2-4-a-referral-domain` (имя ветки от первого шага). В неё уже влит `origin/main` (merge-commit `f6a245e`, без конфликтов). Состояние шагов:
- ✅ `0cbe1e3` Спринт 2.4.A: доменный слой реферальной системы (`Referral` VO + `IReferralRepository` + 5 ошибок + 25 тестов).
- ✅ `56c7ce4` Спринт 2.4.B: persistence (миграция 0015 + ORM + Sql/Fake repo + 6 integration-тестов).
- ✅ `5414693` Спринт 2.4.C: application use-cases (`RegisterReferral` + `GrantReferralSignupBonus` + `GrantReferralThicknessMilestone` + 24 unit-теста).
- ✅ `2865452` Спринт 2.4.C (фикс): убран `unused-ignore` в `test_entities.py`.
- ✅ `9580210` Спринт **2.4.D-a**: интеграция реферальных use-cases в `/start` и `/upgrade` — payload `start=ref_<id>` (только в ЛС, антифрод по типу чата + self-referral + кривой формат), `RegisterPlayer` → `RegisterReferral` + `GrantReferralSignupBonus`, `UpgradeThickness` → `GrantReferralThicknessMilestone`, локали `start-registered-with-referral` RU+EN.
- ✅ `5197ced` + `82109a4` Спринт **2.4.D-b**: кнопка «Поделиться» под результатом `/duel` и `/forest` (presenter `ReferralSharePresenter` + handler `referral_share.py` с callback_data `ref-share:{kind}:{entity_id}` + локали `referral-share-*` RU+EN, ГДД §13.2) + 26 тестов presenter + 14 тестов handler + fix forest-notifier-теста.
- ⏳ **Остаётся (текущая сессия):** **2.4.E** — еженедельный per-clan cron (вс. 18:00 UTC) с реферальной weekly-card (новых бойцов + топ-3 приглашателей за неделю); **2.4.F** — rate-limit-антифрод per-`referrer_tg_id` на `RegisterReferral` + audit-лог попыток (задача 2.4.4 — закрывается «частично», IP/устройство в aiogram недоступны).

**Открытого PR на 2.4 нет.** PR будет открыт после закрытия 2.4.E и 2.4.F и зелёного `make ci`.

**`AGENT_HANDOFF.md` на feature-ветке:** есть (актуализирован под текущую сессию — safety-net). Удаляется отдельным коммитом перед открытием PR.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.4 — Реферальная система и шеринг` |
| **Активный PR / шаг** | `2.4.E → 2.4.F` (полное закрытие спринта 2.4) |
| **Активная feature-ветка** | `devin/1778068742-sprint-2-4-a-referral-domain` (продолжаем существующую ветку, `origin/main` уже влит) |
| **Базовая ветка** | `main` |
| **Последний коммит на ветке** | `82109a4` `test(referral): unit-тесты ReferralSharePresenter + handler + fix forest notifier test` |
| **PR (если открыт)** | ещё не открыт; будет один PR на закрытие 2.4 (E + F) |
| **CI статус** | зелёный (`make ci` на момент приёмки этой сессии — lint/typecheck/import-linter ✅; pytest 2781 passed / 1 skipped, coverage 96.10%) |
| **Связанная задача в `development_plan.md`** | §6 / Спринт 2.4 / задачи 2.4.4 (антифрод), 2.4.6 (weekly cron) |
| **Связанная спецификация в `game_design.md`** | §13.1 (реферальная схема), §13.3 (еженедельные итоги) |
| **`AGENT_HANDOFF.md` существует?** | да (см. `/AGENT_HANDOFF.md` в корне) |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

- [x] **2.4.D-b** (закрыто коммитами `5197ced` + `82109a4`): кнопка «Поделиться» в результате `/duel` и `/forest` — `ReferralSharePresenter` + handler `referral_share.py` (callback_data `ref-share:{kind}:{entity_id}`) + локали `referral-share-*` RU+EN + 26 тестов presenter + 14 тестов handler. ГДД §13.2.
- [ ] **2.4.E**: weekly per-clan referral summary cron.
    - [ ] E.1: `IReferralRepository.weekly_summary_by_clan(*, clan_id, since, until) -> Sequence[WeeklyClanReferralEntry]` (домен) + Sql + Fake + integration-тесты.
    - [ ] E.2: use-case `RunWeeklyClanReferralSummary` + DTO + unit-тесты (frozen-clan / нет рефералов / happy-path / top-3 truncation).
    - [ ] E.3: presenter `WeeklyClanReferralSummaryPresenter` + Telegram-notifier `TelegramWeeklyClanReferralSummaryNotifier` + локали `weekly-referral-summary-*` (RU+EN) + тесты presenter / notifier.
    - [ ] E.4: `IDelayedJobScheduler.schedule_weekly_clan_referral_summary_cron()` + APScheduler `CronTrigger(day_of_week='sun', hour=18, timezone='UTC')` + DI в `bot/main.py` + bootstrap-call + composition-root тест.
- [ ] **2.4.F**: rate-limit-антифрод на `RegisterReferral`.
    - [ ] F.1: `IReferralRateLimiter` (домен) + балансовый параметр `referral.antifraud.max_per_referrer_per_hour` (дефолт 10) + audit-action `ANTICHEAT_REFERRAL_RATE_LIMITED`.
    - [ ] F.2: in-memory реализация (`InMemoryReferralRateLimiter`) + Fake + использование в `RegisterReferral` (новая ветка `ReferralRateLimited`-result, handler swallow-ит).
    - [ ] F.3: запись попыток в `audit_log` + unit/integration-тесты + пометка в ГДД §13.1 о принятых ограничениях антифрода.
- [ ] **Перед PR:** обнови «Связанные документы» в `game_design.md` / `development_plan.md`, если расширил поведение.
- [ ] **Перед PR:** прогон локального CI — `make ci` зелёный.
- [ ] **Перед мерджем:** перенеси запись о завершённом спринте в `history.md` (свежие — сверху); удали `AGENT_HANDOFF.md` отдельным коммитом; пересоздай этот чек-лист под следующий спринт.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущая дельта (PR будет про):**
- **2.4.E** — Еженедельный per-clan referral-summary-cron (вс. 18:00 UTC). Узкая реферальная версия weekly-card: «Новых бойцов за неделю + топ-3 приглашателей». Полная клановая weekly-карточка из ГДД §13.3 (PvP / караваны / рейды) — будущий спринт, потому что агрегатов по этим фичам в репозиториях ещё нет.
- **2.4.F** — Rate-limit-антифрод per-`referrer_tg_id` (≤ N новых рефералов в час) + audit-лог попыток. IP/device в aiogram недоступны — закрываю 2.4.4 как «частично» с пометкой в ГДД.
- Затронутые слои: `domain/referral/{entities,repositories,errors}.py`, `application/referral/run_weekly_clan_summary.py`, `bot/notifications/referral.py`, `bot/presenters/referral.py` (расширение), `infrastructure/db/repositories/referral.py` (новый метод), `infrastructure/scheduler/aps.py` (новый cron + callback), `infrastructure/anticheat/in_memory_referral_rate_limiter.py` (или `infrastructure/rate_limit/`), `bot/main.py` (DI), `locales/{ru,en}.ftl`.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- _нет / список_

---

## 🧹 Что делать при передаче работы другому агенту

Если текущий агент не успевает закрыть PR (закончились токены, упал инструментарий, обрыв сессии), **обязательно**:

1. Обнови «Текущая позиция» и чек-лист выше — отметь, что готово, что начато, что не тронуто.
2. Создай `AGENT_HANDOFF.md` в корне репо с расширенным контекстом по шаблону из `CONTRIBUTING.md` («Протокол передачи работы между агентами»).
3. Закоммить + запушь свои текущие наработки на feature-ветку (даже если они не работают — в WIP-коммите явно укажи `WIP:` в заголовке и опиши состояние в теле).
4. Не открывай PR, если ветка в полусломанном состоянии (CI красный, тесты падают): следующий агент откроет PR сам, когда доведёт до зелёного.

Подробнее — в [`../CONTRIBUTING.md`](../CONTRIBUTING.md), секция «Протокол передачи работы между агентами».

---

## ⚪ Бэклог ближайших спринтов (после текущего)

> Краткая выжимка из [`development_plan.md`](development_plan.md). Полные ТЗ — там.

| Спринт | Содержимое (укрупнённо) |
|---|---|
| **2.5** Расширенный админ-интерфейс в боте | `application/admin/*` use-cases, RBAC через `admins`, TOTP-подтверждение опасных команд, `/clan_*`, `/balance_*`, `/audit`, `admin_audit_log` |
| **3.1** Горы и данжон | Новые PvE-локации с риском потери длины, drop тиров |
| **3.2** Караваны (полная механика) | Создание (с уровня 7) + нападение (с уровня 5), лобби 20 мин, 4 роли (лидер / эскорт / защитник / рейдер), боевая механика |
| **3.3** Рейд-боссы | Призыв (с уровня X), управление боссом, лобби, фазы, награды |
| **4.1** Монетизация и масштаб | Stars / TON / USDT, Redis, метрики, доп. локали (PT/ES/TR/ID/FA/UK) |
| **4.5** Опциональная веб-админ-панель 🌐 | FastAPI + Telegram Login + 2FA, RBAC из 2.5, редактор `balance.yaml` |
| **4.9** Канал-анонсы перед публичным релизом 📣 | Публичный TG-канал бота (автопостинг итогов недели, лидербордов, релиз-нот) |

---

## 🔵 Открытые вопросы геймдизу (блокирует часть будущих задач)

> Полный список и история закрытий — в [`development_plan.md`](development_plan.md) §11. Здесь — только то, что **ещё открыто** и блокирует ближайшие спринты.

| ID | Вопрос | Кому | Блокирует |
|---|---|---|---|
| Q9b | Доступ к опциональной веб-админ-панели (если будем делать): VPN / IP-whitelist / Cloudflare Access | PM/devops | Спринт 4.5 (Фаза 4, опционально) |
| Q12b | Финальный триггер для титула «Нежный» (после v9 — был «первый лес», но переехал) | геймдиз | Расширенная таблица титулов (Фаза 3?) |
| Q13 | Конкретные условия и формулировки **остальных** титулов (расширенная таблица) | геймдиз | Расширенная таблица титулов (Фаза 3?) |

> До получения ответов реализовываем **значения по умолчанию из `balance.yaml`**, отмечаем `# TODO(balance):` в коде.

---

*Файл переписывается при каждой смене активного спринта/PR. История завершённых задач — только в `history.md`. Параллельные направления (тесты / балансировка / DevOps / безопасность) — в `development_plan.md` §8.*
