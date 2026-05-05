# Локализация бота «Пипирик Варс» — RU.
#
# Спринт 1.5.A / ПД 1.5.1: «Все сообщения вытащены из кода».
# Это файл-фундамент: содержит только ключи, которые уже подключены
# к презентерам через `IMessageBundle`. Дальнейшие спринты (1.5.B+)
# добавят остальные ключи и удалят hardcoded-строки из bot/presenters/.
#
# Соглашения:
# - Ключи группируем «модулями»: `start_*`, `profile_*`, `forest_*`...
# - Параметры — Fluent-плейсхолдеры `{ $name }` (BCP-47 / Mozilla Fluent).
# - HTML-теги в значениях допустимы (бот шлёт с parse_mode=HTML), но
#   избегаем их кроме `<b>`/`<i>` — это упрощает миграцию на другие
#   parse-mode при необходимости.

## /start (Спринт 1.1.C → 1.1.D → 1.2.4 DAU Gate)

start-registered = 🍆 Готово! Ты зарегистрирован в Пипирик Варс.

    Стартовая длина — 2 см, толщина — 1 уровень. Имя и титул появятся позже — в первом походе в лес.

start-already = 🍆 Ты уже зарегистрирован. Воспользуйся /profile, чтобы посмотреть карточку.

start-group = 🍆 «Пипирик Варс» здесь!

    1. Сначала зарегистрируйся в личке бота: открой приватный чат и нажми /start.
    2. Потом добавь меня в группу как админа — это превратит чат в клан.

start-other = 🍆 «Пипирик Варс» здесь. Команда /start доступна в ЛС или в группе.

start-queued = 🍆 Серверы переполнены — мы посадили тебя в очередь.

    Твоя позиция: #{ $position }.
    Как только освободится место — мы тебя зарегистрируем и пришлём уведомление.

## /profile (Спринт 1.1.E → 1.5.C)

profile-group = 🍆 Команда /profile доступна только в личке бота. Открой приватный чат и повтори.

profile-other = 🍆 Команда /profile доступна только в личке бота.

profile-not-registered = 🍆 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате, и карточка появится.

# Локализованные имена титулов из `domain.player.value_objects.Title`.
# Ключи привязаны к value enum-а: `Title.NEWBIE = "newbie"` → `profile-title-newbie`.
profile-title-newbie = Новичок

# Карточка персонажа из ГДД §2.2. Параметры:
# - `$nick` — собранный «Титул Название Имя» (через презентер)
# - `$length_cm` — целое, см
# - `$thickness_level` — целое, уровень
profile-card =
    🏷 { $nick }

    📏 Длина: { $length_cm } см
    📐 Толщина: { $thickness_level }

    🎽 Экипировка: пока пусто

## /top (Спринт 1.4.C → 1.5.C)

top-header = 🏆 <b>Топ пипириков</b>

top-empty = 🏆 Пока в топе никого нет. Стань первым — нажми /start!

# Один ряд топа: «<rank>. Титул Название Имя — N см».
top-entry = { $rank }. { $nick } — { $length_cm } см

## /oracle (Спринт 1.4.B → 1.5.D)

oracle-group = 🔮 Команда /oracle доступна только в личке бота. Открой приватный чат и повтори.

oracle-other = 🔮 Команда /oracle доступна только в личке бота.

oracle-not-registered = 🔮 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате, и тогда предсказатель тебя услышит.

# Сообщение успеха (ГДД §11). Параметры:
# - `$prediction` — текст предсказания, уже с подставленным `{ user }`
# - `$bonus_cm` — целое, прибавка длины
# - `$new_length_cm` — целое, новая длина игрока
oracle-success =
    🔮 Предсказание дня:
    { $prediction }

    📏 +{ NUMBER($bonus_cm, useGrouping: 0) } см
    Теперь у тебя: { NUMBER($new_length_cm, useGrouping: 0) } см

# Сообщение «возвращайся завтра». Параметры:
# - `$hours` — целое, часов до сброса 00:00 МСК
# - `$minutes` — целое 0-59, минут (форматирование `%02d` делает презентер)
oracle-already-used =
    🔮 Сегодня ты уже был у предсказателя.
    Возвращайся через { NUMBER($hours, useGrouping: 0) }ч { $minutes }м (00:00 по Москве).

## /upgrade (Спринт 1.4.A → 1.5.D)

upgrade-group = 🍆 Команда /upgrade доступна только в личке бота. Открой приватный чат и повтори.

upgrade-other = 🍆 Команда /upgrade доступна только в личке бота.

upgrade-not-registered = 🍆 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда можно будет качаться.

