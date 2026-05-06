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
