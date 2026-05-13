# Bot localization for "Pipirik Wars" — FA (Persian / Farsi).
#
# Sprint 4.1-K (task 4.1.14): "Catalog of locales expanded to 8 (+pt/es/tr/id/fa/uk)".
# Contentful bootstrap: 30-50 high-traffic onboarding keys (`start-*`,
# `profile-*`, `top-*`, `clantop-*`, `forest-*`, `lang-*`). Остальные
# ~1550 ключей рендерятся через `FluentMessageBundle`-fallback на EN
# (см. `infrastructure/i18n/fluent_bundle.py`).
#
# RTL note: Persian is a right-to-left script. `FluentMessageBundle`
# initializes `FluentBundle(use_isolating=False)`, so no Unicode bidi
# isolation marks (U+2068/U+2069) are inserted around `{ $vars }` —
# values render exactly as written. Mixed numerals / HTML tags / `$nick`
# follow Telegram client's BiDi handling.
#
# Conventions: same as `en.ftl` (Fluent placeholders `{ $name }`,
# HTML `<b>`/`<i>` allowed, indentation = 4 spaces for continuation
# lines).

## /start

start-registered = 🍆 آماده شد! شما در Pipirik Wars ثبت‌نام شدید.

    طول اولیه ۲ سانتی‌متر، ضخامت سطح ۱ است. نام و عنوان شما بعدا — در اولین سفر شما به جنگل — ظاهر می‌شود.

start-already = 🍆 شما قبلاً ثبت‌نام کرده‌اید. برای دیدن کارت خود از /profile استفاده کنید.

start-group = 🍆 "Pipirik Wars" اینجاست!

    1. ابتدا در چت خصوصی ربات ثبت‌نام کنید: DM را باز کنید و /start را بزنید.
    2. سپس مرا به عنوان ادمین به یک گروه اضافه کنید — این چت را به یک قبیله تبدیل می‌کند.

start-other = 🍆 "Pipirik Wars" اینجاست. دستور /start در DM یا در یک گروه کار می‌کند.

start-queued = 🍆 سرورها پر هستند — شما را در صف قرار دادیم.

    موقعیت شما: #{ $position }.
    به‌محض اینکه جای خالی پیدا شود، شما را ثبت‌نام کرده و اطلاعیه ارسال می‌کنیم.

start-registered-with-referral = 🍆 آماده شد! شما در Pipirik Wars ثبت‌نام شدید.

    طول اولیه ۲ سانتی‌متر + <b>{ $bonus_cm } سانتی‌متر پاداش برای ورود از طریق پیوند معرفی</b>. ضخامت سطح ۱ است. نام و عنوان شما بعدا — در اولین سفر شما به جنگل — ظاهر می‌شود.

## /profile

profile-group = 🍆 دستور /profile فقط در DM ربات کار می‌کند. یک چت خصوصی باز کنید و دوباره تلاش کنید.

profile-other = 🍆 دستور /profile فقط در DM ربات کار می‌کند.

profile-not-registered = 🍆 به نظر می‌رسد هنوز ثبت‌نام نکرده‌اید. در این چت /start را بزنید تا کارت شما ظاهر شود.

profile-title-newbie = تازه‌کار
profile-title-ataman = آتامان راهزن

profile-card =
    🏷 { $nick }

    📏 طول: { $length_cm } سانتی‌متر
    📐 ضخامت: { $thickness_level }

    🎽 تجهیزات: فعلاً خالی

## /top

top-header = 🏆 <b>برترین‌های پیپیریک</b>

top-empty = 🏆 جدول برترین‌ها فعلاً خالی است. اولین نفر باشید — /start را بزنید!

top-entry = { $rank }. { $nick } — { $length_cm } سانتی‌متر

## /clantop

clantop-header = 🛡 <b>برترین قبیله‌ها</b>

clantop-empty = 🛡 هنوز قبیله‌ای در جدول برترین‌ها نیست. ربات را به یک گروه اضافه کنید — و قبیله خود را ثبت کنید!

clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } سانتی‌متر ({ $member_count } 👥)

## /forest

forest-group = 🍆 دستور /forest فقط در چت خصوصی ربات در دسترس است. DM را باز کنید و دوباره تلاش کنید.

forest-other = 🍆 دستور /forest فقط در چت خصوصی ربات در دسترس است.

forest-not-registered = 🍆 به نظر می‌رسد هنوز ثبت‌نام نکرده‌اید. در این چت /start را بزنید — سپس می‌توانید به جنگل بروید.

forest-already-in = 🌲 شما در حال حاضر در جنگل هستید — منتظر بازگشت خود باشید. ربات وقتی سفر تمام شد پیامی ارسال می‌کند.

forest-started = 🌲 { $nick } برای { NUMBER($cooldown_minutes, useGrouping: 0) } دقیقه به جنگل رفت...

forest-started-fallback = 🌲 شما برای { NUMBER($cooldown_minutes, useGrouping: 0) } دقیقه به جنگل رفتید...

forest-finished-header = 🌲 { $nick } از جنگل بازگشت!

forest-finished-length =
    📏 طول: +{ NUMBER($length_delta_cm, useGrouping: 0) } سانتی‌متر (قبلاً { NUMBER($length_before_cm, useGrouping: 0) }، اکنون { NUMBER($length_after_cm, useGrouping: 0) })

forest-finished-title-granted = 🎖 عنوان کسب شد: تازه‌کار

forest-rarity-common = عادی
forest-rarity-rare = نادر
forest-rarity-epic = حماسی

## /lang

lang-group = دستور `/lang` فقط برای چت خصوصی است. DM را باز کنید.

lang-other = دستور `/lang` فقط برای کاربران معمولی است.

lang-not-registered = ابتدا /start را بزنید، سپس /lang ru|en|pt|es|tr|id|fa|uk را اجرا کنید.

lang-usage = طرز استفاده: /lang ru|en|pt|es|tr|id|fa|uk.

lang-unsupported = زبان `{ $code }` پشتیبانی نمی‌شود. موجود: ru, en, pt, es, tr, id, fa, uk.

lang-set-fa = زبان رابط به فارسی تغییر یافت. تمام پاسخ‌ها و پیام‌های پس‌زمینه اکنون به فارسی خواهد بود.
