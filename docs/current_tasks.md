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

**На `main`:** последний смерженный спринт — **2.5-A** ([PR #79](https://github.com/Pipirkawar/PipirkaWar/pull/79), коммит `b358349`) «Каркас расширенного админ-интерфейса в боте» — `admin_audit_log` table + `AdminGuard` aiogram-middleware + TOTP-confirm scaffold (миграция `0017_admins_totp_secret`, доменные VO/порты, use-case-ы `RequestAdminConfirm`/`VerifyAdminConfirm`, in-memory store + `pyotp`-verifier, локали `admin-confirm-*`). Завершены Фазы 0, 1 (MVP), 1.6 (анти-чит) полностью; из Фазы 2 закрыты 2.1–2.4 целиком и **2.5-A** — каркас идущего сейчас спринта 2.5. Идёт **Спринт 2.5-B** (команды поддержки в боте: `/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban`).

**Активная feature-ветка:** `devin/1778094141-sprint-2-5-b-support-commands` (от `a967197`).

**Что уже есть в коде после 2.5-A:**
- `domain/admin/{audit,confirm,entities,repositories}.py` + `domain/admin/ports/{admin_audit,admin_confirm}.py` — доменные VO `Admin` / `AdminAuditEntry` / `AdminConfirm{Request,Entry}` + ошибки + enum-ы + порты `IAdminAuditLogger` / `IAdminConfirmStore` / `ITotpVerifier`.
- `application/admin/{request_confirm,verify_confirm}.py` — use-case-ы TOTP-confirm. Каркас под use-case-ы команд поддержки/экономики (2.5-B/C) идёт рядом, в этом же пакете.
- `application/bootstrap/admin.py` — `BootstrapSuperAdmin` (читает `BOOTSTRAP_ADMIN_IDS`).
- `infrastructure/db/{models,repositories}/{admin,admin_audit}.py` + Sql/Fake реализации портов; миграции `0016_admin_audit_log`, `0017_admins_totp_secret`.
- `infrastructure/admin/{in_memory_confirm_store,pyotp_totp_verifier}.py` — реализации портов TOTP-confirm.
- `bot/middlewares/admin_guard.py` + DI в `bot/main.py` — `data["admin"]` доступен handler-ам.
- `bot/handlers/admin.py` — рабочие `/balance_reload`, `/admin_stats`, `/set_max_dau`, `/anticheat_unban` (старые, с авторизацией на уровне use-case-а; в 2.5-D будут перенесены под `AdminGuard` + RBAC).
- `locales/{ru,en}.ftl` — `admin-confirm-*` ключи.
- Пустые пакеты `src/pipirik_wars/admin/{api,auth,rbac,web}/` — зарезервированы под веб-админку в Спринте 4.5.

**Скоуп Спринта 2.5 (4 PR-а):**
- ~~**2.5-A**~~ ✅ закрыт PR #79 (`b358349`) — каркас `admin_audit_log` + `AdminGuard` + TOTP-confirm.
- **2.5-B** (текущий PR): команды поддержки — `/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban` (TOTP только на `/ban`).
- **2.5-C**: экономика — `/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set` + TOTP на все + идемпотентность.
- **2.5-D** (финал): кланы (`/clan`, `/freeze_clan`, `/unfreeze_clan`, `/clan_daily_head_history`) + `/announce` + `/audit` + `/admin_setup_totp` + `docs/admin_runbook.md`.

**`make ci` на ветке 2.5-B:** зелёный — `lint` (ruff) ✅, `typecheck` (mypy --strict, 629 файлов, 0 issues) ✅, `imports` (import-linter, 3 контракта) ✅, `test` 2997 passed / 1 skipped, coverage 96.18%.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте` |
| **Активный PR / шаг** | **2.5-B**: команды поддержки (`/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban`) |
| **Активная feature-ветка** | `devin/1778094141-sprint-2-5-b-support-commands` |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `a967197` (мерж PR #80 «Спринт 2.5-A postmerge docs sync») |
| **PR (если открыт)** | _ещё не открыт_ |
| **CI статус** | локально зелёный (`make ci` на `3c016b7`); ждём GitHub CI после открытия PR |
| **Последний коммит на ветке** | `3c016b7` (Sprint 2.5-B.7: DI use-cases в `Container`) |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задачи 2.5.3 (find_player/player/freeze/unfreeze/ban), 2.5.5 (TOTP на /ban), 2.5.9 (use-case каркас) |
| **Связанная спецификация в `game_design.md`** | §18.6 (основной канал администрирования — Telegram-бот) |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**PR 2.5-B — команды поддержки:**

- [x] **2.5-B.1 — `/find_player <text>`** — поиск игрока по `tg_id` (точно), `@username` (точно), либо подстроке (ILIKE по `username`/`name`). Use-case `FindPlayers(query, limit) -> Sequence[PlayerSummary]`. Без TOTP. Запись `ADMIN_PLAYER_LOOKUP` в `admin_audit_log`. Локаль `admin-find-player-*` (RU+EN).
- [x] **2.5-B.2 — `/player <tg_id>`** — карточка игрока: сводка (длина, толщина, статус, anticheat-soft-ban-таймер), клан + роль, активный forest-run. Use-case `GetPlayerCard(tg_id) -> PlayerCard`. Без TOTP. Запись `ADMIN_PLAYER_LOOKUP`. Локаль `admin-player-*` (RU+EN). Список последних 5 PvP/PvE-боёв вынесен в B-followup: ни `IDuelRepository`, ни `IMassDuelRepository`, ни `IForestRunRepository` не имеют метода «список последних N для игрока» — добавлять новые read-методы поверх существующих агрегатов в скоуп B.2 не входит, но это закроет full-feature-карточку.
- [x] **2.5-B.3 — `/freeze <tg_id> [reason]`** / **`/unfreeze <tg_id>`** — установка `is_frozen=True/False` через `IPlayerRepository`. Use-cases `FreezePlayer` / `UnfreezePlayer`. Без TOTP (обратимая операция). Запись `ADMIN_PLAYER_FROZEN` / `ADMIN_PLAYER_UNFROZEN` с `before/after`. Идемпотентно: повторная заморозка/разморозка ничего не пишет в audit, возвращает `was_already_frozen=True` / `was_already_active=True`. Локали `admin-freeze-*` / `admin-unfreeze-*` (RU+EN).
- [x] **2.5-B.4 — `/ban <tg_id> <reason>`** — необратимый бан. Добавлено: `PlayerStatus.BANNED`, `Player.ban(now)` (идемпотентно). Use-case `BanPlayer` (post-TOTP, с защитой-в-глубину `is_active` + reason-нон-empty). Handler `/ban` зовёт `RequestAdminConfirm(command_kind="ban", payload={target_tg_id, reason})`, отвечает токеном и инструкцией `/confirm <token> <code>`. Запись `ADMIN_PLAYER_BANNED` (на успешном бане). `ADMIN_BAN_BLOCKED` решено НЕ выписывать отдельно — `VerifyAdminConfirm` уже пишет `ADMIN_CONFIRM_FAILED` с привязкой `command_kind=ban`, дублирование не нужно (это можно поднять в /audit-фильтре). Локали `admin-ban-*` (RU+EN).
- [x] **2.5-B.5 — `/confirm <token> <code>`** — общий handler для всех TOTP-команд. Зовёт `VerifyAdminConfirm`, диспатчит по `command_kind`: на MVP только `ban → BanPlayer.execute()`. На неизвестный `command_kind` или сломанный payload — `admin-confirm-unknown-command-kind`. Локали `admin-confirm-*` (RU+EN).
- [x] **2.5-B.6 — Регистрация `admin_support_router`** через `dispatcher.include_router` в `bot/handlers/__init__.py`. Router-фильтр `IsAdminFilter` живёт прямо на самом router-е (`router.message.filter(IsAdminFilter())` + `.callback_query.filter(...)`), читает `data["admin"]` от `AdminGuard`. Не-админы тихо проходят мимо (filter возвращает `False`). Если `AdminGuard` не подключён — secure default = отказать. Файлы: `bot/filters/admin.py`, `bot/filters/__init__.py`, `bot/handlers/admin_support.py` (фильтр на router-е), `bot/handlers/__init__.py` (include_router). 4 unit-теста на фильтр.
- [x] **2.5-B.7 — DI use-case-ов в `Container`** — `find_players`, `get_player_card`, `freeze_player`, `unfreeze_player`, `ban_player`, `request_admin_confirm`, `verify_admin_confirm` + `SqlAlchemyAdminAuditLogger` (write-side `admin_audit_log`), `InMemoryAdminConfirmStore` (singleton, переживать рестарт смысла нет — 60-секундные токены), `PyOtpTotpVerifier`, `TokenFactory = _default_admin_token_factory` (`secrets.token_urlsafe(16)`). Все 7 use-case-ов прокинуты в `dispatcher` workflow-data. Тесты: 2 новых assert-ов в `test_composition_root.py` (`TestContainer.test_container_holds_admin_support_use_cases` + расширения в `TestBuildContainer.test_build_container_returns_real_adapters` и `TestBuildDispatcher.test_build_dispatcher_assembles_full_stack`).
- [x] **2.5-B.8 — Тесты:** покрытие добавлено вместе с каждым шагом B.1–B.7. Unit-тесты на все use-case-ы — `tests/unit/application/admin/test_find_players.py` (9), `test_get_player_card.py` (7), `test_freeze_unfreeze.py` (8), `test_ban_player.py` (7). Integration на `IPlayerRepository`: `find_by_query_*` (7 кейсов: exact tg_id / @username / substring case-insensitive / empty / LIKE-escape / включая frozen / limit / non-positive limit reject), `freeze_unfreeze_round_trip`, `save_persists_mutations` (покрывает `Player.ban` через `save`), а также существовавшие `anticheat_ban_*`. E2E на TOTP-flow `/ban`+`/confirm` — `tests/unit/bot/handlers/test_admin_support.py` (44 кейса, в т.ч. happy / token expired / token not found / admin mismatch / code invalid / TOTP not configured / unknown command_kind / payload typo / target disappeared / already banned).
- [x] **Перед PR:** локальный `make ci` зелёный — lint ✅, mypy --strict ✅, import-linter ✅, pytest 2997/1 skipped, coverage 96.18%.
- [ ] **Перед мерджем:** sync `current_tasks.md` под 2.5-C; запись в `history.md`.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущая дельта (PR 2.5-B будет про):**
- Команды поддержки **без выдачи длины/толщины/банвейв-операций над балансом** (это всё в 2.5-C). Только заморозка / разморозка / бан / lookup.
- Новый router `admin_support_router` подцепляется к dispatcher в `bot/main.py` поверх существующего `AdminGuard` (тот уже регистрируется в композиционном root после мерджа 2.5-A).
- Новые методы `IPlayerRepository`: `find_by_query(query, limit)`, `get_card(tg_id)`, `freeze(tg_id, *, reason)`, `unfreeze(tg_id)`, `ban(tg_id, *, reason)`. Реализуем в `SqlAlchemyPlayerRepository` + `FakePlayerRepository`.
- Новые `AdminAuditAction` константы: `ADMIN_PLAYER_LOOKUP`, `ADMIN_PLAYER_FROZEN`, `ADMIN_PLAYER_UNFROZEN`, `ADMIN_PLAYER_BANNED`, `ADMIN_BAN_BLOCKED` (последний — когда TOTP-подтверждение провалилось до выполнения мутации).
- Затронутые слои: `domain/admin/ports/admin_audit.py` (расширяем enum), `domain/player/{entities,ports/player_repository.py}` (методы поиска/freeze/ban), `application/admin/*.py` (новые use-case-ы), `infrastructure/db/repositories/player.py` (Sql-impl), `tests/fakes/player_repo.py` (Fake-impl), `bot/handlers/admin_support.py` (новый файл) + регистрация router-а в `bot/main.py`, `locales/{ru,en}.ftl`.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- _нет_

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
| **2.5-C** Админ-интерфейс — экономика | `/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set` + TOTP на все + idempotency_key из `(admin_id, command, target, minute)` |
| **2.5-D** Админ-интерфейс — финал | `/clan`, `/freeze_clan`, `/unfreeze_clan`, `/clan_daily_head_history`, `/announce`, `/audit`, `/admin_setup_totp`, `docs/admin_runbook.md` |
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
