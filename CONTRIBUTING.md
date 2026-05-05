# Контрибьютинг в Pipirik Wars

Этот файл — обязательное чтение перед открытием PR. Если что-то непонятно — смотри `docs/pipirik_wars_plan.md` §0 (Политика разработки) и `docs/development_plan.md` §0 (DevOps + чек-листы).

> **Цель:** надёжный, безопасный, поддерживаемый код. SOLID + clean architecture + security-first. CI gate-ов много, и они **обязательны**.

---

## Прежде чем начать

1. **Прочитать ГДД §0** — `docs/pipirik_wars_plan.md`. Это политика разработки (SOLID/ООП/безопасность). Каждый PR проходит чек-лист именно отсюда.
2. **Прочитать план**:
    - `docs/development_plan.md` — фазы / спринты / задачи.
    - `docs/current_tasks.md` — что в работе **сейчас**. Брать задачу отсюда.
3. **Поднять окружение** — см. [README.md](README.md) «Локальная разработка».

## Workflow PR-а

1. **Завести feature-branch.** Формат: `devin/<unix_timestamp>-<short-slug>`. Никогда не пушить напрямую в `main`.
2. **Реализовать фичу с тестами.** Покрытие `domain/` + `application/` ≥ 80 %. Без тестов PR не мерджится.
3. **Прогон локального CI:** `make ci`. Должен быть зелёным **до** пуша.
4. **Открыть PR** в `main`. Описание — по шаблону `.github/pull_request_template.md` (если есть) или ad-hoc:
    - **Summary** — что и зачем.
    - **Risk** — green/yellow/red. Yellow/red требуют отдельного объяснения.
    - **Testing checklist** — что ревьюер должен проверить руками.
5. **CI должен пройти.** Лента CI: lint+types+tests на 3.11 + 3.12, pip-audit (security). Все обязательны.
6. **Code review.** Минимум 1 апрув. Замечания — в новых коммитах (амендить нельзя — см. ниже).
7. **Squash merge.** История `main` остаётся чистой.
8. **После мержа:**
    - запись в `docs/history.md` (свежие — сверху, формат — см. шапку файла);
    - удалить/обновить строку в `docs/current_tasks.md` (✅ смержено / убрать).

### Правила git

- **НЕ** делать `git commit --amend` после первого пуша — портит ревью-ленту. Только новые коммиты.
- **НЕ** force-push в `main`. В feature-branch — только `--force-with-lease` после ребейза.
- **НЕ** коммитить `.env`, секреты, dump-ы БД. `.gitignore` это закрывает, но контролируйте `git add` руками.
- **НЕ** ставить `--no-verify` на pre-commit hooks. Если хук падает — пофиксить причину, а не обходить.
- **НЕ** менять `git config` в репо.

## Чек-лист SOLID + ГДД §0

Каждый PR должен проходить:

- [ ] **SRP** — каждый класс/модуль ровно одна ответственность.
- [ ] **OCP** — расширяемость через новые реализации портов, а не через `if isinstance` в core-коде.
- [ ] **LSP** — все реализации портов взаимозаменяемы; контракт описан в Protocol/ABC.
- [ ] **ISP** — порты узкие (read-side / write-side разделены: `IBalanceConfig` vs `IBalanceReloader`).
- [ ] **DIP** — `domain` и `application` зависят только от Protocol-ов; реализации в `infrastructure`.
- [ ] **Тестируемость** — use-case-ы тестируются с FakeUnitOfWork / FakeRandom / FakeClock без БД.
- [ ] **Никакой случайности и времени** в `domain/application` напрямую — только через `IRandom` / `IClock`.

## Чек-лист безопасности

