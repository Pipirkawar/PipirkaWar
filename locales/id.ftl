# Bot localization for "Pipirik Wars" — ID (Indonesian).
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

start-registered = 🍆 Selesai! Kamu sudah terdaftar di Pipirik Wars.

    Panjang awal adalah 2 cm, ketebalan level 1. Nama dan gelarmu akan muncul nanti — pada perjalanan pertamamu ke hutan.

start-already = 🍆 Kamu sudah terdaftar. Gunakan /profile untuk melihat kartumu.

start-group = 🍆 "Pipirik Wars" sudah ada di sini!

    1. Pertama, daftar di obrolan pribadi bot: buka DM dan tekan /start.
    2. Lalu tambahkan saya ke grup sebagai admin — ini mengubah obrolan menjadi klan.

start-other = 🍆 "Pipirik Wars" ada di sini. Perintah /start berfungsi di DM atau di grup.

start-queued = 🍆 Server penuh — kami menempatkanmu dalam antrean.

    Posisimu: #{ $position }.
    Begitu slot terbuka, kami akan mendaftarkanmu dan mengirim notifikasi.

start-registered-with-referral = 🍆 Selesai! Kamu sudah terdaftar di Pipirik Wars.

    Panjang awal adalah 2 cm + <b>bonus { $bonus_cm } cm karena datang melalui tautan referal</b>. Ketebalan level 1. Nama dan gelarmu akan muncul nanti — pada perjalanan pertamamu ke hutan.

## /profile

profile-group = 🍆 Perintah /profile hanya berfungsi di DM bot. Buka obrolan pribadi dan coba lagi.

profile-other = 🍆 Perintah /profile hanya berfungsi di DM bot.

profile-not-registered = 🍆 Sepertinya kamu belum terdaftar. Tekan /start di obrolan ini dan kartumu akan muncul.

profile-title-newbie = Pemula
profile-title-ataman = Ataman Bandit

profile-card =
    🏷 { $nick }

    📏 Panjang: { $length_cm } cm
    📐 Ketebalan: { $thickness_level }

    🎽 Peralatan: masih kosong

## /top

top-header = 🏆 <b>Top Pipirik</b>

top-empty = 🏆 Top masih kosong. Jadilah yang pertama — tekan /start!

top-entry = { $rank }. { $nick } — { $length_cm } cm

## /clantop

clantop-header = 🛡 <b>Top Klan</b>

clantop-empty = 🛡 Belum ada klan di top. Tambahkan bot ke grup — dan daftarkan klanmu!

clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } cm ({ $member_count } 👥)

## /forest

forest-group = 🍆 Perintah /forest hanya tersedia di obrolan pribadi bot. Buka DM dan coba lagi.

forest-other = 🍆 Perintah /forest hanya tersedia di obrolan pribadi bot.

forest-not-registered = 🍆 Sepertinya kamu belum terdaftar. Tekan /start di obrolan ini — lalu kamu bisa pergi ke hutan.

forest-already-in = 🌲 Kamu sudah ada di hutan — tunggu kepulanganmu. Bot akan mengirim pesan saat perjalanan berakhir.

forest-started = 🌲 { $nick } pergi ke hutan selama { NUMBER($cooldown_minutes, useGrouping: 0) } menit...

forest-started-fallback = 🌲 Kamu pergi ke hutan selama { NUMBER($cooldown_minutes, useGrouping: 0) } menit...

forest-finished-header = 🌲 { $nick } telah kembali dari hutan!

forest-finished-length =
    📏 Panjang: +{ NUMBER($length_delta_cm, useGrouping: 0) } cm (sebelumnya { NUMBER($length_before_cm, useGrouping: 0) }, sekarang { NUMBER($length_after_cm, useGrouping: 0) })

forest-finished-title-granted = 🎖 Gelar diperoleh: Pemula

forest-rarity-common = umum
forest-rarity-rare = langka
forest-rarity-epic = epik

## /lang

lang-group = Perintah `/lang` hanya untuk obrolan pribadi. Buka DM.

lang-other = Perintah `/lang` hanya untuk pengguna biasa.

lang-not-registered = Tekan /start dulu, lalu jalankan /lang ru|en|pt|es|tr|id|fa|uk.

lang-usage = Penggunaan: /lang ru|en|pt|es|tr|id|fa|uk.

lang-unsupported = Bahasa `{ $code }` tidak didukung. Tersedia: ru, en, pt, es, tr, id, fa, uk.

lang-set-id = Bahasa antarmuka diubah ke Bahasa Indonesia. Semua balasan dan pesan latar belakang sekarang akan dalam Bahasa Indonesia.
