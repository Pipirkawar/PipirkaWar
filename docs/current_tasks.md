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

**На `main`:** последний смерженный спринт — **2.4** (PR #78, коммит `e3a7818`) «Реферальная система и шеринг» (закрыты A→F: домен + persistence + use-cases + интеграция в `/start`/`/upgrade` + кнопка шеринга + weekly cron + rate-limit антифрод). Завершены Фазы 0, 1 (MVP), 1.6 (анти-чит) полностью; из Фазы 2 закрыты 2.1 (PvP 1×1), 2.2 (масс-PvP), 2.3 (Глава клана дня), 2.4 (реферальная система). Идёт **Спринт 2.5 — Расширенный админ-интерфейс в боте**.

**Активная feature-ветка:** `devin/1778087829-sprint-2-5-a-admin-foundation` (первый из четырёх PR-ов спринта 2.5). Бралась свежий `main` на момент создания.

**Что уже есть в коде (из Спринтов 1.1.E + 1.2.B + 1.6):**
- `domain/admin/{entities,repositories}.py` — `Admin` VO + `AdminRole` enum (`super_admin`/`economist`/`support`/`read_only`) + `IAdminRepository`.
- `infrastructure/db/{models,repositories}/admin.py` + Fake в `tests/fakes/admin_repo.py`. Таблица `admins` в миграции `0001_initial_security_schema`.
- `application/bootstrap/admin.py` — `BootstrapSuperAdmin` (читает `BOOTSTRAP_ADMIN_IDS`).
- `bot/handlers/admin.py` — рабочие `/balance_reload`, `/admin_stats`, `/set_max_dau`, `/anticheat_unban` (авторизация на уровне use-case-а).
- Пустые пакеты `src/pipirik_wars/admin/{api,auth,rbac,web}/` — зарезервированы под веб-админку в Спринте 4.5.

**Скоуп Спринта 2.5 (разбивается на 4 PR-а):**
- **2.5-A** (текущая ветка): каркас — `admin_audit_log` table, `AdminGuard` aiogram-middleware, FSM `TOTPConfirm` + use-cases `RequestAdminConfirm`/`VerifyAdminConfirm`, локали. Без полезных команд.
- **2.5-B** (следующий PR): команды поддержки — `/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban` (TOTP только на `/ban`).
- **2.5-C**: экономика — `/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set` + TOTP на все + идемпотентность.
- **2.5-D** (финал): кланы + `/announce` + `/audit` + `docs/admin_runbook.md`.

**`make ci` на main:** зелёный (последний прогон в PR #78: 2829 passed / 1 skipped, coverage 96.11%).

**`AGENT_HANDOFF.md`:** нет (удалён в `2c4b588`).

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте` |
| **Активный PR / шаг** | **2.5-A**: каркас (admin_audit_log + AdminGuard + TOTP-FSM) |
| **Активная feature-ветка** | `devin/1778087829-sprint-2-5-a-admin-foundation` (от `e3a7818`) |
| **Базовая ветка** | `main` |
| **Последний коммит на ветке** | `2af84c0` `chore(docs): sync current_tasks.md под Спринт 2.5-A` |
| **PR (если открыт)** | ещё не открыт; будет открыт как 2.5-A после закрытия всех шагов ниже |
| **CI статус** | зелёный (последний прогон в PR #78: 2829 passed / 1 skipped, coverage 96.11%) |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задачи 2.5.1–2.5.10 |
| **Связанная спецификация в `game_design.md`** | §18.6 (основной канал администрирования — Telegram-бот) |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**PR 2.5-A — каркас расширенного админ-интерфейса:**

- [x] sync `current_tasks.md` под 2.5.
- [x] **2.5-A.1** — таблица `admin_audit_log` (миграция `0016_admin_audit_log` + ORM `AdminAuditLogORM` + домен-порт `IAdminAuditLogger` + `AdminAuditEntry` + `AdminAuditAction` + `AdminAuditSource` + `SqlAlchemyAdminAuditLogger` + `FakeAdminAuditLogger` + 6 integration-тестов + 4 unit-теста + расширение `test_migrations`).
- [x] **2.5-A.2** — aiogram-middleware `AdminGuard` (читает `tg_identity`, делает `IAdminRepository.get_by_tg_id`, кладёт `data["admin"] = Admin | None`; деактивированные → `None`). Регистрируется в композиционном root, прибавляется ко всем 3 observer-ам после `AuthMiddleware`. 7 unit-тестов + апдейт композиционного теста.
- [ ] **2.5-A.3** — FSM `TOTPConfirm` + use-cases `RequestAdminConfirm`/`VerifyAdminConfirm` + локали `admin-confirm-*` RU+EN + unit-тесты.
- [ ] **Перед PR:** прогон `make ci` зелёный, lint/typecheck/import-linter ✅.
- [ ] **Перед мерджем:** sync `current_tasks.md` под 2.5-B; запись в `history.md`.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущая дельта (PR 2.5-A будет про):**
- **2.5-A.1 — аудит админ-мутаций.** Новая таблица `admin_audit_log` (отдельная от общего `audit_log`, чтобы /audit по админам был быстрым). Поля по ГДД §18.6: `admin_id, action, target_kind, target_id, before_jsonb, after_jsonb, reason, source ('bot'|'web'), idempotency_key, tg_chat_id, ip, occurred_at`.
- **2.5-A.2 — AdminGuard middleware.** aiogram outer-middleware: из `event.from_user.id` ищет `Admin` в репо, если нет / `is_active=False` — выход без передачи update-а в router (тихий игнор); иначе кладёт `data['admin']` и передаёт дальше. Регистрируется на admin-router в `bot/main.py`.
- **2.5-A.3 — TOTP-confirm FSM.** Use-cases `RequestAdminConfirm(admin_id, command_kind, target, payload_jsonb) -> str (token)` и `VerifyAdminConfirm(admin_id, token, code) -> ConfirmResult`. FSM в памяти бота (`InMemoryAdminConfirmStore`, TTL 60c). Верификация TOTP-кода через `admins.totp_secret` (`pyotp`). Аудит неверных кодов.
- Затронутые слои: `domain/admin/{entities,errors,ports/admin_audit.py,ports/admin_confirm.py}`, `application/admin/{request_confirm,verify_confirm}.py`, `bot/middlewares/admin_guard.py`, `infrastructure/db/{models,repositories}/admin_audit.py`, `infrastructure/db/migrations/versions/20260507_0016_admin_audit_log.py`, `infrastructure/admin/in_memory_confirm_store.py`, `infrastructure/admin/pyotp_totp_verifier.py`, `bot/main.py` (DI), `locales/{ru,en}/admin.ftl`.

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
