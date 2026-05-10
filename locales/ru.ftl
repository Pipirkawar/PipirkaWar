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

# Реферальный приход (Спринт 2.4.D, ГДД §13.1).
# Параметры:
# - `$bonus_cm` — сколько см получил новичок сверх стартовой длины
#   (`balance.referral.on_signup.newbie_bonus_cm`, дефолт 5).
start-registered-with-referral = 🍆 Готово! Ты зарегистрирован в Пипирик Варс.

    Стартовая длина — 2 см + <b>бонус { $bonus_cm } см за приход по реферальной ссылке</b>. Толщина — 1 уровень. Имя и титул появятся позже — в первом походе в лес.

## /profile (Спринт 1.1.E → 1.5.C)

profile-group = 🍆 Команда /profile доступна только в личке бота. Открой приватный чат и повтори.

profile-other = 🍆 Команда /profile доступна только в личке бота.

profile-not-registered = 🍆 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате, и карточка появится.

# Локализованные имена титулов из `domain.player.value_objects.Title`.
# Ключи привязаны к value enum-а: `Title.NEWBIE = "newbie"` → `profile-title-newbie`.
profile-title-newbie = Новичок
profile-title-ataman = Атаман разбойников

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

## /clantop (Спринт 2.2.A)

clantop-header = 🛡 <b>Топ кланов</b>

clantop-empty = 🛡 Кланов в топе пока нет. Добавь бота в группу — и зарегистрируй клан!

# Один ряд топа: «<rank>. Название клана — N см (M 👥)».
clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } см ({ $member_count } 👥)

## /oracle (Спринт 1.4.B → 1.5.D, расширен в 3.6-B; ГДД §11, §11.1)

oracle-group = 🔮 Команда /oracle доступна только в личке бота. Открой приватный чат и повтори.

oracle-other = 🔮 Команда /oracle доступна только в личке бота.

oracle-not-registered = 🔮 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате, и тогда предсказатель тебя услышит.

# Шапка успеха: предсказание дня + текст шаблона. Параметры:
# - `$prediction` — текст предсказания, уже с подставленным `{ user }`
oracle-success-prediction =
    🔮 Предсказание дня:
    { $prediction }

# Базовая прибавка длины (всегда, ГДД §11). Параметры:
# - `$base_cm` — целое, базовый бросок 1..20 см
oracle-base-line = 📏 +{ NUMBER($base_cm, useGrouping: 0) } см — базовая

# Бонус-за-племена (только при `n_active_tribes > 0`, Спринт 3.6-B / ГДД §11.1).
# Параметры:
# - `$tribe_bonus_cm` — целое, прибавка за племена
# - `$n_active_tribes` — целое, число активных племён игрока
# Плюрал по `$n_active_tribes` (CLDR RU): 1 → племя, 2..4 → племени, 5+ → племён.
oracle-tribe-bonus-line = 🛡 +{ NUMBER($tribe_bonus_cm, useGrouping: 0) } см — за племена ({ NUMBER($n_active_tribes, useGrouping: 0) } { $n_active_tribes ->
        [one] племя
        [few] племени
       *[other] племён
    })

# Итоговая прибавка длины за вызов (только при `n_active_tribes > 0`).
# Параметры: `$total_cm` — целое, `base_cm + tribe_bonus_cm`.
oracle-total-line = ✨ Итого: +{ NUMBER($total_cm, useGrouping: 0) } см

# Новая длина игрока после применения прибавки/клампа (всегда).
# Параметры: `$new_length_cm` — целое.
oracle-new-length-line = Теперь у тебя: { NUMBER($new_length_cm, useGrouping: 0) } см

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

# Anti-cheat soft-ban-гейт на /upgrade (Спринт 1.6.E, ГДД §3.3.5).
# `$banned-until` — ISO-строка момента истечения бана (UTC, tz-aware).
upgrade-anticheat-blocked = Прокачка временно заморожена. Антибот-проверка активна до { $banned-until }.

upgrade-toast-anticheat-blocked = Антибот-проверка активна.

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


# /anticheat_unban (Спринт 1.6.G, ГДД §3.3) — admin-команда.
# Использование: показываем, когда формат команды некорректен.
anticheat-unban-usage = ⚠️ Использование: `/anticheat_unban <tg_id> <причина>`. Причина обязательна.

# Не из-под админа (или роль ниже super_admin).
anticheat-unban-not-authorized = ❌ У тебя нет прав на эту команду. Снятие anti-cheat-бана доступно только активным super_admin.

# Игрок с таким `tg_id` не зарегистрирован.
anticheat-unban-player-not-found = ❌ Игрок с tg_id { $tg_id } не зарегистрирован.

# Бан не активен (None или уже истёк) — идемпотентный no-op.
anticheat-unban-not-banned = ℹ️ У игрока tg_id { $tg_id } нет активного anti-cheat-бана. Действие не требуется.

# Бан успешно снят. `$banned-until-before` — ISO-строка прежнего срока бана.
anticheat-unban-success = ✅ Anti-cheat-бан снят (tg_id { $tg_id }, бан до { $banned-until-before }). Причина: { $reason }.


# ──────────────────────────────────────────────────────────────────────────
# PvP-дуэль 1×1 (Спринт 2.1.E, ГДД §7.1).
# ──────────────────────────────────────────────────────────────────────────

# /duel в ЛС без reply — вызов автоматически уходит в глобальное лобби.
# Это сообщение остаётся как fallback и для совместимости с тестами; флоу
# сейчас вызывает duel-global-enqueued после успешного enqueue.
duel-private-needs-global = 🍆 Чтобы вызвать кого-то на дуэль, ответь /duel на сообщение оппонента в общем чате. Или подожди — твой `/duel` в ЛС уже отправлен в глобальное лобби.

# /duel без reply в группе или некорректные аргументы.
duel-usage = 🍆 Использование: ответь `/duel` на сообщение оппонента. По умолчанию — режим «Чат → Глобал». Для «Только чат» — `/duel chat`. В ЛС `/duel` без аргументов отправит вызов в глобальное лобби.

# Игрок (челленджер) ещё не зарегистрирован.
duel-not-registered = 🍆 Похоже, ты ещё не зарегистрирован. Нажми /start.

# Оппонент не зарегистрирован в боте.
duel-target-not-registered = 🍆 Соперник ещё не зарегистрирован в боте — попроси его нажать /start в ЛС.

# Reply на сообщение бота — нельзя.
duel-target-is-bot = 🍆 На дуэль можно вызвать только живого пипирика, не бота.

# Reply на собственное сообщение — нельзя.
duel-self-challenge = 🍆 Сам с собой? Найди реального оппонента.

# Карточка вызова в чате (chat_only mode). $challenger / $challenged — @username.
duel-challenge-chat = ⚔️ { $challenger } вызывает { $challenged } на дуэль (только в этом чате)! Принять?

# Карточка вызова в чате (chat_then_global mode).
duel-challenge-chat-then-global = ⚔️ { $challenger } вызывает { $challenged } на дуэль! Если оппонент не примет за 3 минуты — вызов уплывёт в глобальное лобби.

# Уведомление об отправке вызова в глобальное лобби (global_only mode).
duel-challenge-global = ⚔️ { $challenger }, твой вызов отправлен в глобальное лобби — ждём оппонента до { NUMBER($ttl_minutes, useGrouping: 0) } мин.

# Уведомление в ЛС после `/duel` без аргументов: попал в глобальное лобби.
duel-global-enqueued = ⚔️ Вызов отправлен в глобальное лобби. Ждём, пока кто-нибудь нажмёт /duel_global. Истечёт через { NUMBER($ttl_minutes, useGrouping: 0) } мин — отмени вручную через /cancel_duel { $duel_id }.

# Ответ в ЛС после `/duel_global` — успешный матч.
duel-global-matched = ⚔️ Сматчился с { $challenger }! Бой начался — следи за раунд-промптами в ЛС.

# Ответ в ЛС после `/duel_global` — лобби пусто (или race-condition с собственным вызовом).
duel-global-empty = 🪂 Глобальное лобби пусто. Попробуй позже или брось вызов через /duel.

# `/duel_global` вне ЛС бота — нельзя.
duel-global-only-in-private = 🤖 `/duel_global` работает только в ЛС бота, чтобы оппоненты не светились в чате.

# Текст после accept-а — заменяет challenge-карточку в общем чате.
duel-chat-accepted = ✅ { $challenged } принял вызов { $challenger }. Бой идёт в ЛС бота.

# Inline-кнопки.
duel-button-accept = Принять
duel-button-reject = Отклонить
duel-button-attack-high = Атака: ⬆ верх
duel-button-attack-mid = Атака: ➡ центр
duel-button-attack-low = Атака: ⬇ низ
duel-button-block-high = Блок: ⬆ верх
duel-button-block-mid = Блок: ➡ центр
duel-button-block-low = Блок: ⬇ низ

# Раунд-промпт (DM).
duel-round-attack-prompt = 🥊 Раунд { NUMBER($round_num, useGrouping: 0) } из 3. Куда бьёшь?

# Промпт выбора блока (после атаки).
duel-round-block-prompt = 🛡 Раунд { NUMBER($round_num, useGrouping: 0) } из 3. Атака: { $attack }. Что блокируешь?

# Игрок сделал ход — ждём оппонента.
duel-round-waiting = ⏳ Раунд { NUMBER($round_num, useGrouping: 0) } — твой ход принят. Ждём оппонента…

# Финал боя.
duel-result-victory = 🏆 Победа! +{ NUMBER($delta_cm, useGrouping: 0) } см. Длина теперь { NUMBER($new_length_cm, useGrouping: 0) } см.
duel-result-defeat = 💀 Поражение. { NUMBER($delta_cm, useGrouping: 0) } см. Длина теперь { NUMBER($new_length_cm, useGrouping: 0) } см.
duel-result-draw = 🤝 Ничья. Длина не изменилась — { NUMBER($length_cm, useGrouping: 0) } см.

# Карточка результата дуэли (Спринт 2.1.H, ГДД §15) — публичный
# вариант для расшаривания в чат. `$winner` / `$loser` — отформатированные
# `@username` / «—». В draw-варианте — `$p1` / `$p2` (без победителя).
duel-result-card-victory = ⚔️ Дуэль завершена: { $winner } разорвал { $loser } (+{ NUMBER($delta_cm, useGrouping: 0) } см).
duel-result-card-draw = ⚔️ Дуэль завершена ничьей: { $p1 } и { $p2 } обменялись ударами по нулям.
duel-share-button = 📢 Поделиться

