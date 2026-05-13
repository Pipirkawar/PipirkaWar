# Bot localization for "Pipirik Wars" — UK (Ukrainian).
#
# Sprint 4.1-K (task 4.1.14): "Catalog of locales expanded to 8 (+pt/es/tr/id/fa/uk)".
# Contentful bootstrap: 30-50 high-traffic onboarding keys (`start-*`,
# `profile-*`, `top-*`, `clantop-*`, `forest-*`, `lang-*`). Остальные
# ~1550 ключей рендерятся через `FluentMessageBundle`-fallback на EN
# (см. `infrastructure/i18n/fluent_bundle.py`).
#
# Conventions: same as `en.ftl` (Fluent placeholders `{ $name }`,
# HTML `<b>`/`<i>` allowed, indentation = 4 spaces for continuation
# lines).

## /start

start-registered = 🍆 Готово! Ти зареєстрований у Pipirik Wars.

    Початкова довжина — 2 см, товщина — рівень 1. Твоє ім'я та титул з'являться пізніше — у першому поході до лісу.

start-already = 🍆 Ти вже зареєстрований. Використай /profile, щоб переглянути свою картку.

start-group = 🍆 "Pipirik Wars" тут!

    1. Спочатку зареєструйся в особистому чаті з ботом: відкрий ЛС і натисни /start.
    2. Потім додай мене до групи як адміна — це перетворить чат на клан.

start-other = 🍆 "Pipirik Wars" тут. Команда /start працює в ЛС або в групі.

start-queued = 🍆 Сервери переповнені — ми додали тебе в чергу.

    Твоя позиція: #{ $position }.
    Щойно з'явиться вільне місце, ми зареєструємо тебе і надішлемо сповіщення.

start-registered-with-referral = 🍆 Готово! Ти зареєстрований у Pipirik Wars.

    Початкова довжина — 2 см + <b>{ $bonus_cm } см бонусу за прихід через реферальне посилання</b>. Товщина — рівень 1. Твоє ім'я та титул з'являться пізніше — у першому поході до лісу.

## /profile

profile-group = 🍆 Команда /profile працює лише в ЛС бота. Відкрий приватний чат і спробуй ще раз.

profile-other = 🍆 Команда /profile працює лише в ЛС бота.

profile-not-registered = 🍆 Здається, ти ще не зареєстрований. Натисни /start у цьому чаті — і твоя картка з'явиться.

profile-title-newbie = Новачок
profile-title-ataman = Бандитський Отаман

profile-card =
    🏷 { $nick }

    📏 Довжина: { $length_cm } см
    📐 Товщина: { $thickness_level }

    🎽 Спорядження: поки порожньо

## /top

top-header = 🏆 <b>Топ Пипириків</b>

top-empty = 🏆 Топ поки порожній. Будь першим — натисни /start!

top-entry = { $rank }. { $nick } — { $length_cm } см

## /clantop

clantop-header = 🛡 <b>Топ кланів</b>

clantop-empty = 🛡 У топі ще немає кланів. Додай бота до групи — і зареєструй свій клан!

clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } см ({ $member_count } 👥)

## /forest

forest-group = 🍆 Команда /forest доступна лише в приватному чаті бота. Відкрий ЛС і спробуй ще раз.

forest-other = 🍆 Команда /forest доступна лише в приватному чаті бота.

forest-not-registered = 🍆 Здається, ти ще не зареєстрований. Натисни /start у цьому чаті — потім зможеш піти до лісу.

forest-already-in = 🌲 Ти вже в лісі — зачекай на повернення. Бот надішле повідомлення, коли подорож завершиться.

forest-started = 🌲 { $nick } пішов до лісу на { NUMBER($cooldown_minutes, useGrouping: 0) } хвилин...

forest-started-fallback = 🌲 Ти пішов до лісу на { NUMBER($cooldown_minutes, useGrouping: 0) } хвилин...

forest-finished-header = 🌲 { $nick } повернувся з лісу!

forest-finished-length =
    📏 Довжина: +{ NUMBER($length_delta_cm, useGrouping: 0) } см (було { NUMBER($length_before_cm, useGrouping: 0) }, тепер { NUMBER($length_after_cm, useGrouping: 0) })

forest-finished-title-granted = 🎖 Отримано титул: Новачок

forest-rarity-common = звичайний
forest-rarity-rare = рідкісний
forest-rarity-epic = епічний

## /lang

lang-group = Команда `/lang` доступна лише в приваті. Зайди в ЛС.

lang-other = Команда `/lang` доступна лише звичайним користувачам.

lang-not-registered = Спочатку натисни /start, потім — /lang ru|en|pt|es|tr|id|fa|uk.

lang-usage = Використання: /lang ru|en|pt|es|tr|id|fa|uk.

lang-unsupported = Мову `{ $code }` не підтримано. Доступно: ru, en, pt, es, tr, id, fa, uk.

lang-set-uk = Мову інтерфейсу змінено на українську. Усі відповіді та фонові повідомлення тепер будуть українською.
