# Bot localization for "Pipirik Wars" — TR (Turkish).
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

start-registered = 🍆 Tamamdır! Pipirik Wars'a kaydoldun.

    Başlangıç uzunluğu 2 cm, kalınlık seviye 1. Adın ve unvanın daha sonra görünecek — ormana ilk gidişinde.

start-already = 🍆 Zaten kayıtlısın. Kartını görmek için /profile komutunu kullan.

start-group = 🍆 "Pipirik Wars" burada!

    1. Önce botun özel sohbetinde kaydol: DM'i aç ve /start'a bas.
    2. Sonra beni bir gruba yönetici olarak ekle — bu, sohbeti bir klana dönüştürür.

start-other = 🍆 "Pipirik Wars" burada. /start komutu DM'de veya grupta çalışır.

start-queued = 🍆 Sunucular dolu — seni sıraya aldık.

    Sıradaki konumun: #{ $position }.
    Bir yer açılır açılmaz seni kaydedip bildirim göndereceğiz.

start-registered-with-referral = 🍆 Tamamdır! Pipirik Wars'a kaydoldun.

    Başlangıç uzunluğu 2 cm + <b>davet bağlantısıyla geldiğin için { $bonus_cm } cm bonus</b>. Kalınlık seviye 1. Adın ve unvanın daha sonra görünecek — ormana ilk gidişinde.

## /profile

profile-group = 🍆 /profile komutu yalnızca botun DM'inde çalışır. Özel sohbeti aç ve tekrar dene.

profile-other = 🍆 /profile komutu yalnızca botun DM'inde çalışır.

profile-not-registered = 🍆 Henüz kayıtlı görünmüyorsun. Bu sohbette /start'a bas ve kartın görünecek.

profile-title-newbie = Acemi
profile-title-ataman = Haydut Atamanı

profile-card =
    🏷 { $nick }

    📏 Uzunluk: { $length_cm } cm
    📐 Kalınlık: { $thickness_level }

    🎽 Donanım: şimdilik boş

## /top

top-header = 🏆 <b>Pipirik Top</b>

top-empty = 🏆 Top şimdilik boş. İlk sen ol — /start'a bas!

top-entry = { $rank }. { $nick } — { $length_cm } cm

## /clantop

clantop-header = 🛡 <b>Klan Top</b>

clantop-empty = 🛡 Top'ta henüz klan yok. Botu bir gruba ekle — ve klanını kaydet!

clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } cm ({ $member_count } 👥)

## /forest

forest-group = 🍆 /forest komutu yalnızca botun özel sohbetinde kullanılabilir. DM'i aç ve tekrar dene.

forest-other = 🍆 /forest komutu yalnızca botun özel sohbetinde kullanılabilir.

forest-not-registered = 🍆 Henüz kayıtlı görünmüyorsun. Bu sohbette /start'a bas — sonra ormana gidebilirsin.

forest-already-in = 🌲 Zaten ormandasın — dönmeni bekle. Yolculuk bittiğinde bot bir mesaj gönderecek.

forest-started = 🌲 { $nick } { NUMBER($cooldown_minutes, useGrouping: 0) } dakikalığına ormana gitti...

forest-started-fallback = 🌲 { NUMBER($cooldown_minutes, useGrouping: 0) } dakikalığına ormana gittin...

forest-finished-header = 🌲 { $nick } ormandan döndü!

forest-finished-length =
    📏 Uzunluk: +{ NUMBER($length_delta_cm, useGrouping: 0) } cm ({ NUMBER($length_before_cm, useGrouping: 0) } idi, şimdi { NUMBER($length_after_cm, useGrouping: 0) })

forest-finished-title-granted = 🎖 Unvan kazanıldı: Acemi

forest-rarity-common = sıradan
forest-rarity-rare = nadir
forest-rarity-epic = epik

## /lang

lang-group = `/lang` komutu yalnızca özel sohbet içindir. DM'i aç.

lang-other = `/lang` komutu yalnızca normal kullanıcılar içindir.

lang-not-registered = Önce /start'a bas, sonra /lang ru|en|pt|es|tr|id|fa|uk|ar komutunu çalıştır.

lang-usage = Kullanım: /lang ru|en|pt|es|tr|id|fa|uk|ar.

lang-unsupported = `{ $code }` dili desteklenmiyor. Mevcut: ru, en, pt, es, tr, id, fa, uk, ar.

lang-set-tr = Arayüz dili Türkçe olarak değiştirildi. Tüm yanıtlar ve arka plan mesajları artık Türkçe olacak.
lang-set-ar = تم تغيير لغة الواجهة إلى العربية. جميع الردود والرسائل في الخلفية ستكون الآن باللغة العربية.