# /cancel_duel.
duel-cancelled = ❌ Вызов отменён челленджером { $challenger }.
duel-cancel-usage = Использование: `/cancel_duel <duel_id>`. ID можно найти в карточке вызова.

# Toast-уведомления (ответы на callback_query).
duel-toast-accepted = Вызов принят!
duel-toast-rejected = Спасибо, не интересно.
duel-toast-cancelled = Вызов отменён.
duel-toast-not-found = Эта дуэль уже неактивна.
duel-toast-not-participant = Эта дуэль не для тебя.
duel-toast-foreign-button = Эта кнопка не для тебя.
duel-toast-invalid-state = Дуэль уже не в той фазе.
duel-toast-already-submitted = Ты уже сделал ход в этом раунде.
duel-toast-outdated = Кнопка устарела.

# Ошибки порога входа в дуэль.
duel-requirements-not-met = 📏 Для дуэлей нужны длина ≥ { NUMBER($min_length_cm, useGrouping: 0) } см и толщина ≥ { NUMBER($min_thickness_level, useGrouping: 0) }.

# Anti-cheat soft-ban активен.
duel-anticheat-blocked = Антибот-проверка активна до { $banned-until }. Дуэли временно заморожены.

# Игрок занят другой активностью (forest и т. п.).
duel-lock-already-held = 🔒 Сейчас занят (например, в /forest). Сначала закончи активность.

# === Масс-PvP клан×клан (Спринт 2.2.F, ГДД §7.2) ===

# /clan_attack — usage и базовые ошибки.
pvp-mass-needs-group-chat = ⚔️Команда `/clan_attack` работает только в групповом чате клана. Запусти её из чата клана-противника, который хочешь атаковать.
pvp-mass-not-registered = 🍆Сначала зарегистрируйся через `/start` в ЛС бота.
pvp-mass-attacker-not-found = ❌Этот чат не привязан к зарегистрированному клану.
pvp-mass-attacker-not-member = 🚫Атаковать другие кланы могут только участники клана этого чата.
pvp-mass-target-not-found = ❌Целевой чат не найден или не привязан к зарегистрированному клану.
pvp-mass-target-needed = Использование: `/clan_attack <chat_id>` или ответом на сообщение из чата защищающегося клана.
pvp-mass-self-attack = 🤝Нельзя атаковать собственный клан.
pvp-mass-clan-frozen = 🧊Один из кланов заморожен — массовый бой невозможен.
pvp-mass-cooldown = ⏳Кулдаун ещё не истёк: повторная атака возможна через { NUMBER($cooldown_hours, useGrouping: 0) } ч.
pvp-mass-no-participants = 🪶У одной из сторон нет участников, удовлетворяющих требованиям (длина ≥ { NUMBER($min_length_cm, useGrouping: 0) } см, толщина ≥ { NUMBER($min_thickness_level, useGrouping: 0) }).
pvp-mass-lock-already-held = 🔒Кто-то из участников занят другой активностью. Попробуй ещё раз через минуту.

# Карточка старта в групповом чате.
pvp-mass-started = ⚔️Битва кланов: <b>{ $attacker }</b> × <b>{ $defender }</b>! Состав: { NUMBER($attacker_size, useGrouping: 0) } × { NUMBER($defender_size, useGrouping: 0) }. Все участники получили инструкции в ЛС. Время на ход — { NUMBER($timer_seconds, useGrouping: 0) } сек.

# DM-промпты.
pvp-mass-prompt-attack = ⚔️Битва клан × клан. Куда бьёшь?
pvp-mass-prompt-block = 🛡Атака выбрана: { $attack }. Что блокируешь?
pvp-mass-waiting = ⏳Твой ход принят. Ждём остальных…

# Финальный итог в ЛС каждому участнику.
pvp-mass-result-victory = 🏆Победа! Клан <b>{ $clan }</b> выиграл и забрал { NUMBER($total_dealt, useGrouping: 0) } см. Твоя дельта: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } см.
pvp-mass-result-defeat = 💀Поражение. Клан <b>{ $clan }</b> проиграл, { NUMBER($total_lost, useGrouping: 0) } см ушло противнику. Твоя дельта: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } см.
pvp-mass-result-draw = 🤝Ничья. Никто не выиграл больше. Твоя дельта: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } см.

# Финальная карточка в чат.
pvp-mass-result-chat-victory = 🏆Битва клан × клан окончена! Победил клан <b>{ $clan }</b>, забрал { NUMBER($total_dealt, useGrouping: 0) } см.
pvp-mass-result-chat-draw = 🤝Битва клан × клан окончена ничьёй ({ NUMBER($total_dealt, useGrouping: 0) } см с обеих сторон).

# Кнопки.
pvp-mass-button-attack-high = ⬆️ Голова
pvp-mass-button-attack-mid = ↔ Корпус
pvp-mass-button-attack-low = ⬇️ Ноги
pvp-mass-button-block-high = 🛡⬆ Голова
pvp-mass-button-block-mid = 🛡↔ Корпус
pvp-mass-button-block-low = 🛡⬇ Ноги

# Toast-уведомления.
pvp-mass-toast-not-found = Этот бой уже неактивен.
pvp-mass-toast-not-participant = Ты не участник этого боя.
pvp-mass-toast-foreign-button = Эта кнопка не для тебя.
pvp-mass-toast-invalid-state = Бой уже завершён.
pvp-mass-toast-already-submitted = Ты уже сделал ход.
pvp-mass-toast-outdated = Кнопка устарела.
pvp-mass-toast-attack-selected = Атака выбрана. Теперь выбери блок.
pvp-mass-toast-move-accepted = Ход принят!

## /clan_history (Спринт 2.2.G — журнал клановых атак)

clan-history-needs-group-chat = 📜 Команда `/clan_history` работает только в групповом чате клана.
clan-history-not-registered = 📜 Этот чат не привязан к зарегистрированному клану. Используй /start для регистрации.
clan-history-header = 📜 <b>Журнал клановых атак</b> ({ $clan_title })
clan-history-empty = 📜 У клана <b>{ $clan_title }</b> пока нет завершённых массовых боёв.
# Один ряд журнала: «<idx>. ⚔ Противник — победа +20 см (3×3)».
clan-history-entry-victory = { $idx }. ⚔ { $opponent_clan_title } — 🏆 победа +{ NUMBER($our_delta_cm, useGrouping: 0) } см ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-defeat = { $idx }. ⚔ { $opponent_clan_title } — 💀 поражение { NUMBER($our_delta_cm, useGrouping: 0) } см ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-draw = { $idx }. ⚔ { $opponent_clan_title } — 🤝 ничья ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-cancelled = { $idx }. ⚔ { $opponent_clan_title } — ⛔ отменён ({ $when })

## /clan_head (Спринт 2.3.E — глава клана дня)

clan-head-needs-group-chat = 👑 Команда `/clan_head` работает только в групповом чате клана.
clan-head-not-registered = 👑 Этот чат не привязан к зарегистрированному клану. Используй /start для регистрации.
clan-head-frozen-clan = 👑 Клан временно заморожен. Назначить главу нельзя.
clan-head-not-enough-active = 👑 В клане слишком мало активных за последние 7 дней (нужно как минимум { NUMBER($required, useGrouping: 0) }, активны: { NUMBER($active_count, useGrouping: 0) }).
clan-head-success = 👑 <b>Глава клана дня</b> — { $head_display_name }!
  +{ NUMBER($bonus_cm, useGrouping: 0) } см к длине (теперь { NUMBER($new_length_cm, useGrouping: 0) } см).

  💬 <i>{ $quote_text }</i>
clan-head-already-assigned = 👑 На сегодня глава уже назначен — { $head_display_name } (+{ NUMBER($bonus_cm, useGrouping: 0) } см).

  💬 <i>{ $quote_text }</i>

## Referral-share кнопка (Спринт 2.4.D-b, ГДД §13.2)
# Кнопка подписи под результатом дуэли / похода — шарит результат с реферальной ссылкой.
referral-share-button = 🔗 Поделиться

# Текст, постящийся в чат при нажатии кнопки «Поделиться» после дуэли (победа).
# Параметры: $winner, $loser, $delta_cm, $winner_length_cm, $deeplink.
referral-share-duel-victory = ⚔️ ПИПИРИК ВАРС — Результат боя!
    { $winner } 🏆 победил!
    Украл { NUMBER($delta_cm, useGrouping: 0) } см у { $loser }!
    📏 Новая длина: { NUMBER($winner_length_cm, useGrouping: 0) } см

    🎮 Играй тоже → { $deeplink }

# Текст для ничьей.
# Параметры: $p1, $p2, $deeplink.
referral-share-duel-draw = ⚔️ ПИПИРИК ВАРС — Результат боя!
    Ничья: { $p1 } и { $p2 } разошлись с миром.

    🎮 Играй тоже → { $deeplink }

# Текст, постящийся в чат при нажатии кнопки «Поделиться» после похода.
# Параметры: $player, $delta_cm, $length_cm, $deeplink.
referral-share-forest = 🌲 ПИПИРИК ВАРС — Поход в лес!
    { $player } вернулся из леса с { NUMBER($delta_cm, useGrouping: 0) } см!
    📏 Новая длина: { NUMBER($length_cm, useGrouping: 0) } см

    🎮 Играй тоже → { $deeplink }


## Еженедельная сводка рефералов клана (Спринт 2.4.E, ГДД §13.3)
# Карточка отправляется ботом в чат клана воскресными вечером (cron 18:00 UTC).
# Параметры заголовка: $clan_title.
weekly-referral-summary-title = 📊 ИТОГИ НЕДЕЛИ — Клан "{ $clan_title }"
# Параметры: $total — суммарное число новых рефералов клана за неделю.
weekly-referral-summary-total = 👥 Новых рефералов за неделю: { NUMBER($total, useGrouping: 0) }
# Параметры: $rank (1..3), $referrer_display_name, $count.
weekly-referral-summary-line = 🏆 { NUMBER($rank, useGrouping: 0) }. { $referrer_display_name } — пригласил { NUMBER($count, useGrouping: 0) }
weekly-referral-summary-footer = Зови друзей — все растут вместе!