# Карточка-предложение «Прокачать с N до N+1». Параметры:
# - `$current_thickness` — целое, текущий уровень
# - `$next_thickness` — целое, целевой уровень (current+1)
# - `$cost_cm` — целое, стоимость списания
# - `$current_length_cm` — целое, текущая длина игрока
# - `$remaining_cm` — целое, что останется после списания
# - `$min_after_spend_cm` — целое, нижний предел по правилу 20 см
upgrade-proposal =
    📐 Прокачка толщины
    Текущий уровень: { NUMBER($current_thickness, useGrouping: 0) }
    Целевой уровень: { NUMBER($next_thickness, useGrouping: 0) }
    Стоимость: { NUMBER($cost_cm, useGrouping: 0) } см
    У тебя: { NUMBER($current_length_cm, useGrouping: 0) } см
    Останется: { NUMBER($remaining_cm, useGrouping: 0) } см (минимум по правилу 20 см: { NUMBER($min_after_spend_cm, useGrouping: 0) })

# Сообщение успеха «Толщина прокачана». Параметры:
# - `$new_thickness`, `$cost_cm`, `$new_length_cm`.
upgrade-success =
    ✅ Толщина прокачана до { NUMBER($new_thickness, useGrouping: 0) }!
    📏 Списано: { NUMBER($cost_cm, useGrouping: 0) } см
    Осталось: { NUMBER($new_length_cm, useGrouping: 0) } см

# Карточка отказа «Недостаточно длины». Параметры:
# - `$next_thickness`, `$cost_cm`, `$current_length_cm`,
# - `$min_after_spend_cm`, `$deficit_cm`.
upgrade-insufficient =
    ❌ Недостаточно длины для прокачки до { NUMBER($next_thickness, useGrouping: 0) }.
    Стоимость: { NUMBER($cost_cm, useGrouping: 0) } см
    У тебя: { NUMBER($current_length_cm, useGrouping: 0) } см
    Минимальный остаток: { NUMBER($min_after_spend_cm, useGrouping: 0) } см
    Не хватает: { NUMBER($deficit_cm, useGrouping: 0) } см

upgrade-cancelled = Прокачка отменена.

upgrade-race = ⚠️ Стоимость прокачки изменилась — открой /upgrade ещё раз, чтобы увидеть актуальную.

# Подпись инлайн-кнопки «Подтвердить (X см)». Параметр `$cost_cm`.
upgrade-button-confirm = Подтвердить ({ NUMBER($cost_cm, useGrouping: 0) } см)

upgrade-button-cancel = Отменить

# Toast-ы для callback-ответов (Telegram-лимит ≤ 200 символов).
upgrade-toast-upgraded = Толщина прокачана.

upgrade-toast-cancelled = Прокачка отменена.

upgrade-toast-player-not-found = Сначала нажми /start.

upgrade-toast-insufficient = Недостаточно длины.

upgrade-toast-race = Стоимость изменилась.

# Сжатый «Недостаточно длины» для замены текста сообщения после
# callback-нажатия (без полной карточки — handler знает, что мог
# измениться thickness между показом и нажатием).
upgrade-insufficient-short =
    ❌ Недостаточно длины.
    Стоимость: { NUMBER($cost_cm, useGrouping: 0) } см
    У тебя: { NUMBER($current_length_cm, useGrouping: 0) } см
    Минимальный остаток: { NUMBER($min_after_spend_cm, useGrouping: 0) } см
    Не хватает: { NUMBER($deficit_cm, useGrouping: 0) } см

## /forest (Спринт 1.3.D → 1.5.E)

forest-group = 🍆 Команда /forest доступна только в личке бота. Открой приватный чат и повтори.

forest-other = 🍆 Команда /forest доступна только в личке бота.

forest-not-registered = 🍆 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда сможешь идти в лес.

forest-already-in = 🌲 Ты уже в лесу — дождись возвращения. Бот пришлёт сообщение, когда поход закончится.

# Сообщение-старт «ушёл в лес» (ГДД §8.2). Параметры:
# - `$nick` — собранный «Титул Название Имя» (через презентер)
# - `$cooldown_minutes` — целое, минут до возвращения
forest-started = 🌲 { $nick } ушёл в лес на { NUMBER($cooldown_minutes, useGrouping: 0) } минут...

# Fallback-сообщение, когда `GetProfile` не нашёл игрока сразу после
# `StartForestRun` — параметр `$cooldown_minutes`.
forest-started-fallback = 🌲 Ты ушёл в лес на { NUMBER($cooldown_minutes, useGrouping: 0) } минут...

