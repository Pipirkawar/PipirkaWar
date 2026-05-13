# AGENT_HANDOFF — Спринт 4.1-K «i18n: расширение каталога локалей»

> **Sticky-файл по протоколу CONTRIBUTING.md «Уходящий агент».** Обновляется в каждом коммите этой feature-ветки до открытия PR-а. Удаляется отдельным коммитом перед `git_pr(action="create")` (`chore: remove AGENT_HANDOFF before PR`).

## Контекст

- **PR в работе:** **4.1-K** — i18n: расширение каталога локалей (PT, ES, TR, ID, FA, UK).
- **Базируется на:** `main = 8a3e729` (merge PR #138 4.1-J).
- **Ветка:** `devin/1778662554-sprint-4-1-K-i18n-extra-languages`.
- **Сессия (текущая):** https://app.devin.ai/sessions/f9b7820cdcef4ef59385b24f323c3dce.
- **Baseline `make ci` на `main = 8a3e729`:** **6994 passed + 2 skipped + 95 % cov, 548.52 с**.
- **Задача из ПД §7:** **4.1.14** — «Доп. языки: PT, ES, TR, ID, FA, UK. Файлы переводов, тест fallback.»
- **Соседние задачи (отложены в отдельные PR-ы):** 4.1.13 (ИИ-предсказания, опц.) → PR 4.1-M; 4.1.15 (Grafana-дашборд для метрик 4.1-J) → PR 4.1-L.

## Что уже сделано (текущая i18n-инфраструктура на `main`)

- `SUPPORTED_LOCALES = frozenset({"ru", "en"})` + `DEFAULT_LOCALE = Locale("en")` в `src/pipirik_wars/application/i18n/locale.py`.
- `LocaleResolver.resolve(tg_lang)` — prefix-match на lowercase tg-language-code; stateless.
- `FluentMessageBundle` (`src/pipirik_wars/infrastructure/i18n/fluent_bundle.py`) — lazy-load `locales/{code}.ftl` через `Path`, fallback на EN если ключа нет, threading.Lock на первой загрузке.
- БД: `users.locale_override TEXT NULL` + CHECK-constraint `locale_override IS NULL OR locale_override IN ('ru', 'en')` (Alembic `0006_users_locale_override`).
- `LangPresenter.confirmed(locale)` — if-else на `locale.code` → `lang-set-ru` / `lang-set-en`.
- `locales/{en,ru}.ftl` — по ~1600 ключей каждый.
- Текущий Alembic-HEAD: `0007_anticheat_foundation`.

## Скоуп 4.1-K (согласован с пользователем — вариант A)

- Расширить `SUPPORTED_LOCALES` до 8 значений: `+ pt, es, tr, id, fa, uk`.
- DB: новая Alembic-миграция `0008_users_locale_override_extended_languages` (drop+recreate CHECK).
- 6 новых `.ftl`-файлов с **30-50 ключевыми ключами** (`start-*`, `profile-*`, `lang-*`) — перевод вручную модельным знанием. Остальные ~1550 ключей рендерятся через **fallback на EN** (механизм уже есть в `FluentMessageBundle`).
- `LangPresenter.confirmed()` — добавить 6 новых веток + 6 новых `_KEY_SET_*` MessageKey-констант. `lang-set-{pt,es,tr,id,fa,uk}` ключи в `en.ftl` + `ru.ftl`. Обновить `lang-usage`/`lang-unsupported`.
- Fallback-тесты для каждой из 6 новых локалей: запрос ключа существующего только в EN → возвращается EN; запрос ключа существующего и в PT и в EN → возвращается PT.

## Шаги PR-а (K.0–K.6)

* [x] **K.0** — Snapshot pivot `docs/current_tasks.md` + sticky `AGENT_HANDOFF.md` (commit `76c2a91`). Baseline `make ci` зелён.
* [x] **K.1** — Application/domain: `SUPPORTED_LOCALES = frozenset({"ru","en","pt","es","tr","id","fa","uk"})` + LocaleResolver-тесты для 16 BCP-47-вариантов 6 новых локалей. Обновлён расширенный docstring `application/i18n/locale.py`. 54 tests passed.
* [ ] **K.2** — Infrastructure DB: Alembic-миграция `0008` + UserORM CheckConstraint + integration-тест миграции.
* [ ] **K.3** — 6 новых `.ftl`-файлов в `locales/{pt,es,tr,id,fa,uk}.ftl` с 30-50 ключевыми ключами на язык.
* [ ] **K.4** — `LangPresenter.confirmed()` + 6 `_KEY_SET_*` + `lang-set-{pt,es,tr,id,fa,uk}` в `en.ftl`+`ru.ftl` + `lang-usage`/`lang-unsupported` + handler/presenter-тесты.
* [ ] **K.5** — Fallback-тесты `FluentMessageBundle` (параметризовано на 6 новых локалей).
* [ ] **K.6** — Doc-sync (`docs/history.md` + `docs/current_tasks.md`).
* [ ] **K.7** — Удалить этот `AGENT_HANDOFF.md` + `git_pr(create)` + `git(pr_checks, wait_mode="all")`.

## Что НЕЛЬЗЯ делать

- Не менять default-локаль (`DEFAULT_LOCALE = Locale("en")` — backward-compat).
- Не удалять `locales/en.ftl` / `ru.ftl` — это рабочие файлы, новые добавляются параллельно.
- Не амендить коммиты, не force-push на main.
- Не добавлять новые **non-MVP-ключи** в `.ftl`-файлы (только то, что уже есть на EN/RU).
- Не пропускать `pre-commit` (mypy + ruff + import-linter).

## Команды

```bash
make ci                   # ruff + mypy + import-linter + pytest (~9 мин)
pre-commit run --all-files
```

## Текущее состояние коммитов на ветке

- `76c2a91` — `docs(4.1-K): K.0 — snapshot pivot + sticky AGENT_HANDOFF`
- (этот коммит K.1) `feat(4.1-K): K.1 — expand SUPPORTED_LOCALES to 8 (+pt/es/tr/id/fa/uk)`