## Admin — команды поддержки (Спринт 2.5-B, ГДД §18.6.5)
# Используются `/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban` и общим
# `/confirm`-handler-ом. Тексты намеренно компактные — админ-чаты обычно
# заполнены одной командой за другой, длинные простыни шумят.

# /find_player <text>
admin-find-player-usage = ⚠️ Использование: <code>/find_player &lt;tg_id | @username | подстрока&gt;</code>. Запрос обязателен.
admin-find-player-not-authorized = ❌ Только активные админы могут пользоваться поиском игроков.
admin-find-player-empty = 🔍 По запросу <code>{ $query }</code> игроки не найдены.
# Заголовок выдачи (count — сколько строк ниже).
admin-find-player-header = 🔍 Найдено игроков: { $count } (по запросу <code>{ $query }</code>).
# Одна строка списка. Параметры: $tg_id, $username (или "—"), $name (или "—"),
#  $title (или "—"), $length_cm, $thickness_level, $status (текстовая метка).
admin-find-player-row = • <code>{ $tg_id }</code> · @{ $username } · «{ $name }» · { $title } · L{ $length_cm }/T{ $thickness_level } · { $status }

# /player <tg_id>
admin-player-usage = ⚠️ Использование: <code>/player &lt;tg_id&gt;</code>. Параметр обязателен.
admin-player-not-authorized = ❌ Только активные админы могут смотреть карточки игроков.
admin-player-bad-id = ⚠️ <code>{ $value }</code> не похож на tg_id (целое число). Попробуй ещё раз.
admin-player-not-found = 🔍 Игрок с tg_id <code>{ $tg_id }</code> не найден.
admin-player-card-summary = • <code>{ $tg_id }</code> · @{ $username } · «{ $name }» · { $title } · L{ $length_cm }/T{ $thickness_level } · { $status }
admin-player-card-clan = 🏰 Клан: <code>{ $title }</code> ({ $clan_status }) · роль { $role } · с { $joined_at }
admin-player-card-no-clan = 🏰 Клан: —
admin-player-card-forest-active = 🌲 Активный поход в лес #{ $run_id }: с { $started_at }, до { $ends_at }.
admin-player-card-no-forest = 🌲 Активного похода нет.
admin-player-card-anticheat = 🛡️ Anti-cheat-бан до: { $until }.
admin-player-card-no-anticheat = 🛡️ Anti-cheat-бан: не активен.

# /freeze
admin-freeze-usage = ⚠️ Использование: <code>/freeze &lt;tg_id&gt; [причина]</code>.
admin-freeze-not-authorized = ❌ Только активные админы могут замораживать игроков.
admin-freeze-bad-id = ⚠️ <code>{ $value }</code> не похож на tg_id (целое число).
admin-freeze-not-found = 🔍 Игрок с tg_id <code>{ $tg_id }</code> не найден.
admin-freeze-already = ❄️ Игрок <code>{ $tg_id }</code> уже заморожен.
admin-freeze-ok = 🥶 Игрок <code>{ $tg_id }</code> заморожен.{ $reason_suffix }
admin-freeze-reason-suffix = Причина: { $reason }.

# /unfreeze
admin-unfreeze-usage = ⚠️ Использование: <code>/unfreeze &lt;tg_id&gt; [причина]</code>.
admin-unfreeze-not-authorized = ❌ Только активные админы могут размораживать игроков.
admin-unfreeze-bad-id = ⚠️ <code>{ $value }</code> не похож на tg_id (целое число).
admin-unfreeze-not-found = 🔍 Игрок с tg_id <code>{ $tg_id }</code> не найден.
admin-unfreeze-already = ▶️ Игрок <code>{ $tg_id }</code> и так активен.
admin-unfreeze-ok = ☀️ Игрок <code>{ $tg_id }</code> разморожен.{ $reason_suffix }
admin-unfreeze-reason-suffix = Причина: { $reason }.

# /ban — necessitates TOTP (B.4)
admin-ban-usage = ⚠️ Использование: <code>/ban &lt;tg_id&gt; &lt;причина&gt;</code>. Причина обязательна.
admin-ban-not-authorized = ❌ Только активные админы могут банить игроков.
admin-ban-totp-not-configured = ❌ У тебя не настроен TOTP. Команда `/ban` без него недоступна.
admin-ban-bad-id = ⚠️ <code>{ $value }</code> не похож на tg_id (целое число).
admin-ban-no-reason = ⚠️ Причина обязательна. Использование: <code>/ban &lt;tg_id&gt; &lt;причина&gt;</code>.
admin-ban-not-found = 🔍 Игрок с tg_id <code>{ $tg_id }</code> не найден.
admin-ban-already = 🛑 Игрок <code>{ $tg_id }</code> уже забанен.
admin-ban-confirm-issued = 🛡️ Подтверди операцию. Отправь: <code>/confirm { $token } &lt;6-значный код&gt;</code>. Токен живёт { $ttl_seconds } секунд.

# /confirm (B.5)
admin-confirm-usage = ⚠️ Использование: <code>/confirm &lt;token&gt; &lt;6-значный код&gt;</code>.
admin-confirm-not-authorized = ❌ Только активные админы могут подтверждать операции.
admin-confirm-totp-not-configured = ❌ У тебя не настроен TOTP. Подтверждение невозможно.
admin-confirm-token-not-found = ❌ Токен <code>{ $token }</code> уже использован или не существует.
admin-confirm-token-expired = ⌛ Токен истёк. Заведи команду заново.
admin-confirm-admin-mismatch = ❌ Этот токен принадлежит другому админу.
admin-confirm-code-invalid = ❌ Неверный 6-значный код.
admin-confirm-success-ban = ✅ Игрок <code>{ $tg_id }</code> забанен.
admin-confirm-success-ban-already = 🛑 Игрок <code>{ $tg_id }</code> уже был забанен.
admin-confirm-unknown-command-kind = ⚠️ Неизвестный тип команды <code>{ $command_kind }</code> — обновите бота.

# ─────────────────────────────────────────────────────────────────────────────
# Спринт 2.5-C — команды экономики (TOTP-обязательные кроме /balance_get)
# ─────────────────────────────────────────────────────────────────────────────

# /grant_length <tg_id> <±delta_cm> <reason>
admin-grant-length-usage = ⚠️ Использование: <code>/grant_length &lt;tg_id&gt; &lt;±delta_cm&gt; &lt;причина&gt;</code>. Все три параметра обязательны.
admin-grant-length-not-authorized = ❌ Только активные админы могут менять длину.
admin-grant-length-totp-not-configured = ❌ У тебя не настроен TOTP. `/grant_length` без него недоступен.
admin-grant-length-bad-id = ⚠️ <code>{ $value }</code> не похож на tg_id (целое число).
admin-grant-length-bad-delta = ⚠️ <code>{ $value }</code> не похож на ±целое и ≠ 0.
admin-grant-length-no-reason = ⚠️ Причина обязательна. Использование: <code>/grant_length &lt;tg_id&gt; &lt;±delta_cm&gt; &lt;причина&gt;</code>.
admin-grant-length-not-found = 🔍 Игрок с tg_id <code>{ $tg_id }</code> не найден.
admin-grant-length-blocked = 🚫 Невозможно править длину игрока <code>{ $tg_id }</code>: { $reason }.
admin-grant-length-confirm-issued = 🛡️ Подтверди операцию. Отправь: <code>/confirm { $token } &lt;6-значный код&gt;</code>. Токен живёт { $ttl_seconds } секунд.
admin-grant-length-success = ✅ Игроку <code>{ $tg_id }</code> применено { $delta } см. Новая длина: { $new_length_cm } см.
admin-grant-length-success-clamped = ⚠️ Игроку <code>{ $tg_id }</code> запрошено { $requested } см, по 24-h окну применено { $applied } см. Новая длина: { $new_length_cm } см.
admin-grant-length-soft-ban = 🚫 Игрок <code>{ $tg_id }</code> в anti-cheat soft-ban — операция отклонена.

# /grant_thickness <tg_id> <new_level> <reason>
admin-grant-thickness-usage = ⚠️ Использование: <code>/grant_thickness &lt;tg_id&gt; &lt;new_level&gt; &lt;причина&gt;</code>.
admin-grant-thickness-not-authorized = ❌ Только активные админы могут менять толщину.
admin-grant-thickness-totp-not-configured = ❌ У тебя не настроен TOTP. `/grant_thickness` без него недоступен.
admin-grant-thickness-bad-id = ⚠️ <code>{ $value }</code> не похож на tg_id (целое число).
admin-grant-thickness-bad-level = ⚠️ <code>{ $value }</code> не похож на уровень (целое ≥ 1).
admin-grant-thickness-no-reason = ⚠️ Причина обязательна. Использование: <code>/grant_thickness &lt;tg_id&gt; &lt;new_level&gt; &lt;причина&gt;</code>.
admin-grant-thickness-not-found = 🔍 Игрок с tg_id <code>{ $tg_id }</code> не найден.
admin-grant-thickness-blocked = 🚫 Невозможно править толщину игрока <code>{ $tg_id }</code>: { $reason }.
admin-grant-thickness-level-invalid = ⚠️ Уровень <code>{ $level }</code> вне диапазона [1, { $max_level }] ({ $reason_code }).
admin-grant-thickness-confirm-issued = 🛡️ Подтверди операцию. Отправь: <code>/confirm { $token } &lt;6-значный код&gt;</code>. Токен живёт { $ttl_seconds } секунд.
admin-grant-thickness-success = ✅ Игроку <code>{ $tg_id }</code> установлен уровень толщины { $new_level } (был { $previous_level }).
admin-grant-thickness-already-at-level = ℹ️ Игрок <code>{ $tg_id }</code> уже на уровне толщины { $level }.

# /balance_get <key>
admin-balance-get-usage = ⚠️ Использование: <code>/balance_get &lt;dotted.key&gt;</code>.
admin-balance-get-not-authorized = ❌ Только активные админы могут читать баланс.
admin-balance-get-key-not-found = ⚠️ Ключ <code>{ $path }</code> не найден ({ $reason } на сегменте <code>{ $segment }</code>).
admin-balance-get-result = 📦 <code>{ $path }</code> = <code>{ $value }</code> (balance v{ $version }).