# Сообщение «вернулся из леса» — заголовок и строка длины (ГДД §8.2).
# Параметры:
# - `$nick` — полный ник «Титул Название Имя» с пересчитанным DisplayName
# - `$length_delta_cm` — целое, +N см получено в лесу
# - `$length_before_cm` / `$length_after_cm` — целые, было/стало
forest-finished-header = 🌲 { $nick } вернулся из леса!
forest-finished-length =
    📏 Длина: +{ NUMBER($length_delta_cm, useGrouping: 0) } см (было { NUMBER($length_before_cm, useGrouping: 0) }, стало { NUMBER($length_after_cm, useGrouping: 0) })

# Подстановка `{delta}` в шаблон забавного лога (Спринт 1.5.G, ГДД §15).
# Параметр `$length_delta_cm` — целое; формат идентичен «+N см» в
# `forest-finished-length`. Отдельный ключ нужен, чтобы локализаторы
# могли поменять единицы / знак для будущих языков без правки темплейтов.
forest-flavour-delta = +{ NUMBER($length_delta_cm, useGrouping: 0) } см

# Получен титул «Новичок» (первое возвращение из леса, ГДД §8.2).
forest-finished-title-granted = 🎖 Получен титул: Новичок

# Параметр `$item_name` — display_name предмета,
# `$rarity` — локализованная редкость (см. forest-rarity-*).
forest-finished-item-found = 🎩 Нашёл: { $item_name } [{ $rarity }]

# Имя выдано автоматически (новичок без имени). Параметр `$name`.
forest-finished-name-granted = 🪪 Получено имя: { $name }

# Имя предложено заменить (у игрока уже есть имя). Параметр `$name`.
forest-finished-name-found = 🪪 Нашёл имя: { $name }

# Локализованные редкости (UI «Нашёл: <предмет> [<редкость>]»).
forest-rarity-common = обычный
forest-rarity-rare = редкий
forest-rarity-epic = эпический

# Подписи инлайн-кнопок под сообщением «вернулся из леса».
forest-button-equip = Надеть
forest-button-drop-item = Выбросить
forest-button-replace-name = Заменить
forest-button-drop-name = Выбросить

# Toast-ы для callback-ответов (Telegram-лимит ≤ 200 символов).
forest-toast-name-applied = Имя заменено.
forest-toast-name-already-applied = Имя уже было применено.
forest-toast-name-dropped = Имя выброшено.
forest-toast-item-dropped = Предмет выброшен.
forest-toast-item-equipped-placeholder = Экипировка появится позже — предмет пока в инвентаре.
forest-toast-foreign-button = Эта кнопка не для тебя.
forest-toast-run-not-found = Этот лес уже неактивен.
forest-toast-drop-mismatch = Кнопка устарела.
forest-toast-player-not-found = Сначала нажми /start.

# ----------------------------- /lang -----------------------------
# Команда `/lang ru|en` — выбор языка интерфейса (Спринт 1.5.F).

# Команда вызвана не в ЛС.
lang-group = Команда `/lang` доступна только в личке. Зайди в ЛС.

# Команда вызвана не от Telegram-пользователя (например, из канала).
lang-other = Команда `/lang` доступна только обычным пользователям.

# Игрок не зарегистрирован.
lang-not-registered = Сначала нажми /start, потом — /lang ru|en.

# Использование: показать справку, если аргументы не валидны.
lang-usage = Использование: /lang ru или /lang en.

# Поддерживаемые языки в строке (для подсказки в lang-usage).
lang-unsupported = Язык `{ $code }` не поддерживается. Доступно: ru, en.

# Локаль установлена. `$code` — новый код локали.
lang-set-ru = Язык интерфейса: русский. Все ответы и фоновые сообщения теперь на русском.
lang-set-en = Interface language switched to English. All replies and background messages will be in English.


# Anti-cheat hardcap (Спринт 1.6.D, ГДД §3.3).
# Игрок попытался сделать что-то, дающее длину, но он в soft-ban-е.
# `$banned-until` — ISO-строка момента истечения бана (UTC, tz-aware).
anticheat-soft-ban-active = Антибот-проверка активна до { $banned-until }. Прибавка длины временно заморожена.

# Часть запрошенной дельты подрезана дневным cap-ом.
# `$applied` — фактически применённые см; `$requested` — изначально запрошенные.
anticheat-cap-clamped-daily = Дневной лимит роста почти исчерпан. Применено { NUMBER($applied, useGrouping: 0) } см из { NUMBER($requested, useGrouping: 0) } см.

# Часть запрошенной дельты подрезана недельным cap-ом.
anticheat-cap-clamped-weekly = Недельный лимит роста почти исчерпан. Применено { NUMBER($applied, useGrouping: 0) } см из { NUMBER($requested, useGrouping: 0) } см.
