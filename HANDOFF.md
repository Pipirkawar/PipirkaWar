# HANDOFF — Sprint 1.6.E (`AnticheatGuard` for length spenders)

> Этот файл — рабочая тетрадь Devin-агента. Удалить ПОСЛЕ мержа PR-а 1.6.E.
> Обновляется по мере работы (после каждого крупного шага). Если ты видишь этот файл — значит токены кончились на середине, и тебе нужно подхватить работу.

## Что делаем

**Спринт 1.6.E** — `AnticheatGuard` для всех «спендалок» длины. Если `Player.anticheat_ban_until > now()` → ошибка «вы в режиме проверки», операция не проходит.

Подключаем к существующему `UpgradeThickness` (`/upgrade`). В будущем — `/duel`, караваны, рейды, но сейчас они ещё не реализованы.

## Источники истины

- `docs/current_tasks.md` Спринт 1.6.E (текущий статус задачи).
- `docs/development_plan.md` §4 / задача 1.6.5.
- `docs/pipirik_wars_plan.md` ГДД §3.3.5 (anti-cheat soft-ban: блокирует **получение** длины через `progression.add_length` в Спринте 1.6.D + блокирует **спендалки** длины — это и есть 1.6.E).

## Готовое из предыдущих спринтов

- `Player.anticheat_ban_until: datetime | None` (1.6.A) + `Player.is_anticheat_banned(now=...)` метод.
- `progression.add_length(...)` use-case с soft-ban-гейтом на **прибавке** (1.6.D). Сюда добавлять не надо — этот гейт уже есть в `AddLength`.

## План реализации

### 1. Domain
Создать `src/pipirik_wars/domain/anticheat/guard.py`:
```python
class AnticheatGuard:
    """Чистая функция-сервис: проверяет, не в soft-ban-е ли игрок."""
    @staticmethod
    def require_unlocked(player: Player, *, now: datetime) -> None:
        if player.is_anticheat_banned(now=now):
            assert player.anticheat_ban_until is not None
            raise AnticheatSoftBanError(
                tg_id=player.tg_id,
                banned_until=player.anticheat_ban_until,
            )
```

`AnticheatSoftBanError` уже есть в `domain/progression/errors.py` (1.6.D). Используем её.

Экспортируем из `domain/anticheat/__init__.py`.

### 2. Application — wire in `UpgradeThickness`
В `src/pipirik_wars/application/progression/upgrade.py` (или как там называется файл) — после load player, ДО transaction-mutate части — вызвать `AnticheatGuard.require_unlocked(player, now=clock.now())`. Обработать в presenter / handler как локализованную ошибку `anticheat-guard-blocked`.

Проверить: использует ли `UpgradeThickness` `IClock` уже? Если нет — пробросить через DI.

### 3. Локализация
Добавить в `locales/{ru,en}.ftl`:
- `anticheat-guard-blocked` — «вы в режиме проверки до {$banned-until}, прокачка временно заморожена» (RU + EN).

Подключить в `UpgradePresenter` (или там, где сейчас обрабатываются ошибки `/upgrade`).

### 4. Тесты (≥5 кейсов)
`tests/unit/domain/anticheat/test_guard.py`:
1. `require_unlocked` для игрока без бана → ничего.
2. С истёкшим баном → ничего.
3. С активным баном → `AnticheatSoftBanError` с полями `tg_id` / `banned_until`.
4. `now == banned_until` (граница) → `is_anticheat_banned` возвращает False (см. `Player.is_anticheat_banned` — там проверка `banned_until > now`).
5. Ошибка наивный datetime → должно прокинуться (валидация в `Player`).

`tests/unit/application/progression/test_upgrade.py` (или там, где тесты `UpgradeThickness`):
- Расширить: с активным soft-ban-ом → `AnticheatSoftBanError`, без mutate, без audit.

### 5. CI
`make ci` — coverage ≥80%, lint, types, import-linter.

### 6. PR
- `git_pr fetch_template`
- `git_pr create` со ссылкой на 1.6.D / 1.6.A / ГДД §3.3.5
- `pr_checks` wait_mode=all
- Удалить `HANDOFF.md` в этом же PR (или последним коммитом)

## Состояние работы

| Шаг | Статус |
|---|---|
| Pull main, create branch | ✅ done (`devin/1777987131-sprint-1-6e-anticheat-guard`) |
| HANDOFF scaffold + commit | 🟡 в процессе |
| Прочитать UpgradeThickness | ⚪ |
| Domain `AnticheatGuard` | ⚪ |
| Wire в `UpgradeThickness` | ⚪ |
| Локали `anticheat-guard-blocked` | ⚪ |
| Тесты ≥5 кейсов | ⚪ |
| `make ci` | ⚪ |
| PR | ⚪ |
| Удалить HANDOFF.md | ⚪ |

## Важно

- **Не коммить** в финальный PR этот HANDOFF.md — удалить последним коммитом перед PR (или в первом коммите PR-а).
- Все коммиты в WIP-стадии — с префиксом `[WIP 1.6.E]`.
- Финальный коммит — с обычным сообщением `Sprint 1.6.E: AnticheatGuard for length spenders`.
- НИЧЕГО не менять в `progression.add_length` use-case — он закрыт PR #37.

## Если CI красный
- `mypy` ошибки → проверить, что `AnticheatGuard.require_unlocked` принимает `Player` и `datetime` явно (не `Any`).
- `import-linter` ошибки → новый сервис должен лежать в `domain`, не импортировать `application`/`infrastructure`.
- `ruff RUF023` → __slots__ должны быть отсортированы.
- `ruff PLC0415` → импорты на верхнем уровне.

## Контакт

Сессия: https://app.devin.ai/sessions/dc1c43fa0a1c45dbab2c142a8c657693