# /balance_set <key> <value> <reason>
admin-balance-set-usage = ⚠️ Использование: <code>/balance_set &lt;dotted.key&gt; &lt;json_value&gt; &lt;причина&gt;</code>.
admin-balance-set-not-authorized = ❌ Только активные админы могут менять баланс.
admin-balance-set-totp-not-configured = ❌ У тебя не настроен TOTP. `/balance_set` без него недоступен.
admin-balance-set-no-reason = ⚠️ Причина обязательна.
admin-balance-set-bad-value = ⚠️ <code>{ $value }</code> не парсится как JSON-фрагмент.
admin-balance-set-key-not-found = ⚠️ Ключ <code>{ $path }</code> не найден ({ $reason } на сегменте <code>{ $segment }</code>).
admin-balance-set-validation-error = ❌ Значение для <code>{ $path }</code> не прошло валидацию: { $error }.
admin-balance-set-confirm-issued = 🛡️ Подтверди операцию. Отправь: <code>/confirm { $token } &lt;6-значный код&gt;</code>. Токен живёт { $ttl_seconds } секунд.
admin-balance-set-success = ✅ Ключ <code>{ $path }</code>: <code>{ $previous }</code> → <code>{ $new }</code> (balance v{ $version }).
admin-balance-set-already-at-value = ℹ️ Ключ <code>{ $path }</code> уже равен <code>{ $value }</code>.

# Общая для /confirm idempotency-replay
admin-idempotency-replay = ℹ️ Эта команда (<code>{ $command_kind }</code>) уже выполнялась минуту назад — повторное выполнение пропущено.

# ─────────────────────────────────────────────────────────────────────────────
# Спринт 2.5-D.5 — read-side observability `/audit` (ГДД §18.6.4)
# ─────────────────────────────────────────────────────────────────────────────

# /audit [target_tg_id|-] [action|-] [limit]
admin-audit-usage = ⚠️ Использование: <code>/audit [target_tg_id|-] [action|-] [limit]</code>. Все аргументы опциональны; <code>-</code> означает «без фильтра».
admin-audit-not-authorized = ❌ Только активные админы могут смотреть аудит-лог.
admin-audit-bad-tg-id = ⚠️ <code>{ $value }</code> не похож на tg_id (целое число) или <code>-</code>.
admin-audit-bad-limit = ⚠️ <code>{ $value }</code> не похож на limit (целое > 0).
admin-audit-unknown-action = ⚠️ Неизвестная action-категория <code>{ $value }</code>.
admin-audit-target-not-found = 🔍 Админ с tg_id <code>{ $tg_id }</code> не найден.
# Параметры $target — tg_id или «—»; $action — action-фильтр или «—».
admin-audit-empty = 🗒️ Записей не найдено (target=<code>{ $target }</code>, action=<code>{ $action }</code>).
# Заголовок выдачи без target-фильтра. $count — сколько строк ниже, $limit — кап.
admin-audit-header-all = 🗒️ Аудит-лог: { $count } последних записей (limit { $limit }, все админы).
# Заголовок выдачи с target-фильтром. $target_tg_id — tg_id админа.
admin-audit-header-target = 🗒️ Аудит-лог админа <code>{ $target_tg_id }</code>: { $count } последних записей (limit { $limit }).
# Дописывается к заголовку, если задан action-фильтр.
admin-audit-filter-action-suffix = Фильтр action: <code>{ $action }</code>.
# Одна строка списка. Параметры:
# $id, $occurred_at (ISO-8601 UTC), $actor_tg_id, $action, $target_kind, $target_id, $source, $reason.
admin-audit-row = • #{ $id } · { $occurred_at } · @{ $actor_tg_id } · <code>{ $action }</code> · { $target_kind }=<code>{ $target_id }</code> · src={ $source } · { $reason }

# ─────────────────────────────────────────────────────────────────────────────
# Спринт 2.5-D.1 — read-only карточка клана `/clan` (ГДД §18.6.5)
# ─────────────────────────────────────────────────────────────────────────────

# /clan <id|chat_id>
admin-clan-usage = ⚠ Использование: <code>/clan &lt;id|chat_id&gt;</code>.
admin-clan-not-authorized = ❌Только активные админы могут смотреть карточку клана.
admin-clan-bad-id = ⚠ <code>{ $value }</code> не похож на id клана (целое число).
admin-clan-not-found = 🔍Клан с id/chat_id <code>{ $query }</code> не найден.
# Шапка карточки. Параметры: $clan_id, $chat_id, $chat_kind, $title, $status, $created_at, $updated_at, $member_count, $active_member_count, $total_length_cm.
admin-clan-card-summary =
    🛡 Клан #{ $clan_id }: <b>{ $title }</b>
    chat_id: <code>{ $chat_id }</code> ({ $chat_kind })
    Статус: { $status }
    Создан: { $created_at } · обновлён: { $updated_at }
    Участников: { $member_count } (активных { $active_member_count }) · сумма длин: { $total_length_cm } см.
# Лидер каравана. Параметры: $tg_id, $username, $name, $length_cm, $joined_at.
admin-clan-card-leader = 👑 Лидер: @{ $username } ({ $name }, tg_id <code>{ $tg_id }</code>) · длина { $length_cm } см · с { $joined_at }.
admin-clan-card-no-leader = 👑 Лидер: —
# Одна строка участника. Параметры: $tg_id, $username, $name, $length_cm, $thickness_level, $status, $role, $joined_at.
admin-clan-card-member-row = • @{ $username } ({ $name }, tg_id <code>{ $tg_id }</code>) · { $length_cm } см · t{ $thickness_level } · { $status } · { $role } · с { $joined_at }
admin-clan-card-no-members = (в клане нет участников)

# ─────────────────────────────────────────────────────────────────────────────
# Спринт 2.5-D.2 — `/freeze_clan` / `/unfreeze_clan` (ГДД §18.6.5)
# ─────────────────────────────────────────────────────────────────────────────

# /freeze_clan <id|chat_id> [reason]
admin-freeze-clan-usage = ⚠ Использование: <code>/freeze_clan &lt;id|chat_id&gt; [reason]</code>.
admin-freeze-clan-not-authorized = ❌Только активные админы могут замораживать кланы.
admin-freeze-clan-bad-id = ⚠ <code>{ $value }</code> не похож на id клана (целое число).
admin-freeze-clan-not-found = 🔍Клан с id/chat_id <code>{ $query }</code> не найден.
admin-freeze-clan-already = ℹ Клан #{ $clan_id } уже заморожен.
admin-freeze-clan-ok = ❄ Клан #{ $clan_id } заморожен.{ $reason_suffix }
admin-freeze-clan-reason-suffix = Причина: { $reason }.

# /unfreeze_clan <id|chat_id>
admin-unfreeze-clan-usage = ⚠ Использование: <code>/unfreeze_clan &lt;id|chat_id&gt;</code>.
admin-unfreeze-clan-not-authorized = ❌Только активные админы могут размораживать кланы.
admin-unfreeze-clan-bad-id = ⚠ <code>{ $value }</code> не похож на id клана (целое число).
admin-unfreeze-clan-not-found = 🔍Клан с id/chat_id <code>{ $query }</code> не найден.
admin-unfreeze-clan-already = ℹ Клан #{ $clan_id } уже активен.
admin-unfreeze-clan-ok = 🔥 Клан #{ $clan_id } разморожен.

# ─────────────────────────────────────────────────────────────────────────────
# Спринт 2.5-D.3 — `/clan_daily_head_history` (read-only)
# ─────────────────────────────────────────────────────────────────────────────

admin-clan-daily-head-history-usage = ⚠ Использование: <code>/clan_daily_head_history &lt;id|chat_id&gt; [N=10]</code>.
admin-clan-daily-head-history-not-authorized = ❌Только активные админы могут смотреть историю «Главы клана дня».
admin-clan-daily-head-history-bad-id = ⚠ <code>{ $value }</code> не похож на id клана (целое число).
admin-clan-daily-head-history-bad-limit = ⚠ <code>{ $value }</code> не похож на лимит (целое число 1..50).
admin-clan-daily-head-history-not-found = 🔍Клан с id/chat_id <code>{ $query }</code> не найден.
admin-clan-daily-head-history-empty = 👑 Клан #{ $clan_id } «{ $title }»: история «Главы дня» пуста.
admin-clan-daily-head-history-header = 👑 Клан #{ $clan_id } «{ $title }», последние { $count } назначений «Главы дня»:
admin-clan-daily-head-history-row = • <b>{ $moscow_date }</b> — { $tg_id } (@{ $username }, { $name }) +{ $bonus } см ({ $source })
admin-clan-daily-head-history-row-orphan = • <b>{ $moscow_date }</b> — игрок удалён +{ $bonus } см ({ $source })

# ─────────────────────────────────────────────────────────────────────────────
# Спринт 2.5-D.4 — `/announce` (broadcast с TOTP-confirm)
# ─────────────────────────────────────────────────────────────────────────────

admin-announce-usage = ⚠ Использование: <code>/announce &lt;ru|en|*&gt; &lt;текст&gt;</code>. Локаль выбирает аудиторию: ru — игроки с RU-локалью, en — с EN или без явного выбора (default), * — все активные.
admin-announce-non-private = 🍆 Админ-команды доступны только в ЛС бота.
admin-announce-not-authorized = ❌Только активные админы могут запускать broadcast.
admin-announce-totp-not-configured = ❌У тебя не настроен TOTP. <code>/announce</code> без него недоступен.
admin-announce-bad-locale = ⚠ <code>{ $value }</code> — неизвестный фильтр локали. Допустимо: <code>ru</code>, <code>en</code>, <code>*</code>.
admin-announce-empty-message = ⚠ Текст объявления не может быть пустым.
admin-announce-too-long = ⚠ Сообщение слишком длинное: { $length } символов, максимум { $max_length }.
admin-announce-confirm-issued = 🛡 Готов разослать <b>{ $recipient_count }</b> игрокам (фильтр: { $locale_filter }). Подтверди: <code>/confirm { $token } &lt;6-значный код&gt;</code>. Токен живёт { $ttl_seconds } секунд.
admin-announce-progress-start = 📤 Запускаю рассылку: { $recipient_count } получателей (фильтр: { $locale_filter }). По окончании пришлю отчёт.
admin-announce-progress-final = ✅ Рассылка завершена. Получателей: { $recipient_count }, доставлено: { $sent_count }, ошибок: { $failed_count }, забанили бота: { $blocked_count }.
admin-announce-progress-failed = ⚠ Фоновая рассылка завершилась с ошибкой. Подробности — в логах бота и admin-аудите.

