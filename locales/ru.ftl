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