- [ ] **Транзакции** — все state-mutations в `application` идут через `IUnitOfWork.transaction()`. Никаких «частичных» успехов.
- [ ] **Idempotency** — write-path-команды защищены `IIdempotencyService` с осмысленным ключом.
- [ ] **Audit log** — каждое изменение состояния пишет audit-запись через `IAuditLogger`. Никаких «тихих» апдейтов.
- [ ] **RBAC / AuthContext** — admin-only handler-ы провалидированы через `AuthContext`-middleware. Никаких ручных проверок `tg_id == ...`.
- [ ] **Activity lock** — конкурирующие действия на одного игрока (например, повторный `/forest`) защищены `IActivityLockService`.
- [ ] **Rate limit** — публичные команды проходят через `ThrottleMiddleware` (token-bucket).
- [ ] **Никаких секретов в код / git / логи** — только через env. `SecretStr.__repr__` маскирует значение.
- [ ] **Без `Any`, `getattr`, `setattr`** — типы выписаны явно, mypy --strict проходит.

## CI gates (обязательны)

| Gate | Команда | Что проверяет |
|---|---|---|
| ruff | `make lint` | Стиль (PEP 8, импорты, line length) + базовые баги. |
| mypy --strict | `make typecheck` | Все аннотации обязательны; `Any` запрещён. |
| import-linter | `make imports` | Контракт слоёв clean architecture. |
| pytest | `make test` | Все тесты + coverage ≥ 80 % (`--cov-fail-under=80`). |
| pip-audit | `make audit` | CVE-проверка зависимостей (отдельной job-ой в CI). |

Локально всё разом — `make ci`.

## Структура тестов

```
tests/
├── unit/             # быстрые, in-memory, без сети и БД
│   ├── domain/       # чистая бизнес-логика (entities, services)
│   └── application/  # use-cases с FakeUnitOfWork / FakeRandom / FakeClock
├── integration/      # БД + миграции (через aiosqlite в CI)
├── load/             # параллельные сценарии (race-conditions)
└── fakes/            # in-memory реализации портов
```

**Правило:** unit-тест не должен зависеть от БД, сети, времени, случайности — всё через Fake-реализации портов. Integration-тесты включают БД (через `aiosqlite`) и проверяют реальные SQL-репо + миграции.

## Локализация

Все user-facing строки — через `IMessageBundle` (Mozilla Fluent), не через f-string в коде.

- Ключи: `<domain>-<screen>-<state>` (пример: `forest-finished-name-drop`, `profile-card`).
- Числа: `NUMBER($x, useGrouping: 0)` — иначе Fluent втыкает NBSP между разрядами.
- Bidi-isolation в `FluentMessageBundle` отключён (`use_isolating=False`), чтобы `\u2068`/`\u2069` не засоряли вывод.
- Файлы локалей: `locales/ru.ftl`, `locales/en.ftl`. Ключи синхронны — отсутствие ключа в одной из локалей валит integration-тест.

## Балансные данные

`config/balance.yaml` — источник правды для всех числовых констант (длины, веса, кулдауны, исходы леса). Hot-reload через `/balance_reload` (admin-only).

- **Никогда** не хардкодить балансные числа в коде.
- Изменения структуры — обновлять pydantic-схемы в `domain/balance/config.py`.
- Изменения значений — обновлять `config/balance.yaml`. Никаких миграций — только перезагрузка.

JSON-каталоги (`config/templates/*.json`):
- `oracle_{ru,en}.json` — предсказания дня (≥ 200 шаблонов на локаль).
- `forest_logs_{ru,en}.json` — забавные логи леса (≥ 300 шаблонов на локаль; в текущем релизе 350).
- Допустимые плейсхолдеры регламентированы по каталогу — см. integration-тесты `tests/integration/templates/`.

## История и задачи

- `docs/history.md` — хронологический журнал. Свежие записи **сверху**. Формат — см. шапку файла. Каждый PR (mvp-фичу) пишет туда запись.
- `docs/current_tasks.md` — текущие спринты. После мержа PR — статус задачи меняется на ✅ смержено или строка убирается, если спринт закрыт.

## Вопросы / помощь

Если что-то непонятно — смотри `docs/`, потом задавай вопрос в issue/PR. Не ломай контракты архитектуры «по-быстрому». Лучше потратить лишний день на правильную абстракцию, чем неделю на разгребание последствий.