# ─────────────────────────────────────────────────────────────────────────────
# Спринт 2.5-D.6 — `/admin_setup_totp` (self-service выдача TOTP-секрета)
# ─────────────────────────────────────────────────────────────────────────────
# Сама пара «секрет + otpauth://-URI» в чат не уходит — handler пишет её
# только в `structlog`-лог сервера (event=admin_totp_setup). В Telegram-чате
# лежит только короткое подтверждение «настроено, см. логи».

admin-setup-totp-usage = ⚠ Использование: <code>/admin_setup_totp &lt;bootstrap-пароль&gt;</code>. Команда доступна только в ЛС бота.
admin-setup-totp-non-private = 🍆 Админ-команды доступны только в ЛС бота.
admin-setup-totp-not-authorized = ❌ Только активные super-admin-ы могут настраивать TOTP-секрет.
admin-setup-totp-password-not-configured = ❌ <code>BOOTSTRAP_ADMIN_PASSWORD</code> не задан в окружении бота. Команда отказывает (fail-closed): self-service-выдача нового TOTP-секрета без второго фактора недопустима.
admin-setup-totp-password-invalid = ❌ Неверный bootstrap-пароль.
admin-setup-totp-already-configured = ❌ TOTP уже настроен. Чтобы выдать новый секрет, потребуется ручной сброс через DBA (см. <code>docs/admin_runbook.md</code>).
admin-setup-totp-success = ✅ TOTP настроен. Секрет и <code>otpauth://</code>-URI записаны в server-side-логи (event=<code>admin_totp_setup</code>) — открой их у инфры и импортируй в Authenticator/1Password. В чат секрет не попадает намеренно.

# ============================================================================
# /mountains, /dungeon (Спринт 3.1-E, ГДД §8). PvE-локации с ±-исходом.
# Структура зеркальная forest-*; различие — два набора длина-строк
# (`-gain` / `-loss` / `-zero`) и `requirement-*` для проверок «нужна
# толщина N» / «нужно ≥ 20 см».
# ============================================================================

# --------------------------- /mountains -------------------------------------

mountains-group = 🏔 Команда /mountains доступна только в личке бота. Открой приватный чат и повтори.
mountains-other = 🏔 Команда /mountains доступна только в личке бота.
mountains-not-registered = 🏔 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда сможешь пойти в горы.
mountains-already-in = 🏔 Ты уже в горах — дождись возвращения. Бот пришлёт сообщение, когда поход закончится.
mountains-requirement-thickness = 🏔 В горы пускают с { NUMBER($required, useGrouping: 0) }-й толщины. У тебя сейчас { NUMBER($actual, useGrouping: 0) }-я. Прокачай /upgrade.
mountains-requirement-length = 🏔 Чтобы идти в горы, нужно ≥ { NUMBER($required_cm, useGrouping: 0) } см. У тебя { NUMBER($actual_cm, useGrouping: 0) } см.
mountains-started = 🏔 { $nick } ушёл в горы на { NUMBER($cooldown_minutes, useGrouping: 0) } минут...
mountains-started-fallback = 🏔 Ты ушёл в горы на { NUMBER($cooldown_minutes, useGrouping: 0) } минут...

mountains-finished-header = 🏔 { $nick } вернулся из гор!
mountains-finished-length-gain =
    📏 Длина: +{ NUMBER($length_delta_cm, useGrouping: 0) } см (было { NUMBER($length_before_cm, useGrouping: 0) }, стало { NUMBER($length_after_cm, useGrouping: 0) })
mountains-finished-length-loss =
    📏 Длина: −{ NUMBER($length_delta_abs_cm, useGrouping: 0) } см (было { NUMBER($length_before_cm, useGrouping: 0) }, стало { NUMBER($length_after_cm, useGrouping: 0) })
mountains-finished-length-zero =
    📏 Длина не изменилась ({ NUMBER($length_before_cm, useGrouping: 0) } см)
mountains-finished-item-found = 🎩 Нашёл: { $item_name } [{ $rarity }]

mountains-button-equip = Надеть
mountains-button-drop-item = Выбросить

mountains-toast-item-equipped-placeholder = Экипировка появится позже — предмет пока в инвентаре.
mountains-toast-item-dropped = Предмет выброшен.
mountains-toast-foreign-button = Эта кнопка не для тебя.
mountains-toast-run-not-found = Этот поход уже неактивен.
mountains-toast-drop-mismatch = Кнопка устарела.

# --------------------------- /dungeon ---------------------------------------

dungeon-group = 🏰 Команда /dungeon доступна только в личке бота. Открой приватный чат и повтори.
dungeon-other = 🏰 Команда /dungeon доступна только в личке бота.
dungeon-not-registered = 🏰 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда сможешь пойти в данжон.
dungeon-already-in = 🏰 Ты уже в данжоне — дождись возвращения. Бот пришлёт сообщение, когда поход закончится.
dungeon-requirement-thickness = 🏰 В данжон пускают с { NUMBER($required, useGrouping: 0) }-й толщины. У тебя сейчас { NUMBER($actual, useGrouping: 0) }-я. Прокачай /upgrade.
dungeon-requirement-length = 🏰 Чтобы идти в данжон, нужно ≥ { NUMBER($required_cm, useGrouping: 0) } см. У тебя { NUMBER($actual_cm, useGrouping: 0) } см.
dungeon-started = 🏰 { $nick } ушёл в данжон на { NUMBER($cooldown_minutes, useGrouping: 0) } минут...
dungeon-started-fallback = 🏰 Ты ушёл в данжон на { NUMBER($cooldown_minutes, useGrouping: 0) } минут...

dungeon-finished-header = 🏰 { $nick } вернулся из данжона!
dungeon-finished-length-gain =
    📏 Длина: +{ NUMBER($length_delta_cm, useGrouping: 0) } см (было { NUMBER($length_before_cm, useGrouping: 0) }, стало { NUMBER($length_after_cm, useGrouping: 0) })
dungeon-finished-length-loss =
    📏 Длина: −{ NUMBER($length_delta_abs_cm, useGrouping: 0) } см (было { NUMBER($length_before_cm, useGrouping: 0) }, стало { NUMBER($length_after_cm, useGrouping: 0) })
dungeon-finished-length-zero =
    📏 Длина не изменилась ({ NUMBER($length_before_cm, useGrouping: 0) } см)
dungeon-finished-item-found = 🎩 Нашёл: { $item_name } [{ $rarity }]

dungeon-button-equip = Надеть
dungeon-button-drop-item = Выбросить

dungeon-toast-item-equipped-placeholder = Экипировка появится позже — предмет пока в инвентаре.
dungeon-toast-item-dropped = Предмет выброшен.
dungeon-toast-foreign-button = Эта кнопка не для тебя.
dungeon-toast-run-not-found = Этот поход уже неактивен.
dungeon-toast-drop-mismatch = Кнопка устарела.

# ============================================================================
# /caravan (Спринт 3.2-D, ГДД §9). Караваны кланов: лидер
# собирает группу, идёт в чат другого клана, ловит атаку рейдеров.
# Команда работает только в личке бота: лидер указывает chat_id чата
# клана-получателя и величину взноса в см. Пост-объявление с кнопкой
# «Показать лобби» уходит в чат клана-отправителя.
# ============================================================================

caravans-group = 🐪 Команда /caravan доступна только в личке бота. Открой приватный чат и повтори.
caravans-other = 🐪 Команда /caravan доступна только в личке бота.
caravans-not-registered = 🐪 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда сможешь собрать караван.
caravans-usage =
    🐪 Чтобы собрать караван, укажи чат клана-получателя и взнос в см:
    <code>/caravan &lt;chat_id_получателя&gt; &lt;взнос_см&gt;</code>

    Пример: <code>/caravan -1001234567890 30</code>
caravans-receiver-invalid = 🐪 Не похоже на chat_id Telegram-чата: <code>{ $value }</code>. Передай числовой chat_id клана-получателя (для группового чата он отрицательный).
caravans-contribution-invalid = 🐪 Взнос должен быть положительным целым числом, передано: <code>{ $value }</code>.
caravans-no-clan = 🐪 У тебя нет клана. Караван собирает только лидер клана.
caravans-not-a-leader = 🐪 Караван собирает только лидер клана. Ты — обычный участник.
caravans-receiver-not-found = 🐪 Чат с chat_id <code>{ $chat_id }</code> не зарегистрирован как клан. Передай chat_id чата другого клана.
caravans-receiver-same-as-sender = 🐪 Караван к собственному клану невозможен. Передай chat_id чужого клана.
caravans-already-in = 🐪 У твоего клана уже идёт активный караван — дождись его завершения или отмени из лобби.
caravans-cooldown = 🐪 Кулдаун клана между караванами ещё не истёк. Попробуй через { NUMBER($remaining_minutes, useGrouping: 0) } мин.
caravans-requirement-thickness = 🐪 Караван собирает лидер с толщиной ≥ { NUMBER($required, useGrouping: 0) }. У тебя сейчас { NUMBER($actual, useGrouping: 0) }. Прокачай /upgrade.
caravans-requirement-length = 🐪 После взноса должно остаться ≥ { NUMBER($required_cm, useGrouping: 0) } см длины. У тебя после взноса будет { NUMBER($actual_cm, useGrouping: 0) } см.
caravans-player-frozen = 🐪 Твой профиль заморожен — собрать караван нельзя.
caravans-clan-frozen-sender = 🐪 Твой клан заморожен — собрать караван нельзя.
caravans-clan-frozen-receiver = 🐪 Клан-получатель заморожен — отправить караван к нему нельзя.

caravans-created-private =
    🐪 Караван собран!
    Получатель: <b>{ $receiver_clan_name }</b>
    Взнос: { NUMBER($contribution_cm, useGrouping: 0) } см
    Лобби открыто на { NUMBER($lobby_minutes, useGrouping: 0) } мин — объявление ушло в чат твоего клана.
caravans-created-announcement =
    🐪 <b>{ $leader_nick }</b> собирает караван!
    Цель: <b>{ $receiver_clan_name }</b>
    Взнос лидера: { NUMBER($contribution_cm, useGrouping: 0) } см
    Лобби открыто на { NUMBER($lobby_minutes, useGrouping: 0) } мин — успей вступить.
