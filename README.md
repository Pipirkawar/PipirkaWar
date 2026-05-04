# 🍆 Пипирик Варс

Telegram-бот PvP/PvE-игры с прокачкой «пипирика», походами, караванами, рейдами и кланами.

Этот репозиторий содержит **документацию проекта** и подготовленный **каркас структуры** будущего кода.

## 📚 Документация

- [`docs/pipirik_wars_plan.md`](docs/pipirik_wars_plan.md) — Игровой Дизайн-Документ (ГДД v7).
- [`docs/development_plan.md`](docs/development_plan.md) — Подробный план разработки по фазам и спринтам.
- [`docs/current_tasks.md`](docs/current_tasks.md) — Текущие задачи (актуальный спринт).
- [`docs/history.md`](docs/history.md) — Хронологический журнал выполненных работ.

> ⚠️ **Перед началом любой работы** — прочитать §0 ГДД («Политика разработки»: SOLID/ООП/безопасность). Эти требования обязательны.

## 🧱 Архитектура

Проект построен по принципам **clean architecture**:

```
domain/         ← чистая бизнес-логика (зависит только от себя)
   ↑
application/    ← use-cases (оркестрация домена)
   ↑
infrastructure/ ← реализации портов (PG, Redis, APScheduler, Telegram, платежи)
   ↑
bot/  +  admin/ ← тонкие слои (aiogram handlers / FastAPI endpoints)
```

Зависимости направлены строго **внутрь**. Импорт `domain → infrastructure` блокируется CI (`import-linter`).

См. [`docs/development_plan.md`](docs/development_plan.md) §2 для полной структуры.

## 📂 Структура репозитория

```
.
├── docs/                  # документация (ГДД, план, история, задачи)
├── src/pipirik_wars/      # код проекта
│   ├── domain/            # чистый домен
│   ├── application/       # use-cases
│   ├── infrastructure/    # PG, Redis, Telegram, платежи, i18n, шаблоны
│   ├── bot/               # aiogram (тонкий слой)
│   ├── admin/             # FastAPI веб-панель
│   └── shared/            # logger, metrics, errors
├── tests/                 # unit / integration / e2e
├── config/                # настройки, balance.yaml, локали
├── ops/                   # docker, deploy, runbooks
└── .github/workflows/     # CI
```

## 🚀 Текущий статус

Проект на этапе **Фазы 0 — Фундамент** (см. [`docs/current_tasks.md`](docs/current_tasks.md)).

Каркас директорий подготовлен, но кода ещё нет — Фаза 0 как раз посвящена настройке инфраструктуры (CI, lint, mypy --strict, import-linter, idempotency, audit log, activity lock) до того, как начать писать геймплей.

## 🔐 Политика разработки (кратко)

- **SOLID/ООП** — обязательно. Каждый PR проходит чек-лист.
- **Безопасность и целостность данных** — приоритет №1. Транзакции, idempotency, audit log, RBAC.
- **Тесты** — покрытие `domain/` + `application/` ≥ 80 %.
- **CI gates**: `ruff`, `mypy --strict`, `pytest`, `pip-audit`, `import-linter`.
- **Никаких прямых пушей в `main`** — только через PR с code review.

Полный текст — в [`docs/pipirik_wars_plan.md`](docs/pipirik_wars_plan.md) §0.

## 🤝 Как участвовать

1. Прочитать ГДД §0 и план разработки §0.
2. Взять задачу из `docs/current_tasks.md`.
3. Завести feature-branch.
4. Реализовать с тестами, пройти SOLID + security чек-лист.
5. Открыть PR. Дождаться CI и ревью.
6. После мержа — записать выполненное в `docs/history.md`, удалить задачу из `docs/current_tasks.md`.

## 📜 Лицензия

TBD.
