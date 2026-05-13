# AGENT_HANDOFF — Спринт 4.1-K «i18n: расширение каталога локалей»

> **Sticky-файл по протоколу CONTRIBUTING.md «Уходящий агент».** Обновляется в каждом коммите этой feature-ветки до открытия PR-а. Удаляется отдельным коммитом перед `git_pr(action="create")` (`chore: remove AGENT_HANDOFF before PR`).

## Контекст

- **PR в работе:** **4.1-K** — i18n: расширение каталога локалей (PT, ES, TR, ID, FA, UK).
- **Базируется на:** `main = 8a3e729` (merge PR #138 4.1-J).
- **Ветка:** `devin/1778662554-sprint-4-1-K-i18n-extra-languages`.
- **Сессия (текущая):** https://app.devin.ai/sessions/dc53351a3caf438ea211fc897a110dc0 (предыдущая: https://app.devin.ai/sessions/f9b7820cdcef4ef59385b24f323c3dce — K.0–K.2).
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
* [x] **K.1** (commit `a7dc59d`) — Application/domain: `SUPPORTED_LOCALES = frozenset({"ru","en","pt","es","tr","id","fa","uk"})` + LocaleResolver-тесты для 16 BCP-47-вариантов 6 новых локалей. 54 tests passed.
* [x] **K.2** (commit `465dd52`) — Infrastructure DB: Alembic-миграция `0039_users_locale_override_extended_languages` (revises `0038_ton_connect_nonces`, текущий HEAD), drop+recreate CHECK в `batch_alter_table("users")`. UserORM CheckConstraint обновлён для 8 локалей. Integration-тесты `tests/integration/db/test_migrations.py`: 3 новых теста (revision в list, descends-from, файл в dir-listing) + 2 новых INSERT-теста (все 8 локалей + NULL проходят, `fr` роняет IntegrityError; downgrade → 0038 роняет `pt`). 46 migration-tests passed.
* [x] **K.3** (commit `dd7fa5e`) — 6 новых `.ftl`-файлов в `locales/{pt,es,tr,id,fa,uk}.ftl`. Каждый файл содержит ~34 онбординг-ключа (`start-*` ×6, `profile-*` ×6, `top-*` ×3, `clantop-*` ×3, `forest-*` ×10, `lang-*` ×6 включая `lang-set-<own>`). Остальные ~1550 ключей рендерятся через `FluentMessageBundle`-fallback на EN. Smoke-test через `FluentMessageBundle.format`: все 6 локалей загружаются, EN-fallback (`oracle-success-prediction`) работает.
* [x] **K.4** (commit `809e11f`) — `LangPresenter.confirmed()` переведён с `if/elif`-цепочки на словарь `_KEY_SET_BY_LOCALE: dict[str, MessageKey]` (8 вхождений, dispatch по `locale.code`, fallback на EN). 6 новых ключей `lang-set-{pt,es,tr,id,fa,uk}` добавлены в `en.ftl` и `ru.ftl`. `lang-usage`/`lang-unsupported`/`lang-not-registered` в обоих файлах перечисляют все 8 поддерживаемых кодов. Тесты: `test_lang.py` (презентер) параметризован на 8 локалей; `test_lang.py` (handler) +6 параметризованных кейсов для новых локалей; `test_set_locale.py` «sets override» параметризован на все 8. 43 lang-related tests passed.
* [x] **K.5** (commit `726fe4d`) — Параметризованные fallback-тесты `FluentMessageBundle` в `tests/unit/infrastructure/i18n/test_fluent_bundle.py::TestExtraLocalesFallback`. Для каждой из 6 новых локалей (`pt`/`es`/`tr`/`id`/`fa`/`uk`) — 12 кейсов (2 × 6): сценарий 1 «ключ есть и в EN, и в локали» → выбирается локаль; сценарий 2 «ключ есть только в EN» → фолбэк возвращает EN-текст. Изоляция через `tmp_path`. 20 fluent-bundle-tests passed.
* [x] **K.6** (этот коммит) — Doc-sync: `docs/history.md` дополнен записью «2026-05-13 — Спринт 4.1-K «i18n: расширение каталога локалей (PT, ES, TR, ID, FA, UK)»» (формат как 4.1-J: заголовок, ПД-связь, чек-лист K.0–K.7, результат/артефакты, заметки/решения). `docs/current_tasks.md`: чек-лист K.0–K.6 → `[x]`.
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
- `a7dc59d` — `feat(4.1-K): K.1 — expand SUPPORTED_LOCALES to 8 (+pt/es/tr/id/fa/uk)`
- `465dd52` — `feat(4.1-K): K.2 — Alembic 0039 extends users.locale_override CHECK to 8 locales`
- `dd7fa5e` — `feat(4.1-K): K.3 — 6 new .ftl bootstrap files (pt/es/tr/id/fa/uk)`
- `809e11f` — `feat(4.1-K): K.4 — LangPresenter handles 8 locales, lang-set-* keys in en.ftl/ru.ftl`
- `726fe4d` — `test(4.1-K): K.5 — parametrized fallback tests for FluentMessageBundle (6 extra locales)`
- (этот коммит K.6) `docs(4.1-K): K.6 — doc-sync history.md + current_tasks.md`