caravans-button-show-lobby = Показать лобби
caravans-button-cancel = Отменить караван

# --- Callback `caravan:show_lobby:<id>` (Спринт 3.2-D, D.3c) ---

caravans-lobby-state =
    🐪 <b>{ $leader_nick }</b> собирает караван к <b>{ $receiver_clan_name }</b>
    Лобби { $lobby_status }.

    Состав:
    • Караванщики: { NUMBER($caravaneers_count, useGrouping: 0) } (взнос: { NUMBER($total_contribution_cm, useGrouping: 0) } см)
    • Защитники: { NUMBER($defenders_count, useGrouping: 0) } / { NUMBER($defenders_cap, useGrouping: 0) }
    • Рейдеры: { NUMBER($raiders_count, useGrouping: 0) } / { NUMBER($raiders_cap, useGrouping: 0) }
caravans-lobby-status-open = закроется через { NUMBER($remaining_minutes, useGrouping: 0) } мин
caravans-lobby-status-closing = закрывается
caravans-button-join-defender = Вступить как защитник
caravans-button-join-raider = Вступить как рейдер
caravans-button-leave = Покинуть

# --- Старт боя / финиш боя (Спринт 3.2-D, D.4–D.6) ---
# Публикуются APScheduler-callback-ами в чат-отправитель и чат-получатель
# каравана сразу после успешных `LOBBY → IN_BATTLE` и `IN_BATTLE → FINISHED`.

caravans-battle-started =
    🐪 Караван от <b>{ $sender_clan_name }</b> к <b>{ $receiver_clan_name }</b> отправился в путь!

    Лидер: <b>{ $leader_nick }</b>
    Караванщики: { NUMBER($caravaneers_count, useGrouping: 0) }
    Защитники: { NUMBER($defenders_count, useGrouping: 0) }
    Рейдеры: { NUMBER($raiders_count, useGrouping: 0) }
    Груз: { NUMBER($total_cargo_cm, useGrouping: 0) } см

    ⚔️ Бой завершится примерно через { NUMBER($battle_minutes, useGrouping: 0) } мин.
caravans-battle-finished-delivered =
    ✅ Караван от <b>{ $sender_clan_name }</b> доставлен в <b>{ $receiver_clan_name }</b>!

    Лидер: <b>{ $leader_nick }</b>
    Караванщики выжили: { NUMBER($caravaneers_alive, useGrouping: 0) } / { NUMBER($caravaneers_total, useGrouping: 0) }
    Защитники выжили: { NUMBER($defenders_alive, useGrouping: 0) } / { NUMBER($defenders_total, useGrouping: 0) }

    🎁 Каждый член клана-отправителя получил +{ NUMBER($clan_bonus_sender_cm, useGrouping: 0) } см.
    🎁 Каждый член клана-получателя получил +{ NUMBER($clan_bonus_receiver_cm, useGrouping: 0) } см.
caravans-battle-finished-raided =
    ☠️ Караван от <b>{ $sender_clan_name }</b> к <b>{ $receiver_clan_name }</b> разграблен!

    Лидер: <b>{ $leader_nick }</b>
    Атаман-победитель: <b>{ $ataman_nick }</b>

    Груз ({ NUMBER($total_cargo_cm, useGrouping: 0) } см) поделён между { NUMBER($raiders_count, useGrouping: 0) } рейдерами.

# --- Callback `caravan:cancel:<id>` (Спринт 3.2-D, D.3) ---

caravans-cancel-message = 🐪 Караван отменён лидером.
caravans-cancel-toast-success = Караван отменён
caravans-cancel-toast-already-cancelled = Караван уже был отменён ранее

# --- Общие callback-toast-ы каравана (Спринт 3.2-D, D.3) ---

caravans-callback-toast-caravan-not-found = Караван не найден
caravans-callback-toast-invalid-state = Караван больше не в лобби
caravans-callback-toast-not-a-leader = Только лидер может отменить караван
caravans-callback-toast-player-not-found = Сначала нажми /start в личке бота
caravans-callback-toast-generic-error = Что-то пошло не так. Попробуй ещё раз.

# --- Callback `caravan:join_defender|join_raider:<id>` (Спринт 3.2-D, D.3d) ---

caravans-join-toast-success-defender = Ты в лобби как защитник
caravans-join-toast-success-raider = Ты в лобби как рейдер
caravans-callback-toast-lobby-closed = Лобби каравана уже закрыто
caravans-callback-toast-player-frozen = Твой профиль заморожен
caravans-callback-toast-already-in-caravan = Ты уже участвуешь в активном караване
caravans-callback-toast-role-conflict-defender = Защитник должен состоять в клане-получателе
caravans-callback-toast-role-conflict-raider = Рейдер не должен состоять ни в одном из кланов каравана
caravans-callback-toast-capacity-defender = Лимит защитников: { NUMBER($limit, useGrouping: 0) }. Слотов больше нет.
caravans-callback-toast-capacity-raider = Лимит рейдеров: { NUMBER($limit, useGrouping: 0) }. Слотов больше нет.
caravans-callback-toast-requirement-thickness = Нужна толщина ≥ { NUMBER($required, useGrouping: 0) }. У тебя { NUMBER($actual, useGrouping: 0) }.
caravans-callback-toast-requirement-length = Нужна длина ≥ { NUMBER($required_cm, useGrouping: 0) } см. У тебя { NUMBER($actual_cm, useGrouping: 0) } см.

# --- Callback `caravan:leave:<id>` (Спринт 3.2-D, D.3e) ---

caravans-leave-toast-success = Ты вышел из лобби каравана
caravans-leave-toast-success-with-contribution = Ты вышел из лобби. Возвращено: { NUMBER($contribution_cm, useGrouping: 0) } см
caravans-leave-toast-leader-cannot-leave = Лидер не может выйти. Чтобы распустить караван, нажми «Отменить».
caravans-leave-toast-not-a-participant = Ты не участник этого каравана

# --- Команда `/caravan_join` (Спринт 3.2-D, D.3f) ---
# Команда работает только в личке: игрок указывает caravan_id и взнос в см,
# чтобы вступить в лобби как CARAVANEER (для DEFENDER/RAIDER — инлайн-кнопки
# в lobby-сообщении, контрибьюция там не требуется).

caravans-join-usage =
    🐪 Чтобы вступить в караван как караванщик, укажи caravan_id (виден в лобби) и взнос в см:
    <code>/caravan_join &lt;caravan_id&gt; &lt;взнос_см&gt;</code>

    Пример: <code>/caravan_join 42 30</code>
caravans-join-caravan-id-invalid = 🐪 caravan_id должен быть положительным целым числом, передано: <code>{ $value }</code>.
caravans-join-success-caravaneer =
    🐪 Ты вступил в караван как караванщик!
    Взнос: { NUMBER($contribution_cm, useGrouping: 0) } см
caravans-join-role-conflict-caravaneer = 🐪 Караванщиком может стать только член клана-отправителя.

# ============================================================================
# /boss (Спринт 3.3-D, ГДД §10). Рейд-боссы: саммонер вызывает
# случайного игрока из топ-30 на бой, собирает лобби рейдеров,
# группа сражается с боссом фиксированными по длительности раундами.
# Команда работает в личке бота; объявление с кнопкой «Показать
# лобби» уходит в тот же чат, откуда был вызван `/boss` (группа или личка).
# ============================================================================

bosses-not-registered = 👹 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда сможешь призвать рейд-босса.
bosses-usage = 👹 Чтобы призвать рейд-босса, просто напиши <code>/boss</code> — случайный игрок из топ-{ NUMBER($top_n_pool, useGrouping: 0) } станет боссом.
bosses-cooldown = 👹 Глобальный кулдаун рейд-боссов ещё не истёк. Попробуй через { NUMBER($remaining_minutes, useGrouping: 0) } мин.
bosses-already-in = 👹 Ты уже участвуешь в активном рейде — дождись его завершения или сначала покинь лобби.
bosses-requirement-thickness = 👹 Чтобы призвать рейд-босса, нужна толщина ≥ { NUMBER($required, useGrouping: 0) }. У тебя сейчас { NUMBER($actual, useGrouping: 0) }. Прокачай /upgrade.
bosses-requirement-length = 👹 Чтобы призвать рейд-босса, нужна длина ≥ { NUMBER($required_cm, useGrouping: 0) } см. У тебя { NUMBER($actual_cm, useGrouping: 0) } см.
bosses-player-frozen = 👹 Твой профиль заморожен — призвать рейд-босса нельзя.
bosses-pool-empty = 👹 Подходящих кандидатов в боссы сейчас нет — попробуй позже.

bosses-summoned-private =
    👹 Рейд-босс призван!
    Босс: <b>{ $boss_nick }</b> ({ NUMBER($boss_length_cm, useGrouping: 0) } см)
    Лобби открыто на { NUMBER($lobby_minutes, useGrouping: 0) } мин — объявление ушло в чат.
bosses-summoned-announcement =
    👹 <b>{ $summoner_nick }</b> бросает вызов <b>{ $boss_nick }</b>!
    Длина босса: { NUMBER($boss_length_cm, useGrouping: 0) } см
    Лобби открыто на { NUMBER($lobby_minutes, useGrouping: 0) } мин — успей вступить.
bosses-button-show-lobby = Показать лобби
bosses-button-cancel = Отменить рейд

# --- Callback `boss:show_lobby:<id>` (Спринт 3.3-D, D.4) ---

bosses-lobby-state =
    👹 <b>{ $summoner_nick }</b> рейдит <b>{ $boss_nick }</b>
    Лобби { $lobby_status }.

    Длина босса: { NUMBER($boss_length_cm, useGrouping: 0) } см
    Рейдеры: { NUMBER($raiders_count, useGrouping: 0) }
bosses-lobby-status-open = закроется через { NUMBER($remaining_minutes, useGrouping: 0) } мин
bosses-lobby-status-closing = закрывается
bosses-button-join = Вступить в рейд
bosses-button-leave = Покинуть

# --- Старт боя / тик раунда / финиш боя (Спринт 3.3-D, D.7) ---
# Публикуются APScheduler-callback-ами в чат, откуда был вызван `/boss`,
# сразу после `LOBBY → IN_BATTLE`, после каждого раунда и на
# `IN_BATTLE → FINISHED`.

bosses-battle-started =
    👹 Рейд против <b>{ $boss_nick }</b> начался!

    Саммонер: <b>{ $summoner_nick }</b>
    Рейдеры: { NUMBER($raiders_count, useGrouping: 0) }
    Длина босса: { NUMBER($boss_length_cm, useGrouping: 0) } см

    ⚔️ Босс бьёт раз в { NUMBER($round_seconds, useGrouping: 0) } сек.
bosses-round-tick =
    ⚔️ Раунд { NUMBER($round_number, useGrouping: 0) } — босс <b>{ $boss_nick }</b>

    Урон по боссу: { NUMBER($boss_damage_cm, useGrouping: 0) } см (осталось { NUMBER($boss_length_cm, useGrouping: 0) } см)
    Выбыло: { NUMBER($eliminated_count, useGrouping: 0) }
    Рейдеров осталось: { NUMBER($raiders_alive, useGrouping: 0) }
bosses-battle-finished-victory =
    🏆 Рейдеры одолели <b>{ $boss_nick }</b>!

    Саммонер: <b>{ $summoner_nick }</b>
    Рейдеров выжило: { NUMBER($raiders_alive, useGrouping: 0) }

    🎁 Каждый выживший рейдер получает +{ NUMBER($per_raider_grant_cm, useGrouping: 0) } см.
bosses-battle-finished-defeat =
    ☠️ Рейд против <b>{ $boss_nick }</b> провален!

    Саммонер: <b>{ $summoner_nick }</b>
    Рейдеров выжило: { NUMBER($raiders_alive, useGrouping: 0) }

    Босс забирает { NUMBER($total_granted_cm, useGrouping: 0) } см длины.

# --- Callback `boss:cancel:<id>` (Спринт 3.3-D, D.4) ---

bosses-cancel-message = 👹 Рейд отменён саммонером.
bosses-cancel-toast-success = Рейд отменён
bosses-cancel-toast-already-cancelled = Рейд уже был отменён ранее

# --- Общие callback-toast-ы рейд-босса (Спринт 3.3-D, D.4) ---

bosses-callback-toast-fight-not-found = Рейд не найден
bosses-callback-toast-invalid-state = Рейд больше не в лобби
bosses-callback-toast-not-summoner = Только саммонер может отменить рейд
bosses-callback-toast-player-not-found = Сначала нажми /start в личке бота
bosses-callback-toast-player-frozen = Твой профиль заморожен
bosses-callback-toast-generic-error = Что-то пошло не так. Попробуй ещё раз.

# --- Callback `boss:join:<id>` (Спринт 3.3-D, D.4) ---

bosses-join-toast-success = Ты вступил в рейд
bosses-callback-toast-lobby-closed = Лобби рейда уже закрыто
bosses-callback-toast-already-in-fight = Ты уже участвуешь в этом рейде
bosses-callback-toast-cannot-join-as-boss = Вступить рейдером нельзя — ты сам босс
bosses-callback-toast-requirement-thickness = Нужна толщина ≥ { NUMBER($required, useGrouping: 0) }. У тебя { NUMBER($actual, useGrouping: 0) }.
bosses-callback-toast-requirement-length = Нужна длина ≥ { NUMBER($required_cm, useGrouping: 0) } см. У тебя { NUMBER($actual_cm, useGrouping: 0) } см.

# --- Callback `boss:leave:<id>` (Спринт 3.3-D, D.4) ---

bosses-leave-toast-success = Ты вышел из лобби рейда
bosses-leave-toast-not-a-participant = Ты не участник этого рейда
bosses-leave-toast-summoner-leaves = Саммонер не может выйти — нажми «Отменить рейд».

## /inventory + /enchant (Спринт 3.4-D)

# --- /inventory ---

inventory-group = 🎒 Команда /inventory работает только в личке бота. Откройте чат с ботом и попробуйте снова.

inventory-other = 🎒 Команда /inventory работает только в личке бота.

inventory-not-registered = 🎒 Похоже, вы ещё не зарегистрированы. Нажмите /start в этом чате — тогда сможете посмотреть инвентарь.

inventory-empty = 🎒 Ваш инвентарь пуст.\nСходите в /forest, /mountains, на /boss или в /caravan — там можно получить предметы и свитки.

# Карточка инвентаря. Параметры:
# - `$items_count` — общее количество предметов.
# - `$scrolls_count` — общее количество стэков свитков.
inventory-card =
    🎒 Инвентарь
    Предметов: { NUMBER($items_count, useGrouping: 0) }
    Стэков свитков: { NUMBER($scrolls_count, useGrouping: 0) }

# Строка одного предмета. Параметры:
# - `$display_name` — каталожное имя (например, «Шапка воеводы»).
# - `$enchant_suffix` — преформатированный суффикс «+N» (или пусто при +0).
# - `$slot_label` — локализованное имя слота.
# - `$rarity_label` — локализованное имя редкости.
inventory-item-line = • <b>{ $display_name }{ $enchant_suffix }</b> [{ $slot_label }, { $rarity_label }]

# Строка одного стэка свитков. Параметры:
# - `$scroll_label` — локализованное имя свитка.
# - `$qty` — количество.
inventory-scroll-line = • { $scroll_label } × { NUMBER($qty, useGrouping: 0) }

inventory-section-items = 📦 Предметы:
inventory-section-scrolls = 📜 Свитки:

# Inline-кнопка «Заточить» в карточке предмета.
inventory-button-enchant = ⚒ Заточить

# Тост, когда нет подходящих свитков для предмета.
inventory-toast-no-scroll = Нет подходящих свитков для этого предмета.

# Picker-карточка выбора свитка (regular vs blessed) — D.1d.
# Параметры:
# - `$item_display` — полное красивое имя предмета с +N (например, «Меч +5»).
inventory-picker-card =
    ⚒ Заточка предмета
    Предмет: <b>{ $item_display }</b>

    Выберите свиток для заточки.

inventory-picker-button-regular = Обычный свиток
inventory-picker-button-blessed = Благословлённый свиток
inventory-picker-button-cancel = Отмена

inventory-picker-cancelled = Заточка отменена.

# Toast после нажатия «Отмена» в picker-е (Telegram-лимит ≤ 200 символов).
inventory-picker-toast-cancelled = Отменено.

# Имена слотов (8 слотов, ГДД §2.6).
inventory-slot-hat = голова
inventory-slot-body = тело
inventory-slot-legs = ноги
inventory-slot-boots = обувь
inventory-slot-ring = кольцо
inventory-slot-chain = цепочка
inventory-slot-right-hand = правая рука
inventory-slot-left-hand = левая рука

# Имена редкостей (ГДД §2.5).
inventory-rarity-common = обычное
inventory-rarity-uncommon = необычное
inventory-rarity-rare = редкое
inventory-rarity-epic = эпическое
inventory-rarity-legendary = легендарное

# Имена свитков.
# `$category_label` — одно из inventory-scroll-category-*.
inventory-scroll-display-regular = свиток на { $category_label }
inventory-scroll-display-blessed = благословлённый свиток на { $category_label }

inventory-scroll-category-weapon = оружие
inventory-scroll-category-armor = броню
inventory-scroll-category-jewelry = украшение

# --- /enchant ---

enchant-group = ⚒ Команда /enchant работает только в личке бота. Откройте чат с ботом и попробуйте снова.

enchant-other = ⚒ Команда /enchant работает только в личке бота.

enchant-not-registered = ⚒ Похоже, вы ещё не зарегистрированы. Нажмите /start в этом чате — тогда сможете точить.

enchant-usage = Использование: <code>/enchant &lt;item_id&gt; &lt;scroll_id&gt;</code>\n\nПример: <code>/enchant item.right_hand.test_1 weapon_scroll:regular</code>\n\nИли откройте /inventory и нажмите кнопку ⚒ Заточить на карточке предмета.

# Карточка-предупреждение перед подтверждением. Параметры:
# - `$item_display` — полное красивое имя с +N (например, «Меч +5»).
# - `$scroll_display` — красивое имя свитка.
# - `$tier_label` — локализованный тир (safe / easy / hard / very-hard / extreme / impossible).
# - `$tier_emoji` — эмодзи тира.
enchant-warning-regular =
    ⚒ Попытка заточки
    Предмет: <b>{ $item_display }</b>
    Свиток: { $scroll_display }
    Тир: { $tier_emoji } { $tier_label }

    Возможные исходы:
    • Успех (+1)
    • Без эффекта
    • Падение (-1)
    • <b>Уничтожение</b> (предмет потерян безвозвратно)

enchant-warning-blessed =
    ⚒ Благословлённая заточка
    Предмет: <b>{ $item_display }</b>
    Свиток: { $scroll_display }
    Тир: { $tier_emoji } { $tier_label }

    Возможные исходы:
    • Большой успех (+2)
    • Успех (+1)
    • Без эффекта
    • Падение (-1)
    • Большое падение (-2)

    Благословлённый свиток никогда не уничтожает предмет.

# Inline-кнопки для подтверждения/отмены.
enchant-button-confirm = Подтвердить
enchant-button-cancel = Отмена

# Результат. Параметры в каждом:
# - `$item_display` — полное красивое имя с новым +N (после).
# - `$old_level` — уровень до попытки.
# - `$new_level` — уровень после попытки.
enchant-success =
    ✅ Успех! { $item_display }
    Уровень: +{ NUMBER($old_level, useGrouping: 0) } → +{ NUMBER($new_level, useGrouping: 0) }

enchant-no-effect =
    ⚪ Без эффекта.
    Предмет: <b>{ $item_display }</b>
    Уровень не изменился: +{ NUMBER($old_level, useGrouping: 0) }
    Свиток израсходован.

enchant-drop =
    🔻 Падение.
    Предмет: <b>{ $item_display }</b>
    Уровень: +{ NUMBER($old_level, useGrouping: 0) } → +{ NUMBER($new_level, useGrouping: 0) }

enchant-destroy =
    💥 Предмет уничтожен!
    <b>{ $item_display }</b> потерян безвозвратно.

enchant-cancelled = Заточка отменена.

enchant-idempotent = ℹ Эта попытка уже обработана. Откройте /inventory, чтобы увидеть актуальное состояние.

# Имена тиров + эмодзи (ГДД §2.8.5).
enchant-tier-safe = безопасный
enchant-tier-easy = лёгкий
enchant-tier-hard = сложный
enchant-tier-very-hard = очень сложный
enchant-tier-extreme = экстремальный
enchant-tier-impossible = невозможный

# Сообщения об ошибках.
enchant-error-wrong-category = ⚠ Этим свитком нельзя заточить этот предмет: не совпадает категория.
enchant-error-item-not-found = ⚠ Предмет не найден в инвентаре.
enchant-error-scroll-not-found = ⚠ У вас нет такого свитка.
enchant-error-out-of-stock = ⚠ Свитки закончились.
enchant-error-bad-args = ⚠ Неверные аргументы. См. /enchant.

# Тосты для callback-ответов (лимит Telegram ≤ 200 символов).
enchant-toast-confirmed = Заточка завершена.
enchant-toast-cancelled = Заточка отменена.
enchant-toast-already-processed = Уже обработано.
enchant-toast-error = Что-то пошло не так.

# ============================================================================
# /roulette_free (Спринт 3.5-D, ГДД §12.4). Free-to-play рулетка:
# толщина ≥ 2, списание 100 см, разыгрывается приз — длина (LENGTH-исход)
# или зарезервированные предметы / скроллы / крипто-лоты (Phase 4).
# Команда работает только в личке бота.
# ============================================================================

roulette-free-group = 🎰 Команда /roulette_free доступна только в личке бота. Открой приватный чат и повтори.
roulette-free-other = 🎰 Команда /roulette_free доступна только в личке бота.
roulette-free-not-registered = 🎰 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда сможешь крутить рулетку.

# Gate-warning-карточки в личке (вместо pre-spin-карточки).
roulette-free-requirement-thickness = 🎰 Рулетка открывается с толщиной ≥ { NUMBER($required, useGrouping: 0) }. У тебя сейчас { NUMBER($actual, useGrouping: 0) }. Прокачай /upgrade.
roulette-free-requirement-length = 🎰 Для прокрутки нужно ≥ { NUMBER($required_cm, useGrouping: 0) } см. У тебя сейчас { NUMBER($actual_cm, useGrouping: 0) } см.

# Pre-spin карточка с кнопкой [Прокрутить — 100 см].
roulette-free-prompt =
    🎰 Free-рулетка
    Текущая длина: { NUMBER($current_length_cm, useGrouping: 0) } см
    Стоимость прокрутки: { NUMBER($cost_cm, useGrouping: 0) } см
    После прокрутки останется: { NUMBER($remaining_cm, useGrouping: 0) } см

    Нажми кнопку, чтобы прокрутить.

roulette-free-button-spin = Прокрутить — { NUMBER($cost_cm, useGrouping: 0) } см

# Анимация прокрутки (3 кадра через edit_text).
roulette-free-animation-frame-1 = 🎰 Прокручиваем рулетку…
roulette-free-animation-frame-2 = 🎰 Шарик ещё крутится…
roulette-free-animation-frame-3 = 🎰 Почти остановился…

# Result-карточки. Параметры в каждой: $cost_cm — фактически списано;
# в LENGTH-варианте дополнительно $length_cm — приз в см.
roulette-free-result-length =
    🎰 Длина! Тебе выпало <b>+{ NUMBER($length_cm, useGrouping: 0) } см</b>.
    Списано за прокрутку: { NUMBER($cost_cm, useGrouping: 0) } см.

roulette-free-result-item =
    🎰 Тебе выпал предмет!
    Списано: { NUMBER($cost_cm, useGrouping: 0) } см.
    Награда будет начислена в Phase 4 — пока что попадание зафиксировано.

roulette-free-result-scroll-regular =
    🎰 Тебе выпал свиток!
    Списано: { NUMBER($cost_cm, useGrouping: 0) } см.
    Награда будет начислена в Phase 4 — пока что попадание зафиксировано.

roulette-free-result-scroll-blessed =
    🎰 Тебе выпал благословлённый свиток!
    Списано: { NUMBER($cost_cm, useGrouping: 0) } см.
    Награда будет начислена в Phase 4 — пока что попадание зафиксировано.

roulette-free-result-crypto-lot =
    🎰 Тебе выпал крипто-лот!
    Списано: { NUMBER($cost_cm, useGrouping: 0) } см.
    Награда будет начислена в Phase 4 — пока что попадание зафиксировано.

roulette-free-result-idempotent = ℹ Эта прокрутка уже завершена. Открой /profile, чтобы увидеть актуальное состояние.

# Toast-ы для callback-ответов (Telegram ≤ 200 символов).
roulette-free-toast-thickness-gate = Нужна толщина ≥ { NUMBER($required, useGrouping: 0) }. У тебя { NUMBER($actual, useGrouping: 0) }.
roulette-free-toast-insufficient-length = Нужно ≥ { NUMBER($required_cm, useGrouping: 0) } см. У тебя { NUMBER($actual_cm, useGrouping: 0) } см.
roulette-free-toast-not-registered = Сначала /start в личке бота.
roulette-free-toast-spin-complete = Прокрутка завершена.
roulette-free-toast-already-processed = Уже обработано.
roulette-free-toast-error = Что-то пошло не так.

# -----------------------------------------------------------------------------
# /roulette_paid (Спринт 4.1-A, ГДД §12.5). Платная рулетка за Telegram Stars:
# 1 ⭐ = 1 спин, 9 ⭐ = 10 спинов. Толщина ≥ 1 (доступна со старта).
# Cost списывается в Stars через invoice + pre_checkout_query +
# successful_payment-flow. На LENGTH-исходе игрок получает «свежие» см
# (`ROULETTE_PAID_REWARD`), на остальных — заглушка до 4.1-C.
# -----------------------------------------------------------------------------
roulette-paid-group = 🎰 Команда /roulette_paid доступна только в личке бота. Открой приватный чат и повтори.
roulette-paid-other = 🎰 Команда /roulette_paid доступна только в личке бота.
roulette-paid-not-registered = 🎰 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда сможешь крутить рулетку.

# Gate-warning-карточка (если толщина < min_thickness_level конфига).
roulette-paid-requirement-thickness = 🎰 Платная рулетка открывается с толщиной ≥ { NUMBER($required, useGrouping: 0) }. У тебя сейчас { NUMBER($actual, useGrouping: 0) }. Прокачай /upgrade.

# Pre-spin карточка с двумя кнопками покупки (single и pack-10).
roulette-paid-prompt =
    🎰 Платная рулетка
    Каждый спин — шанс на длину, шмот, свиток или крипто-приз.

    Стоимость:
    — 1 спин: { NUMBER($single_cost_stars, useGrouping: 0) } ⭐
    — { NUMBER($pack10_spins, useGrouping: 0) }-pack: { NUMBER($pack10_cost_stars, useGrouping: 0) } ⭐

    Выбери пакет, чтобы оформить покупку.

roulette-paid-button-buy-single = Купить 1 спин — { NUMBER($cost_stars, useGrouping: 0) } ⭐
roulette-paid-button-buy-pack-10 = Купить { NUMBER($pack10_spins, useGrouping: 0) }-pack — { NUMBER($cost_stars, useGrouping: 0) } ⭐

# Invoice (Telegram Stars) — title / description / label per-pack.
roulette-paid-invoice-title-single = 🎰 Платная рулетка — 1 спин
roulette-paid-invoice-title-pack-10 = 🎰 Платная рулетка — pack-10
roulette-paid-invoice-description-single = Один спин платной рулетки за { NUMBER($cost_stars, useGrouping: 0) } ⭐. Шанс на длину, шмот, свиток или крипто-приз.
roulette-paid-invoice-description-pack-10 = { NUMBER($pack10_spins, useGrouping: 0) } спинов платной рулетки за { NUMBER($cost_stars, useGrouping: 0) } ⭐. Скидка ~10 % vs одиночные покупки.
roulette-paid-invoice-label-single = Платная рулетка — 1 спин
roulette-paid-invoice-label-pack-10 = Платная рулетка — { NUMBER($pack10_spins, useGrouping: 0) }-pack

# Result-карточки SINGLE-pack-а (один outcome).
roulette-paid-result-single-length =
    🎰 Длина! Тебе выпало <b>+{ NUMBER($length_cm, useGrouping: 0) } см</b>.
    Списано: { NUMBER($spent_stars, useGrouping: 0) } ⭐.

roulette-paid-result-single-item =
    🎰 Тебе выпал предмет!
    Списано: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    Награда будет начислена в Phase 4 — пока что попадание зафиксировано.

roulette-paid-result-single-scroll-regular =
    🎰 Тебе выпал свиток!
    Списано: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    Награда будет начислена в Phase 4 — пока что попадание зафиксировано.

roulette-paid-result-single-scroll-blessed =
    🎰 Тебе выпал благословлённый свиток!
    Списано: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    Награда будет начислена в Phase 4 — пока что попадание зафиксировано.

roulette-paid-result-single-crypto-lot =
    🎰 Тебе выпал крипто-лот!
    Списано: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    Награда будет начислена в Phase 4 — пока что попадание зафиксировано.

# Result-карточка PACK_10-а — агрегированная сводка по pack10_spins outcome-ам.
roulette-paid-result-pack-10 =
    🎰 Pack-{ NUMBER($n_spins, useGrouping: 0) } завершён!
    Длина: <b>+{ NUMBER($total_length_cm, useGrouping: 0) } см</b> ({ NUMBER($n_length, useGrouping: 0) } из { NUMBER($n_spins, useGrouping: 0) }).
    Шмот: { NUMBER($n_item, useGrouping: 0) }, свитки: { NUMBER($n_scroll_regular, useGrouping: 0) }, благ. свитки: { NUMBER($n_scroll_blessed, useGrouping: 0) }, крипто-лоты: { NUMBER($n_crypto_lot, useGrouping: 0) }.
    Списано: { NUMBER($spent_stars, useGrouping: 0) } ⭐.

roulette-paid-result-idempotent = ℹ Эта прокрутка уже завершена. Открой /profile, чтобы увидеть актуальное состояние.

# Toast-ы.
roulette-paid-toast-thickness-gate = Нужна толщина ≥ { NUMBER($required, useGrouping: 0) }. У тебя { NUMBER($actual, useGrouping: 0) }.
roulette-paid-toast-not-registered = Сначала /start в личке бота.
roulette-paid-toast-payment-ok = Платёж проведён, рулетка прокручена.
roulette-paid-toast-already-processed = Уже обработано.
roulette-paid-toast-error = Что-то пошло не так.
