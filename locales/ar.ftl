# Bot localization for "Pipirik Wars" — AR (Arabic).
#
# Sprint 4.5 (локализация): full Arabic translation of all keys from en.ftl.
# Arabic is a right-to-left script. `FluentMessageBundle` initializes
# `FluentBundle(use_isolating=False)`, so no Unicode bidi isolation marks
# (U+2068/U+2069) are inserted around `{ $vars }` — values render exactly
# as written. Mixed numerals / HTML tags / `$nick` follow Telegram client's
# BiDi handling.
#
# Conventions: same as `en.ftl` (Fluent placeholders `{ $name }`,
# HTML `<b>`/`<i>` allowed, indentation = 4 spaces for continuation
# lines).

## /start (Sprint 1.1.C → 1.1.D → 1.2.4 DAU Gate)

start-registered = 🍆 تم! لقد سُجّلت في حروب البيبيريك.

    الطول الابتدائي ٢ سم، السُمك مستوى ١. اسمك ولقبك سيظهران لاحقاً — في أول رحلة لك إلى الغابة.

start-already = 🍆 أنت مسجّل بالفعل. استخدم /profile لعرض بطاقتك.

start-group = 🍆 "حروب البيبيريك" هنا!

    1. أولاً، سجّل في المحادثة الخاصة مع البوت: افتح رسالة مباشرة واضغط /start.
    2. ثم أضفني كمشرف في مجموعة — وستتحوّل المحادثة إلى قبيلة.

start-other = 🍆 "حروب البيبيريك" هنا. أمر /start يعمل في الرسائل الخاصة أو في مجموعة.

start-queued = 🍆 الخوادم ممتلئة — وضعناك في قائمة الانتظار.

    ترتيبك: #{ $position }.
    بمجرد أن يتوفر مكان، سنسجّلك ونرسل لك إشعاراً.

# Referral arrival (Sprint 2.4.D, GDD §13.1).
start-registered-with-referral = 🍆 تم! لقد سُجّلت في حروب البيبيريك.

    الطول الابتدائي ٢ سم + <b>{ $bonus_cm } سم مكافأة للوصول عبر رابط إحالة</b>. السُمك مستوى ١. اسمك ولقبك سيظهران لاحقاً — في أول رحلة لك إلى الغابة.

## /profile (Sprint 1.1.E → 1.5.C)

profile-group = 🍆 أمر /profile يعمل فقط في المحادثة الخاصة مع البوت. افتح رسالة خاصة وحاول مرة أخرى.

profile-other = 🍆 أمر /profile يعمل فقط في المحادثة الخاصة مع البوت.

profile-not-registered = 🍆 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة وستظهر بطاقتك.

profile-title-newbie = مبتدئ
profile-title-ataman = أتامان قاطع طريق

profile-card =
    🏷 { $nick }

    📏 الطول: { $length_cm } سم
    📐 السُمك: { $thickness_level }

    🎽 التجهيزات: فارغة حالياً

## /top (Sprint 1.4.C → 1.5.C)

top-header = 🏆 <b>أفضل البيبيريك</b>

top-empty = 🏆 الترتيب فارغ حالياً. كن الأول — اضغط /start!

top-entry = { $rank }. { $nick } — { $length_cm } سم

## /clantop (Sprint 2.2.A)

clantop-header = 🛡 <b>أفضل القبائل</b>

clantop-empty = 🛡 لا قبائل في الترتيب بعد. أضف البوت إلى مجموعة — وسجّل قبيلتك!

clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } سم ({ $member_count } 👥)

## /oracle (Sprint 1.4.B → 1.5.D, extended in 3.6-B; GDD §11, §11.1)

oracle-group = 🔮 أمر /oracle يعمل فقط في المحادثة الخاصة مع البوت. افتح رسالة خاصة وحاول مرة أخرى.

oracle-other = 🔮 أمر /oracle يعمل فقط في المحادثة الخاصة مع البوت.

oracle-not-registered = 🔮 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة وسيسمعك العرّاف.

oracle-success-prediction =
    🔮 تنبؤ اليوم:
    { $prediction }

oracle-base-line = 📏 +{ NUMBER($base_cm, useGrouping: 0) } سم — أساسي

oracle-tribe-bonus-line = 🛡 +{ NUMBER($tribe_bonus_cm, useGrouping: 0) } سم — مكافأة القبيلة ({ NUMBER($n_active_tribes, useGrouping: 0) } { $n_active_tribes ->
        [one] قبيلة
       *[other] قبائل
    })

oracle-total-line = ✨ المجموع: +{ NUMBER($total_cm, useGrouping: 0) } سم

oracle-new-length-line = طولك الآن: { NUMBER($new_length_cm, useGrouping: 0) } سم

oracle-already-used =
    🔮 لقد زرت العرّاف اليوم بالفعل.
    عُد بعد { NUMBER($hours, useGrouping: 0) } ساعة { $minutes } دقيقة (00:00 بتوقيت موسكو).

## /upgrade (Sprint 1.4.A → 1.5.D)

upgrade-group = 🍆 أمر /upgrade يعمل فقط في المحادثة الخاصة مع البوت. افتح رسالة خاصة وحاول مرة أخرى.

upgrade-other = 🍆 أمر /upgrade يعمل فقط في المحادثة الخاصة مع البوت.

upgrade-not-registered = 🍆 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من الترقية.

upgrade-proposal =
    📐 ترقية السُمك
    المستوى الحالي: { NUMBER($current_thickness, useGrouping: 0) }
    المستوى المستهدف: { NUMBER($next_thickness, useGrouping: 0) }
    التكلفة: { NUMBER($cost_cm, useGrouping: 0) } سم
    لديك: { NUMBER($current_length_cm, useGrouping: 0) } سم
    المتبقي: { NUMBER($remaining_cm, useGrouping: 0) } سم (الحد الأدنى بقاعدة الـ 20 سم: { NUMBER($min_after_spend_cm, useGrouping: 0) })

upgrade-success =
    ✅ تمت ترقية السُمك إلى { NUMBER($new_thickness, useGrouping: 0) }!
    📏 المُنفق: { NUMBER($cost_cm, useGrouping: 0) } سم
    المتبقي: { NUMBER($new_length_cm, useGrouping: 0) } سم

upgrade-insufficient =
    ❌ لا يكفي الطول للترقية إلى { NUMBER($next_thickness, useGrouping: 0) }.
    التكلفة: { NUMBER($cost_cm, useGrouping: 0) } سم
    لديك: { NUMBER($current_length_cm, useGrouping: 0) } سم
    الحد الأدنى للمتبقي: { NUMBER($min_after_spend_cm, useGrouping: 0) } سم
    ينقصك: { NUMBER($deficit_cm, useGrouping: 0) } سم

upgrade-cancelled = تم إلغاء الترقية.

upgrade-race = ⚠️ تغيّرت تكلفة الترقية — افتح /upgrade مرة أخرى لرؤية السعر الحالي.

upgrade-button-confirm = تأكيد ({ NUMBER($cost_cm, useGrouping: 0) } سم)

upgrade-button-cancel = إلغاء

upgrade-toast-upgraded = تمت ترقية السُمك.

upgrade-toast-cancelled = تم إلغاء الترقية.

upgrade-toast-player-not-found = اضغط /start أولاً.

upgrade-toast-insufficient = الطول غير كافٍ.

upgrade-toast-race = تغيّرت التكلفة.

upgrade-anticheat-blocked = الترقية مجمّدة مؤقتاً. التحقق من مكافحة الغش فعّال حتى { $banned-until }.

upgrade-toast-anticheat-blocked = التحقق من مكافحة الغش فعّال.

upgrade-insufficient-short =
    ❌ الطول غير كافٍ.
    التكلفة: { NUMBER($cost_cm, useGrouping: 0) } سم
    لديك: { NUMBER($current_length_cm, useGrouping: 0) } سم
    الحد الأدنى للمتبقي: { NUMBER($min_after_spend_cm, useGrouping: 0) } سم
    ينقصك: { NUMBER($deficit_cm, useGrouping: 0) } سم

## /forest (Sprint 1.3.D → 1.5.E)

forest-group = 🍆 أمر /forest متاح فقط في المحادثة الخاصة مع البوت. افتح الرسائل الخاصة وحاول مرة أخرى.

forest-other = 🍆 أمر /forest متاح فقط في المحادثة الخاصة مع البوت.

forest-not-registered = 🍆 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من الذهاب إلى الغابة.

forest-already-in = 🌲 أنت بالفعل في الغابة — انتظر عودتك. سيرسل البوت رسالة عند انتهاء الرحلة.

forest-started = 🌲 { $nick } ذهب إلى الغابة لمدة { NUMBER($cooldown_minutes, useGrouping: 0) } دقيقة...

forest-started-fallback = 🌲 ذهبت إلى الغابة لمدة { NUMBER($cooldown_minutes, useGrouping: 0) } دقيقة...

forest-finished-header = 🌲 { $nick } عاد من الغابة!
forest-finished-length =
    📏 الطول: +{ NUMBER($length_delta_cm, useGrouping: 0) } سم (كان { NUMBER($length_before_cm, useGrouping: 0) }، الآن { NUMBER($length_after_cm, useGrouping: 0) })

forest-flavour-delta = +{ NUMBER($length_delta_cm, useGrouping: 0) } سم

forest-finished-title-granted = 🎖 حصلت على لقب: مبتدئ

forest-finished-item-found = 🎩 وجدت: { $item_name } [{ $rarity }]

forest-finished-name-granted = 🪪 حصلت على اسم: { $name }

forest-finished-name-found = 🪪 اسم جديد: { $name }

forest-rarity-common = عادي
forest-rarity-rare = نادر
forest-rarity-epic = ملحمي

forest-button-equip = تجهيز
forest-button-drop-item = إسقاط
forest-button-replace-name = استبدال
forest-button-drop-name = إسقاط

forest-toast-name-applied = تم استبدال الاسم.
forest-toast-name-already-applied = الاسم مُطبّق بالفعل.
forest-toast-name-dropped = تم إسقاط الاسم.
forest-toast-item-dropped = تم إسقاط العنصر.
forest-toast-item-equipped-placeholder = التجهيزات قادمة لاحقاً — العنصر في مخزونك حالياً.
forest-toast-foreign-button = هذا الزر ليس لك.
forest-toast-run-not-found = هذه الرحلة لم تعد نشطة.
forest-toast-drop-mismatch = الزر قديم.
forest-toast-player-not-found = اضغط /start أولاً.

# ----------------------------- /lang -----------------------------

lang-group = أمر `/lang` متاح فقط في المحادثة الخاصة. افتح الرسائل الخاصة.

lang-other = أمر `/lang` متاح فقط للمستخدمين العاديين.

lang-not-registered = اضغط /start أولاً، ثم شغّل /lang ru|en|pt|es|tr|id|fa|uk|ar.

lang-usage = الاستخدام: /lang ru|en|pt|es|tr|id|fa|uk|ar.

lang-unsupported = اللغة `{ $code }` غير مدعومة. المتاح: ru, en, pt, es, tr, id, fa, uk, ar.

lang-set-ru = Язык интерфейса: русский. Все ответы и фоновые сообщения теперь на русском.
lang-set-en = Interface language switched to English. All replies and background messages will be in English.
lang-set-pt = Idioma da interface alterado para português. Todas as respostas e mensagens em segundo plano agora serão em português.
lang-set-es = Idioma de la interfaz cambiado a español. Todas las respuestas y mensajes en segundo plano ahora estarán en español.
lang-set-tr = Arayüz dili Türkçe olarak değiştirildi. Tüm yanıtlar ve arka plan mesajları artık Türkçe olacak.
lang-set-id = Bahasa antarmuka diubah ke Bahasa Indonesia. Semua balasan dan pesan latar belakang sekarang akan dalam Bahasa Indonesia.
lang-set-fa = زبان رابط به فارسی تغییر یافت. تمام پاسخ‌ها و پیام‌های پس‌زمینه اکنون به فارسی خواهد بود.
lang-set-uk = Мову інтерфейсу змінено на українську. Усі відповіді та фонові повідомлення тепер будуть українською.
lang-set-ar = تم تغيير لغة الواجهة إلى العربية. جميع الردود والرسائل في الخلفية ستكون الآن باللغة العربية.


# Anti-cheat hardcap (Sprint 1.6.D, GDD §3.3).
anticheat-soft-ban-active = التحقق من مكافحة الغش فعّال حتى { $banned-until }. نمو الطول مجمّد مؤقتاً.

anticheat-cap-clamped-daily = اقتربت من الحد اليومي للنمو. تم تطبيق { NUMBER($applied, useGrouping: 0) } سم من أصل { NUMBER($requested, useGrouping: 0) } سم.

anticheat-cap-clamped-weekly = اقتربت من الحد الأسبوعي للنمو. تم تطبيق { NUMBER($applied, useGrouping: 0) } سم من أصل { NUMBER($requested, useGrouping: 0) } سم.


# /anticheat_unban (Sprint 1.6.G, GDD §3.3)
anticheat-unban-usage = ⚠️ الاستخدام: `/anticheat_unban <tg_id> <reason>`. السبب مطلوب.

anticheat-unban-not-authorized = ❌ لا تملك صلاحية لهذا الأمر. رفع حظر مكافحة الغش متاح فقط لمشرف أعلى نشط.

anticheat-unban-player-not-found = ❌ اللاعب بمعرّف tg_id { $tg_id } غير مسجّل.

anticheat-unban-not-banned = ℹ️ اللاعب بمعرّف tg_id { $tg_id } ليس عليه حظر مكافحة غش نشط. لا حاجة لاتخاذ إجراء.

anticheat-unban-success = ✅ تم رفع حظر مكافحة الغش (tg_id { $tg_id }، كان محظوراً حتى { $banned-until-before }). السبب: { $reason }.


# ──────────────────────────────────────────────────────────────────────────
# 1×1 PvP duel (Sprint 2.1.E, GDD §7.1).
# ──────────────────────────────────────────────────────────────────────────

duel-private-needs-global = 🍆 لتحدّي شخص ما، ردّ بأمر /duel على رسالته في محادثة جماعية. أو انتظر — أمر `/duel` الخاص بك قد أُرسل بالفعل إلى الساحة العامة.

duel-usage = 🍆 الاستخدام: ردّ بأمر `/duel` على رسالة خصمك. الوضع الافتراضي هو محادثة → عام. للمحادثة فقط — `/duel chat`. في الرسائل الخاصة، `/duel` بدون وسائط يضعك في الساحة العامة.

duel-not-registered = 🍆 لم تسجّل بعد. اضغط /start أولاً.

duel-target-not-registered = 🍆 الخصم غير مسجّل بعد — اطلب منه تشغيل /start في البوت.

duel-target-is-bot = 🍆 يمكنك تحدّي لاعب حقيقي فقط، ليس بوت.

duel-self-challenge = 🍆 تتحدّى نفسك؟ ابحث عن خصم حقيقي.

duel-challenge-chat = ⚔️ { $challenger } يتحدّى { $challenged } في مبارزة (المحادثة فقط)! هل تقبل؟

duel-challenge-chat-then-global = ⚔️ { $challenger } يتحدّى { $challenged } في مبارزة! إن لم يُقبل التحدي خلال 3 دقائق، سينتقل إلى الساحة العامة.

duel-challenge-global = ⚔️ { $challenger }، تم إرسال تحدّيك إلى الساحة العامة — في انتظار حتى { NUMBER($ttl_minutes, useGrouping: 0) } دقيقة.

duel-global-enqueued = ⚔️ تم إرسال التحدي إلى الساحة العامة. في انتظار شخص يستخدم /duel_global. ينتهي خلال { NUMBER($ttl_minutes, useGrouping: 0) } دقيقة — ألغِ يدوياً بأمر /cancel_duel { $duel_id }.

duel-global-matched = ⚔️ تم التطابق مع { $challenger }! بدأت المعركة — تابع مطالبات الجولة في المحادثة الخاصة.

duel-global-empty = 🪂 الساحة العامة فارغة. حاول لاحقاً أو أرسل تحدياً عبر /duel.

duel-global-only-in-private = 🤖 أمر `/duel_global` يعمل فقط في المحادثة الخاصة — لا يجب كشف الخصوم علناً.

duel-chat-accepted = ✅ { $challenged } قبل تحدّي { $challenger }. المعركة جارية (خاصة).

duel-button-accept = قبول
duel-button-reject = رفض
duel-button-attack-high = هجوم: ⬆ أعلى
duel-button-attack-mid = هجوم: ➡ وسط
duel-button-attack-low = هجوم: ⬇ أسفل
duel-button-block-high = دفاع: ⬆ أعلى
duel-button-block-mid = دفاع: ➡ وسط
duel-button-block-low = دفاع: ⬇ أسفل

duel-round-attack-prompt = 🥊 الجولة { NUMBER($round_num, useGrouping: 0) } من 3. أين تضرب؟

duel-round-block-prompt = 🛡 الجولة { NUMBER($round_num, useGrouping: 0) } من 3. الهجوم: { $attack }. ماذا تحجب؟

duel-round-waiting = ⏳ الجولة { NUMBER($round_num, useGrouping: 0) } — تم قبول حركتك. في انتظار الخصم…

duel-result-victory = 🏆 انتصار! +{ NUMBER($delta_cm, useGrouping: 0) } سم. طولك الآن { NUMBER($new_length_cm, useGrouping: 0) } سم.
duel-result-defeat = 💀 هزيمة. { NUMBER($delta_cm, useGrouping: 0) } سم. طولك الآن { NUMBER($new_length_cm, useGrouping: 0) } سم.
duel-result-draw = 🤝 تعادل. الطول لم يتغيّر — { NUMBER($length_cm, useGrouping: 0) } سم.

duel-result-card-victory = ⚔️ انتهت المبارزة: { $winner } سحق { $loser } (+{ NUMBER($delta_cm, useGrouping: 0) } سم).
duel-result-card-draw = ⚔️ انتهت المبارزة بالتعادل: { $p1 } و { $p2 } تبادلا ضربات بلا ضرر.
duel-share-button = 📢 مشاركة

duel-cancelled = ❌ ألغى { $challenger } التحدي.
duel-cancel-usage = الاستخدام: `/cancel_duel <duel_id>`. المعرّف موجود في بطاقة التحدي.

duel-toast-accepted = تم قبول التحدي!
duel-toast-rejected = شكراً، لست مهتماً.
duel-toast-cancelled = تم إلغاء التحدي.
duel-toast-not-found = هذه المبارزة لم تعد نشطة.
duel-toast-not-participant = هذه المبارزة ليست لك.
duel-toast-foreign-button = هذا الزر ليس لك.
duel-toast-invalid-state = المبارزة لم تعد في تلك المرحلة.
duel-toast-already-submitted = لقد تحرّكت بالفعل في هذه الجولة.
duel-toast-outdated = الزر قديم.

duel-requirements-not-met = 📏 المبارزات تتطلب طولاً ≥ { NUMBER($min_length_cm, useGrouping: 0) } سم وسُمكاً ≥ { NUMBER($min_thickness_level, useGrouping: 0) }.

duel-anticheat-blocked = التحقق من مكافحة الغش فعّال حتى { $banned-until }. المبارزات مجمّدة مؤقتاً.

duel-lock-already-held = 🔒 أنت مشغول (مثلاً في /forest). أنهِ النشاط الحالي أولاً.

# === Mass PvP clan×clan (Sprint 2.2.F, GDD §7.2) ===

pvp-mass-needs-group-chat = ⚔️أمر `/clan_attack` يعمل فقط في محادثات القبائل الجماعية. شغّله من محادثة القبيلة التي تريد مهاجمتها.
pvp-mass-not-registered = 🍆سجّل أولاً عبر `/start` في الرسائل الخاصة مع البوت.
pvp-mass-attacker-not-found = ❌هذه المحادثة غير مرتبطة بقبيلة مسجّلة.
pvp-mass-attacker-not-member = 🚫فقط أعضاء هذه القبيلة يمكنهم مهاجمة قبائل أخرى.
pvp-mass-target-not-found = ❌محادثة الهدف غير موجودة أو غير مرتبطة بقبيلة مسجّلة.
pvp-mass-target-needed = الاستخدام: `/clan_attack <chat_id>` أو ردّ على رسالة من محادثة القبيلة المدافعة.
pvp-mass-self-attack = 🤝لا يمكنك مهاجمة قبيلتك.
pvp-mass-clan-frozen = 🧊إحدى القبائل مجمّدة — المبارزة الجماعية مستحيلة.
pvp-mass-cooldown = ⏳فترة التهدئة لا تزال سارية: الهجوم التالي ممكن بعد { NUMBER($cooldown_hours, useGrouping: 0) } ساعة.
pvp-mass-no-participants = 🪶أحد الطرفين ليس لديه مشاركون يستوفون المتطلبات (طول ≥ { NUMBER($min_length_cm, useGrouping: 0) } سم، سُمك ≥ { NUMBER($min_thickness_level, useGrouping: 0) }).
pvp-mass-lock-already-held = 🔒بعض المشاركين مشغولون بنشاط آخر. حاول مرة أخرى بعد دقيقة.

pvp-mass-started = ⚔️معركة القبائل: <b>{ $attacker }</b> × <b>{ $defender }</b>! التشكيلة: { NUMBER($attacker_size, useGrouping: 0) } × { NUMBER($defender_size, useGrouping: 0) }. جميع المشاركين تلقّوا التعليمات في الرسائل الخاصة. مؤقّت الحركة — { NUMBER($timer_seconds, useGrouping: 0) } ثانية.

pvp-mass-prompt-attack = ⚔️معركة قبيلة × قبيلة. أين تضرب؟
pvp-mass-prompt-block = 🛡تم اختيار الهجوم: { $attack }. ماذا تحجب؟
pvp-mass-waiting = ⏳تم قبول حركتك. في انتظار الآخرين…

pvp-mass-result-victory = 🏆انتصار! قبيلة <b>{ $clan }</b> فازت وأخذت { NUMBER($total_dealt, useGrouping: 0) } سم. التغيير لديك: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } سم.
pvp-mass-result-defeat = 💀هزيمة. قبيلة <b>{ $clan }</b> خسرت، { NUMBER($total_lost, useGrouping: 0) } سم ذهبت للعدو. التغيير لديك: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } سم.
pvp-mass-result-draw = 🤝تعادل. لم يفز أحد بالأكثر. التغيير لديك: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } سم.

pvp-mass-result-chat-victory = 🏆انتهت معركة القبائل! قبيلة <b>{ $clan }</b> فازت وأخذت { NUMBER($total_dealt, useGrouping: 0) } سم.
pvp-mass-result-chat-draw = 🤝انتهت معركة القبائل بالتعادل ({ NUMBER($total_dealt, useGrouping: 0) } سم لكل طرف).

pvp-mass-button-attack-high = ⬆️ الرأس
pvp-mass-button-attack-mid = ↔ الجسم
pvp-mass-button-attack-low = ⬇️ الأرجل
pvp-mass-button-block-high = 🛡⬆ الرأس
pvp-mass-button-block-mid = 🛡↔ الجسم
pvp-mass-button-block-low = 🛡⬇ الأرجل

pvp-mass-toast-not-found = هذه المعركة لم تعد نشطة.
pvp-mass-toast-not-participant = لست مشاركاً في هذه المعركة.
pvp-mass-toast-foreign-button = هذا الزر ليس لك.
pvp-mass-toast-invalid-state = المعركة انتهت بالفعل.
pvp-mass-toast-already-submitted = لقد قمت بحركتك بالفعل.
pvp-mass-toast-outdated = هذا الزر قديم.
pvp-mass-toast-attack-selected = تم اختيار الهجوم. الآن اختر الدفاع.
pvp-mass-toast-move-accepted = تم قبول الحركة!

## /clan_history (Sprint 2.2.G)

clan-history-needs-group-chat = 📜 أمر `/clan_history` يعمل فقط في محادثة قبيلة جماعية.
clan-history-not-registered = 📜 هذه المحادثة غير مسجّلة كقبيلة. استخدم /start للتسجيل.
clan-history-header = 📜 <b>سجل هجمات القبيلة</b> ({ $clan_title })
clan-history-empty = 📜 قبيلة <b>{ $clan_title }</b> ليس لديها معارك جماعية مكتملة بعد.
clan-history-entry-victory = { $idx }. ⚔ { $opponent_clan_title } — 🏆 انتصار +{ NUMBER($our_delta_cm, useGrouping: 0) } سم ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }، { $when })
clan-history-entry-defeat = { $idx }. ⚔ { $opponent_clan_title } — 💀 هزيمة { NUMBER($our_delta_cm, useGrouping: 0) } سم ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }، { $when })
clan-history-entry-draw = { $idx }. ⚔ { $opponent_clan_title } — 🤝 تعادل ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }، { $when })
clan-history-entry-cancelled = { $idx }. ⚔ { $opponent_clan_title } — ⛔ ملغاة ({ $when })

## /clan_head (Sprint 2.3.E)

clan-head-needs-group-chat = 👑 أمر /clan_head يعمل فقط في محادثة قبيلة جماعية.
clan-head-not-registered = 👑 هذه المحادثة غير مرتبطة بقبيلة مسجّلة. استخدم /start للتسجيل.
clan-head-frozen-clan = 👑 القبيلة مجمّدة مؤقتاً. لا يمكن تعيين رئيس.
clan-head-not-enough-active = 👑 عدد الأعضاء النشطين في القبيلة خلال آخر 7 أيام قليل جداً (مطلوب على الأقل { NUMBER($required, useGrouping: 0) }، نشطون: { NUMBER($active_count, useGrouping: 0) }).
clan-head-success = 👑 <b>رئيس القبيلة لهذا اليوم</b> — { $head_display_name }!
  +{ NUMBER($bonus_cm, useGrouping: 0) } سم للطول (الآن { NUMBER($new_length_cm, useGrouping: 0) } سم).

  💬 <i>{ $quote_text }</i>
clan-head-already-assigned = 👑 رئيس القبيلة لهذا اليوم معيّن بالفعل — { $head_display_name } (+{ NUMBER($bonus_cm, useGrouping: 0) } سم).

  💬 <i>{ $quote_text }</i>

## Referral-share button (Sprint 2.4.D-b, GDD §13.2)
referral-share-button = 🔗 مشاركة

referral-share-duel-victory = ⚔️ حروب البيبيريك — نتيجة المعركة!
    { $winner } 🏆 فاز!
    سرق { NUMBER($delta_cm, useGrouping: 0) } سم من { $loser }!
    📏 الطول الجديد: { NUMBER($winner_length_cm, useGrouping: 0) } سم

    🎮 العب أنت أيضاً → { $deeplink }

referral-share-duel-draw = ⚔️ حروب البيبيريك — نتيجة المعركة!
    تعادل: { $p1 } و { $p2 } افترقا بشروط متساوية.

    🎮 العب أنت أيضاً → { $deeplink }

referral-share-forest = 🌲 حروب البيبيريك — رحلة الغابة!
    { $player } عاد من الغابة بـ { NUMBER($delta_cm, useGrouping: 0) } سم!
    📏 الطول الجديد: { NUMBER($length_cm, useGrouping: 0) } سم

    🎮 العب أنت أيضاً → { $deeplink }


## Weekly clan referral summary (Sprint 2.4.E, GDD §13.3)
weekly-referral-summary-title = 📊 التقرير الأسبوعي — قبيلة "{ $clan_title }"
weekly-referral-summary-total = 👥 الإحالات الجديدة هذا الأسبوع: { NUMBER($total, useGrouping: 0) }
weekly-referral-summary-line = 🏆 { NUMBER($rank, useGrouping: 0) }. { $referrer_display_name } — جلب { NUMBER($count, useGrouping: 0) }
weekly-referral-summary-footer = ادعُ أصدقاءك — الجميع ينمو معاً!


## Admin — support commands (Sprint 2.5-B, GDD §18.6.5)

admin-find-player-usage = ⚠️ الاستخدام: <code>/find_player &lt;tg_id | @username | substring&gt;</code>. الاستعلام مطلوب.
admin-find-player-not-authorized = ❌ فقط المشرفون النشطون يمكنهم البحث عن اللاعبين.
admin-find-player-empty = 🔍 لم يُعثر على لاعبين للاستعلام <code>{ $query }</code>.
admin-find-player-header = 🔍 عُثر على { $count } لاعب(ين) للاستعلام <code>{ $query }</code>.
admin-find-player-row = • <code>{ $tg_id }</code> · @{ $username } · «{ $name }» · { $title } · L{ $length_cm }/T{ $thickness_level } · { $status }

admin-player-usage = ⚠️ الاستخدام: <code>/player &lt;tg_id&gt;</code>. الوسيط مطلوب.
admin-player-not-authorized = ❌ فقط المشرفون النشطون يمكنهم عرض بطاقات اللاعبين.
admin-player-bad-id = ⚠️ <code>{ $value }</code> ليس معرّف tg_id صالح (عدد صحيح). حاول مرة أخرى.
admin-player-not-found = 🔍 لا يوجد لاعب بمعرّف tg_id <code>{ $tg_id }</code>.
admin-player-card-summary = • <code>{ $tg_id }</code> · @{ $username } · «{ $name }» · { $title } · L{ $length_cm }/T{ $thickness_level } · { $status }
admin-player-card-clan = 🏰 القبيلة: <code>{ $title }</code> ({ $clan_status }) · الدور { $role } · منذ { $joined_at }
admin-player-card-no-clan = 🏰 القبيلة: —
admin-player-card-forest-active = 🌲 رحلة غابة نشطة #{ $run_id }: من { $started_at } إلى { $ends_at }.
admin-player-card-no-forest = 🌲 لا رحلة غابة نشطة.
admin-player-card-anticheat = 🛡️ حظر مكافحة الغش حتى: { $until }.
admin-player-card-no-anticheat = 🛡️ حظر مكافحة الغش: غير فعّال.

admin-freeze-usage = ⚠️ الاستخدام: <code>/freeze &lt;tg_id&gt; [reason]</code>.
admin-freeze-not-authorized = ❌ فقط المشرفون النشطون يمكنهم تجميد اللاعبين.
admin-freeze-bad-id = ⚠️ <code>{ $value }</code> ليس معرّف tg_id صالح (عدد صحيح).
admin-freeze-not-found = 🔍 لا يوجد لاعب بمعرّف tg_id <code>{ $tg_id }</code>.
admin-freeze-already = ❄️ اللاعب <code>{ $tg_id }</code> مجمّد بالفعل.
admin-freeze-ok = 🥶 تم تجميد اللاعب <code>{ $tg_id }</code>.{ $reason_suffix }
admin-freeze-reason-suffix = السبب: { $reason }.

admin-unfreeze-usage = ⚠️ الاستخدام: <code>/unfreeze &lt;tg_id&gt; [reason]</code>.
admin-unfreeze-not-authorized = ❌ فقط المشرفون النشطون يمكنهم إلغاء تجميد اللاعبين.
admin-unfreeze-bad-id = ⚠️ <code>{ $value }</code> ليس معرّف tg_id صالح (عدد صحيح).
admin-unfreeze-not-found = 🔍 لا يوجد لاعب بمعرّف tg_id <code>{ $tg_id }</code>.
admin-unfreeze-already = ▶️ اللاعب <code>{ $tg_id }</code> نشط بالفعل.
admin-unfreeze-ok = ☀️ تم إلغاء تجميد اللاعب <code>{ $tg_id }</code>.{ $reason_suffix }
admin-unfreeze-reason-suffix = السبب: { $reason }.

admin-ban-usage = ⚠️ الاستخدام: <code>/ban &lt;tg_id&gt; &lt;reason&gt;</code>. السبب مطلوب.
admin-ban-not-authorized = ❌ فقط المشرفون النشطون يمكنهم حظر اللاعبين.
admin-ban-totp-not-configured = ❌ TOTP غير مُعدّ. `/ban` غير متاح.
admin-ban-bad-id = ⚠️ <code>{ $value }</code> ليس معرّف tg_id صالح (عدد صحيح).
admin-ban-no-reason = ⚠️ السبب مطلوب. الاستخدام: <code>/ban &lt;tg_id&gt; &lt;reason&gt;</code>.
admin-ban-not-found = 🔍 لا يوجد لاعب بمعرّف tg_id <code>{ $tg_id }</code>.
admin-ban-already = 🛑 اللاعب <code>{ $tg_id }</code> محظور بالفعل.
admin-ban-confirm-issued = 🛡️ أكّد هذه العملية. أرسل: <code>/confirm { $token } &lt;6-digit code&gt;</code>. مدة صلاحية التوكن: { $ttl_seconds } ثانية.

# /confirm
admin-confirm-usage = ⚠️ الاستخدام: <code>/confirm &lt;token&gt; &lt;6-digit code&gt;</code>.
admin-confirm-not-authorized = ❌ فقط المشرفون النشطون يمكنهم تأكيد العمليات.
admin-confirm-totp-not-configured = ❌ TOTP غير مُعدّ. التأكيد مستحيل.
admin-confirm-token-not-found = ❌ التوكن <code>{ $token }</code> مستخدم بالفعل أو غير موجود.
admin-confirm-token-expired = ⌛ انتهت صلاحية التوكن. أعد تشغيل الأمر.
admin-confirm-admin-mismatch = ❌ هذا التوكن يخص مشرفاً آخر.
admin-confirm-code-invalid = ❌ رمز من 6 أرقام غير صالح.
admin-confirm-success-ban = ✅ تم حظر اللاعب <code>{ $tg_id }</code>.
admin-confirm-success-ban-already = 🛑 اللاعب <code>{ $tg_id }</code> كان محظوراً بالفعل.
admin-confirm-unknown-command-kind = ⚠️ نوع أمر غير معروف <code>{ $command_kind }</code> — يرجى تحديث البوت.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-C — economy commands
# ─────────────────────────────────────────────────────────────────────────────

admin-grant-length-usage = ⚠️ الاستخدام: <code>/grant_length &lt;tg_id&gt; &lt;±delta_cm&gt; &lt;reason&gt;</code>. جميع الوسائط مطلوبة.
admin-grant-length-not-authorized = ❌ فقط المشرفون النشطون يمكنهم تعديل الطول.
admin-grant-length-totp-not-configured = ❌ TOTP غير مُعدّ. `/grant_length` غير متاح.
admin-grant-length-bad-id = ⚠️ <code>{ $value }</code> ليس معرّف tg_id صالح (عدد صحيح).
admin-grant-length-bad-delta = ⚠️ <code>{ $value }</code> ليس ±عدد صحيح أو يساوي 0.
admin-grant-length-no-reason = ⚠️ السبب مطلوب. الاستخدام: <code>/grant_length &lt;tg_id&gt; &lt;±delta_cm&gt; &lt;reason&gt;</code>.
admin-grant-length-not-found = 🔍 لا يوجد لاعب بمعرّف tg_id <code>{ $tg_id }</code>.
admin-grant-length-blocked = 🚫 لا يمكن تعديل طول اللاعب <code>{ $tg_id }</code>: { $reason }.
admin-grant-length-confirm-issued = 🛡️ أكّد هذه العملية. أرسل: <code>/confirm { $token } &lt;6-digit code&gt;</code>. مدة صلاحية التوكن: { $ttl_seconds } ثانية.
admin-grant-length-success = ✅ اللاعب <code>{ $tg_id }</code>: تم تطبيق { $delta } سم. الطول الجديد: { $new_length_cm } سم.
admin-grant-length-success-clamped = ⚠️ اللاعب <code>{ $tg_id }</code>: المطلوب { $requested } سم، تم تطبيق { $applied } سم (حد 24 ساعة). الطول الجديد: { $new_length_cm } سم.
admin-grant-length-soft-ban = 🚫 اللاعب <code>{ $tg_id }</code> في حظر مكافحة غش — تم رفض العملية.

admin-grant-thickness-usage = ⚠️ الاستخدام: <code>/grant_thickness &lt;tg_id&gt; &lt;new_level&gt; &lt;reason&gt;</code>.
admin-grant-thickness-not-authorized = ❌ فقط المشرفون النشطون يمكنهم تعديل السُمك.
admin-grant-thickness-totp-not-configured = ❌ TOTP غير مُعدّ. `/grant_thickness` غير متاح.
admin-grant-thickness-bad-id = ⚠️ <code>{ $value }</code> ليس معرّف tg_id صالح (عدد صحيح).
admin-grant-thickness-bad-level = ⚠️ <code>{ $value }</code> ليس مستوى (عدد صحيح ≥ 1).
admin-grant-thickness-no-reason = ⚠️ السبب مطلوب. الاستخدام: <code>/grant_thickness &lt;tg_id&gt; &lt;new_level&gt; &lt;reason&gt;</code>.
admin-grant-thickness-not-found = 🔍 لا يوجد لاعب بمعرّف tg_id <code>{ $tg_id }</code>.
admin-grant-thickness-blocked = 🚫 لا يمكن تعديل سُمك اللاعب <code>{ $tg_id }</code>: { $reason }.
admin-grant-thickness-level-invalid = ⚠️ المستوى <code>{ $level }</code> خارج النطاق [1, { $max_level }] ({ $reason_code }).
admin-grant-thickness-confirm-issued = 🛡️ أكّد هذه العملية. أرسل: <code>/confirm { $token } &lt;6-digit code&gt;</code>. مدة صلاحية التوكن: { $ttl_seconds } ثانية.
admin-grant-thickness-success = ✅ اللاعب <code>{ $tg_id }</code>: مستوى السُمك أصبح { $new_level } (كان { $previous_level }).
admin-grant-thickness-already-at-level = ℹ️ اللاعب <code>{ $tg_id }</code> بالفعل في مستوى السُمك { $level }.

admin-balance-get-usage = ⚠️ الاستخدام: <code>/balance_get &lt;dotted.key&gt;</code>.
admin-balance-get-not-authorized = ❌ فقط المشرفون النشطون يمكنهم قراءة قيم التوازن.
admin-balance-get-key-not-found = ⚠️ المفتاح <code>{ $path }</code> غير موجود ({ $reason } عند القطعة <code>{ $segment }</code>).
admin-balance-get-result = 📦 <code>{ $path }</code> = <code>{ $value }</code> (توازن v{ $version }).

admin-balance-set-usage = ⚠️ الاستخدام: <code>/balance_set &lt;dotted.key&gt; &lt;json_value&gt; &lt;reason&gt;</code>.
admin-balance-set-not-authorized = ❌ فقط المشرفون النشطون يمكنهم تعديل قيم التوازن.
admin-balance-set-totp-not-configured = ❌ TOTP غير مُعدّ. `/balance_set` غير متاح.
admin-balance-set-no-reason = ⚠️ السبب مطلوب.
admin-balance-set-bad-value = ⚠️ <code>{ $value }</code> ليست قطعة JSON صالحة.
admin-balance-set-key-not-found = ⚠️ المفتاح <code>{ $path }</code> غير موجود ({ $reason } عند القطعة <code>{ $segment }</code>).
admin-balance-set-validation-error = ❌ القيمة لـ <code>{ $path }</code> فشلت في التحقق: { $error }.
admin-balance-set-confirm-issued = 🛡️ أكّد هذه العملية. أرسل: <code>/confirm { $token } &lt;6-digit code&gt;</code>. مدة صلاحية التوكن: { $ttl_seconds } ثانية.
admin-balance-set-success = ✅ المفتاح <code>{ $path }</code>: <code>{ $previous }</code> → <code>{ $new }</code> (توازن v{ $version }).
admin-balance-set-already-at-value = ℹ️ المفتاح <code>{ $path }</code> قيمته بالفعل <code>{ $value }</code>.

admin-idempotency-replay = ℹ️ هذا الأمر (<code>{ $command_kind }</code>) نُفّذ بالفعل خلال الدقيقة الأخيرة — تم تخطي الإعادة.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.5 — /audit
# ─────────────────────────────────────────────────────────────────────────────

admin-audit-usage = ⚠️ الاستخدام: <code>/audit [target_tg_id|-] [action|-] [limit]</code>. جميع الوسائط اختيارية؛ <code>-</code> تعني "بلا فلتر".
admin-audit-not-authorized = ❌ فقط المشرفون النشطون يمكنهم فحص سجل التدقيق.
admin-audit-bad-tg-id = ⚠️ <code>{ $value }</code> ليس معرّف tg_id صالح (عدد صحيح) أو <code>-</code>.
admin-audit-bad-limit = ⚠️ <code>{ $value }</code> ليس حداً صالحاً (عدد صحيح > 0).
admin-audit-unknown-action = ⚠️ فئة إجراء غير معروفة <code>{ $value }</code>.
admin-audit-target-not-found = 🔍 لا يوجد مشرف بمعرّف tg_id <code>{ $tg_id }</code>.
admin-audit-empty = 🗒️ لم يُعثر على سجلات (هدف=<code>{ $target }</code>، إجراء=<code>{ $action }</code>).
admin-audit-header-all = 🗒️ سجل التدقيق: { $count } أحدث السجلات (حد { $limit }، جميع المشرفين).
admin-audit-header-target = 🗒️ سجل التدقيق للمشرف <code>{ $target_tg_id }</code>: { $count } أحدث السجلات (حد { $limit }).
admin-audit-filter-action-suffix = فلتر الإجراء: <code>{ $action }</code>.
admin-audit-row = • #{ $id } · { $occurred_at } · @{ $actor_tg_id } · <code>{ $action }</code> · { $target_kind }=<code>{ $target_id }</code> · src={ $source } · { $reason }

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.1 — /clan
# ─────────────────────────────────────────────────────────────────────────────

admin-clan-usage = ⚠ الاستخدام: <code>/clan &lt;id|chat_id&gt;</code>.
admin-clan-not-authorized = ❌فقط المشرفون النشطون يمكنهم عرض بطاقات القبائل.
admin-clan-bad-id = ⚠ <code>{ $value }</code> ليس معرّف قبيلة (عدد صحيح).
admin-clan-not-found = 🔍القبيلة بمعرّف id/chat_id <code>{ $query }</code> غير موجودة.
admin-clan-card-summary =
    🛡 القبيلة #{ $clan_id }: <b>{ $title }</b>
    chat_id: <code>{ $chat_id }</code> ({ $chat_kind })
    الحالة: { $status }
    الإنشاء: { $created_at } · التحديث: { $updated_at }
    الأعضاء: { $member_count } (نشطون { $active_member_count }) · الطول الإجمالي: { $total_length_cm } سم.
admin-clan-card-leader = 👑 القائد: @{ $username } ({ $name }، tg_id <code>{ $tg_id }</code>) · الطول { $length_cm } سم · منذ { $joined_at }.
admin-clan-card-no-leader = 👑 القائد: —
admin-clan-card-member-row = • @{ $username } ({ $name }، tg_id <code>{ $tg_id }</code>) · { $length_cm } سم · t{ $thickness_level } · { $status } · { $role } · منذ { $joined_at }
admin-clan-card-no-members = (القبيلة ليس لها أعضاء)

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.2 — /freeze_clan + /unfreeze_clan
# ─────────────────────────────────────────────────────────────────────────────

admin-freeze-clan-usage = ⚠ الاستخدام: <code>/freeze_clan &lt;id|chat_id&gt; [reason]</code>.
admin-freeze-clan-not-authorized = ❌فقط المشرفون النشطون يمكنهم تجميد القبائل.
admin-freeze-clan-bad-id = ⚠ <code>{ $value }</code> ليس معرّف قبيلة (عدد صحيح).
admin-freeze-clan-not-found = 🔍القبيلة بمعرّف id/chat_id <code>{ $query }</code> غير موجودة.
admin-freeze-clan-already = ℹ القبيلة #{ $clan_id } مجمّدة بالفعل.
admin-freeze-clan-ok = ❄ تم تجميد القبيلة #{ $clan_id }.{ $reason_suffix }
admin-freeze-clan-reason-suffix = السبب: { $reason }.

admin-unfreeze-clan-usage = ⚠ الاستخدام: <code>/unfreeze_clan &lt;id|chat_id&gt;</code>.
admin-unfreeze-clan-not-authorized = ❌فقط المشرفون النشطون يمكنهم إلغاء تجميد القبائل.
admin-unfreeze-clan-bad-id = ⚠ <code>{ $value }</code> ليس معرّف قبيلة (عدد صحيح).
admin-unfreeze-clan-not-found = 🔍القبيلة بمعرّف id/chat_id <code>{ $query }</code> غير موجودة.
admin-unfreeze-clan-already = ℹ القبيلة #{ $clan_id } نشطة بالفعل.
admin-unfreeze-clan-ok = 🔥 تم إلغاء تجميد القبيلة #{ $clan_id }.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.3 — /clan_daily_head_history
# ─────────────────────────────────────────────────────────────────────────────

admin-clan-daily-head-history-usage = ⚠ الاستخدام: <code>/clan_daily_head_history &lt;id|chat_id&gt; [N=10]</code>.
admin-clan-daily-head-history-not-authorized = ❌فقط المشرفون النشطون يمكنهم رؤية تاريخ رئيس اليوم.
admin-clan-daily-head-history-bad-id = ⚠ <code>{ $value }</code> ليس معرّف قبيلة (عدد صحيح).
admin-clan-daily-head-history-bad-limit = ⚠ <code>{ $value }</code> ليس حداً (عدد صحيح 1..50).
admin-clan-daily-head-history-not-found = 🔍القبيلة بمعرّف id/chat_id <code>{ $query }</code> غير موجودة.
admin-clan-daily-head-history-empty = 👑 القبيلة #{ $clan_id } "{ $title }": تاريخ رئيس اليوم فارغ.
admin-clan-daily-head-history-header = 👑 القبيلة #{ $clan_id } "{ $title }"، آخر { $count } تعيينات لرئيس اليوم:
admin-clan-daily-head-history-row = • <b>{ $moscow_date }</b> — { $tg_id } (@{ $username }، { $name }) +{ $bonus } سم ({ $source })
admin-clan-daily-head-history-row-orphan = • <b>{ $moscow_date }</b> — لاعب محذوف +{ $bonus } سم ({ $source })

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.4 — /announce
# ─────────────────────────────────────────────────────────────────────────────

admin-announce-usage = ⚠ الاستخدام: <code>/announce &lt;ru|en|*&gt; &lt;text&gt;</code>. اللغة تحدد الجمهور: ru — لاعبون بلغة RU، en — بلغة EN أو بلا تفضيل (افتراضي)، * — جميع اللاعبين النشطين.
admin-announce-non-private = 🍆 أوامر المشرف متاحة فقط في الرسائل الخاصة مع البوت.
admin-announce-not-authorized = ❌فقط المشرفون النشطون يمكنهم إطلاق البث.
admin-announce-totp-not-configured = ❌TOTP غير مُعدّ. <code>/announce</code> غير متاح بدونه.
admin-announce-bad-locale = ⚠ <code>{ $value }</code> ليس فلتر لغة معروف. المسموح: <code>ru</code>، <code>en</code>، <code>*</code>.
admin-announce-empty-message = ⚠ نص الإعلان لا يمكن أن يكون فارغاً.
admin-announce-too-long = ⚠ الرسالة طويلة جداً: { $length } حرف، الحد الأقصى { $max_length }.
admin-announce-confirm-issued = 🛡 جاهز للبث إلى <b>{ $recipient_count }</b> لاعب (فلتر: { $locale_filter }). أكّد: <code>/confirm { $token } &lt;6-digit code&gt;</code>. صلاحية التوكن { $ttl_seconds } ثانية.
admin-announce-progress-start = 📤 بدء البث: { $recipient_count } مستلم (فلتر: { $locale_filter }). سأُبلغك عند الانتهاء.
admin-announce-progress-final = ✅ اكتمل البث. المستلمون: { $recipient_count }، تم الإرسال: { $sent_count }، فشل: { $failed_count }، محظورون: { $blocked_count }.
admin-announce-progress-failed = ⚠ فشل البث في الخلفية. التفاصيل في سجلات البوت وتدقيق المشرف.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.6 — /admin_setup_totp
# ─────────────────────────────────────────────────────────────────────────────

admin-setup-totp-usage = ⚠ الاستخدام: <code>/admin_setup_totp &lt;bootstrap-password&gt;</code>. متاح فقط في الرسائل الخاصة مع البوت.
admin-setup-totp-non-private = 🍆 أوامر المشرف متاحة فقط في الرسائل الخاصة مع البوت.
admin-setup-totp-not-authorized = ❌ فقط المشرفون الأعلى النشطون يمكنهم إعداد سر TOTP.
admin-setup-totp-password-not-configured = ❌ <code>BOOTSTRAP_ADMIN_PASSWORD</code> غير مُعدّ في بيئة البوت. الأمر يرفض (fail-closed): إصدار سر TOTP جديد بدون عامل ثانٍ غير مسموح.
admin-setup-totp-password-invalid = ❌ كلمة مرور التهيئة غير صالحة.
admin-setup-totp-already-configured = ❌ TOTP مُعدّ بالفعل. إصدار سر جديد يتطلب إعادة تعيين يدوية من مسؤول قاعدة البيانات (انظر <code>docs/admin_runbook.md</code>).
admin-setup-totp-success = ✅ تم إعداد TOTP. السر وعنوان <code>otpauth://</code> مكتوبان في سجلات الخادم (event=<code>admin_totp_setup</code>) — افتحها في بنيتك التحتية واستوردها في Authenticator/1Password. السر لن يظهر أبداً في المحادثة عمداً.

# ============================================================================
# /mountains, /dungeon (Sprint 3.1-E, GDD §8)
# ============================================================================

# --------------------------- /mountains -------------------------------------

mountains-group = 🏔 أمر /mountains متاح فقط في المحادثة الخاصة مع البوت. افتح الرسائل الخاصة وحاول مرة أخرى.
mountains-other = 🏔 أمر /mountains متاح فقط في المحادثة الخاصة مع البوت.
mountains-not-registered = 🏔 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من الذهاب إلى الجبال.
mountains-already-in = 🏔 أنت بالفعل في الجبال — انتظر عودتك. سيرسل البوت رسالة عند انتهاء الرحلة.
mountains-requirement-thickness = 🏔 الجبال تتطلب سُمكاً ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }. تدرّب عبر /upgrade.
mountains-requirement-length = 🏔 الجبال تتطلب ≥ { NUMBER($required_cm, useGrouping: 0) } سم. لديك { NUMBER($actual_cm, useGrouping: 0) } سم.
mountains-started = 🏔 { $nick } ذهب إلى الجبال لمدة { NUMBER($cooldown_minutes, useGrouping: 0) } دقيقة...
mountains-started-fallback = 🏔 ذهبت إلى الجبال لمدة { NUMBER($cooldown_minutes, useGrouping: 0) } دقيقة...

mountains-finished-header = 🏔 { $nick } عاد من الجبال!
mountains-finished-length-gain =
    📏 الطول: +{ NUMBER($length_delta_cm, useGrouping: 0) } سم (كان { NUMBER($length_before_cm, useGrouping: 0) }، الآن { NUMBER($length_after_cm, useGrouping: 0) })
mountains-finished-length-loss =
    📏 الطول: −{ NUMBER($length_delta_abs_cm, useGrouping: 0) } سم (كان { NUMBER($length_before_cm, useGrouping: 0) }، الآن { NUMBER($length_after_cm, useGrouping: 0) })
mountains-finished-length-zero =
    📏 الطول لم يتغيّر ({ NUMBER($length_before_cm, useGrouping: 0) } سم)
mountains-finished-item-found = 🎩 وجدت: { $item_name } [{ $rarity }]

mountains-button-equip = تجهيز
mountains-button-drop-item = إسقاط

mountains-toast-item-equipped-placeholder = التجهيزات قادمة لاحقاً — العنصر في مخزونك حالياً.
mountains-toast-item-dropped = تم إسقاط العنصر.
mountains-toast-foreign-button = هذا الزر ليس لك.
mountains-toast-run-not-found = هذه الرحلة لم تعد نشطة.
mountains-toast-drop-mismatch = الزر قديم.

# --------------------------- /dungeon ---------------------------------------

dungeon-group = 🏰 أمر /dungeon متاح فقط في المحادثة الخاصة مع البوت. افتح الرسائل الخاصة وحاول مرة أخرى.
dungeon-other = 🏰 أمر /dungeon متاح فقط في المحادثة الخاصة مع البوت.
dungeon-not-registered = 🏰 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من دخول الزنزانة.
dungeon-already-in = 🏰 أنت بالفعل في الزنزانة — انتظر عودتك. سيرسل البوت رسالة عند انتهاء الرحلة.
dungeon-requirement-thickness = 🏰 الزنزانة تتطلب سُمكاً ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }. تدرّب عبر /upgrade.
dungeon-requirement-length = 🏰 الزنزانة تتطلب ≥ { NUMBER($required_cm, useGrouping: 0) } سم. لديك { NUMBER($actual_cm, useGrouping: 0) } سم.
dungeon-started = 🏰 { $nick } دخل الزنزانة لمدة { NUMBER($cooldown_minutes, useGrouping: 0) } دقيقة...
dungeon-started-fallback = 🏰 دخلت الزنزانة لمدة { NUMBER($cooldown_minutes, useGrouping: 0) } دقيقة...

dungeon-finished-header = 🏰 { $nick } عاد من الزنزانة!
dungeon-finished-length-gain =
    📏 الطول: +{ NUMBER($length_delta_cm, useGrouping: 0) } سم (كان { NUMBER($length_before_cm, useGrouping: 0) }، الآن { NUMBER($length_after_cm, useGrouping: 0) })
dungeon-finished-length-loss =
    📏 الطول: −{ NUMBER($length_delta_abs_cm, useGrouping: 0) } سم (كان { NUMBER($length_before_cm, useGrouping: 0) }، الآن { NUMBER($length_after_cm, useGrouping: 0) })
dungeon-finished-length-zero =
    📏 الطول لم يتغيّر ({ NUMBER($length_before_cm, useGrouping: 0) } سم)
dungeon-finished-item-found = 🎩 وجدت: { $item_name } [{ $rarity }]

dungeon-button-equip = تجهيز
dungeon-button-drop-item = إسقاط

dungeon-toast-item-equipped-placeholder = التجهيزات قادمة لاحقاً — العنصر في مخزونك حالياً.
dungeon-toast-item-dropped = تم إسقاط العنصر.
dungeon-toast-foreign-button = هذا الزر ليس لك.
dungeon-toast-run-not-found = هذه الرحلة لم تعد نشطة.
dungeon-toast-drop-mismatch = الزر قديم.

# ============================================================================
# /caravan (Sprint 3.2-D, GDD §9)
# ============================================================================

caravans-group = 🐪 أمر /caravan متاح فقط في المحادثة الخاصة مع البوت. افتح الرسائل الخاصة وحاول مرة أخرى.
caravans-other = 🐪 أمر /caravan متاح فقط في المحادثة الخاصة مع البوت.
caravans-not-registered = 🐪 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من تجميع قافلة.
caravans-usage =
    🐪 لتجميع قافلة، مرّر معرّف محادثة القبيلة المستقبِلة ومساهمتك بالسنتيمتر:
    <code>/caravan &lt;receiver_chat_id&gt; &lt;contribution_cm&gt;</code>

    مثال: <code>/caravan -1001234567890 30</code>
caravans-receiver-invalid = 🐪 هذا لا يبدو مثل معرّف محادثة Telegram: <code>{ $value }</code>. مرّر معرّف المحادثة الرقمي للقبيلة المستقبِلة (معرّفات المحادثات الجماعية سالبة).
caravans-contribution-invalid = 🐪 المساهمة يجب أن تكون عدداً صحيحاً موجباً، حصلت على: <code>{ $value }</code>.
caravans-no-clan = 🐪 ليس لديك قبيلة. فقط قائد القبيلة يمكنه تجميع قافلة.
caravans-not-a-leader = 🐪 فقط قائد القبيلة يمكنه تجميع قافلة — أنت عضو عادي.
caravans-receiver-not-found = 🐪 المحادثة بمعرّف chat_id <code>{ $chat_id }</code> ليست قبيلة مسجّلة. مرّر معرّف محادثة قبيلة أخرى.
caravans-receiver-same-as-sender = 🐪 لا يمكنك إرسال قافلة إلى قبيلتك. مرّر معرّف محادثة قبيلة أخرى.
caravans-already-in = 🐪 قبيلتك لديها بالفعل قافلة نشطة — انتظر حتى تنتهي أو ألغها من اللوبي.
caravans-cooldown = 🐪 فترة تهدئة قافلة القبيلة لم تنتهِ بعد. حاول مرة أخرى بعد { NUMBER($remaining_minutes, useGrouping: 0) } دقيقة.
caravans-requirement-thickness = 🐪 تجميع قافلة يتطلب سُمكاً ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }. تدرّب عبر /upgrade.
caravans-requirement-length = 🐪 بعد مساهمتك يجب أن يبقى لديك ≥ { NUMBER($required_cm, useGrouping: 0) } سم من الطول. سيبقى لك { NUMBER($actual_cm, useGrouping: 0) } سم.
caravans-player-frozen = 🐪 ملفك الشخصي مجمّد — لا يمكنك تجميع قافلة.
caravans-clan-frozen-sender = 🐪 قبيلتك مجمّدة — لا يمكنك تجميع قافلة.
caravans-clan-frozen-receiver = 🐪 القبيلة المستقبِلة مجمّدة — لا يمكنك إرسال قافلة إليها.

caravans-created-private =
    🐪 تم تجميع القافلة!
    المستقبِل: <b>{ $receiver_clan_name }</b>
    المساهمة: { NUMBER($contribution_cm, useGrouping: 0) } سم
    اللوبي مفتوح لمدة { NUMBER($lobby_minutes, useGrouping: 0) } دقيقة — تم نشر الإعلان في محادثة قبيلتك.
caravans-created-announcement =
    🐪 <b>{ $leader_nick }</b> يجمّع قافلة!
    الهدف: <b>{ $receiver_clan_name }</b>
    مساهمة القائد: { NUMBER($contribution_cm, useGrouping: 0) } سم
    اللوبي مفتوح لمدة { NUMBER($lobby_minutes, useGrouping: 0) } دقيقة — انضم قبل فوات الأوان.
caravans-button-show-lobby = عرض اللوبي
caravans-button-cancel = إلغاء القافلة

caravans-lobby-state =
    🐪 <b>{ $leader_nick }</b> يجمّع قافلة إلى <b>{ $receiver_clan_name }</b>
    اللوبي { $lobby_status }.

    القائمة:
    • القوافل: { NUMBER($caravaneers_count, useGrouping: 0) } (مساهمة: { NUMBER($total_contribution_cm, useGrouping: 0) } سم)
    • المدافعون: { NUMBER($defenders_count, useGrouping: 0) } / { NUMBER($defenders_cap, useGrouping: 0) }
    • المغيرون: { NUMBER($raiders_count, useGrouping: 0) } / { NUMBER($raiders_cap, useGrouping: 0) }
caravans-lobby-status-open = يُغلق بعد { NUMBER($remaining_minutes, useGrouping: 0) } دقيقة
caravans-lobby-status-closing = يُغلق
caravans-button-join-defender = انضم كمدافع
caravans-button-join-raider = انضم كمُغير
caravans-button-leave = مغادرة

caravans-battle-started =
    🐪 قافلة من <b>{ $sender_clan_name }</b> إلى <b>{ $receiver_clan_name }</b> انطلقت!

    القائد: <b>{ $leader_nick }</b>
    القوافل: { NUMBER($caravaneers_count, useGrouping: 0) }
    المدافعون: { NUMBER($defenders_count, useGrouping: 0) }
    المغيرون: { NUMBER($raiders_count, useGrouping: 0) }
    الحمولة: { NUMBER($total_cargo_cm, useGrouping: 0) } سم

    ⚔️ المعركة ستنتهي تقريباً بعد { NUMBER($battle_minutes, useGrouping: 0) } دقيقة.
caravans-battle-finished-delivered =
    ✅ قافلة من <b>{ $sender_clan_name }</b> وصلت إلى <b>{ $receiver_clan_name }</b>!

    القائد: <b>{ $leader_nick }</b>
    القوافل الناجون: { NUMBER($caravaneers_alive, useGrouping: 0) } / { NUMBER($caravaneers_total, useGrouping: 0) }
    المدافعون الناجون: { NUMBER($defenders_alive, useGrouping: 0) } / { NUMBER($defenders_total, useGrouping: 0) }

    🎁 كل عضو في قبيلة المُرسل حصل على +{ NUMBER($clan_bonus_sender_cm, useGrouping: 0) } سم.
    🎁 كل عضو في قبيلة المستقبِل حصل على +{ NUMBER($clan_bonus_receiver_cm, useGrouping: 0) } سم.
caravans-battle-finished-raided =
    ☠️ قافلة من <b>{ $sender_clan_name }</b> إلى <b>{ $receiver_clan_name }</b> تعرّضت للنهب!

    القائد: <b>{ $leader_nick }</b>
    أتامان الفائز: <b>{ $ataman_nick }</b>

    الحمولة ({ NUMBER($total_cargo_cm, useGrouping: 0) } سم) قُسّمت بين { NUMBER($raiders_count, useGrouping: 0) } مُغيرين.

caravans-cancel-message = 🐪 ألغى القائد القافلة.
caravans-cancel-toast-success = تم إلغاء القافلة
caravans-cancel-toast-already-cancelled = القافلة مُلغاة بالفعل

caravans-callback-toast-caravan-not-found = القافلة غير موجودة
caravans-callback-toast-invalid-state = القافلة لم تعد في اللوبي
caravans-callback-toast-not-a-leader = فقط القائد يمكنه إلغاء القافلة
caravans-callback-toast-player-not-found = اضغط /start في الرسائل الخاصة مع البوت أولاً
caravans-callback-toast-generic-error = حدث خطأ ما. يرجى المحاولة مرة أخرى.

caravans-join-toast-success-defender = أنت في اللوبي كمدافع
caravans-join-toast-success-raider = أنت في اللوبي كمُغير
caravans-callback-toast-lobby-closed = لوبي القافلة مغلق بالفعل
caravans-callback-toast-player-frozen = ملفك الشخصي مجمّد
caravans-callback-toast-already-in-caravan = أنت بالفعل في قافلة نشطة
caravans-callback-toast-role-conflict-defender = المدافعون يجب أن يكونوا أعضاء في قبيلة المستقبِل
caravans-callback-toast-role-conflict-raider = المغيرون يجب ألا يكونوا أعضاء في أي من قبائل القافلة
caravans-callback-toast-capacity-defender = اكتمل عدد المدافعين: { NUMBER($limit, useGrouping: 0) }. لا أماكن متبقية.
caravans-callback-toast-capacity-raider = اكتمل عدد المغيرين: { NUMBER($limit, useGrouping: 0) }. لا أماكن متبقية.
caravans-callback-toast-requirement-thickness = يتطلب سُمكاً ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }.
caravans-callback-toast-requirement-length = يتطلب طولاً ≥ { NUMBER($required_cm, useGrouping: 0) } سم. لديك { NUMBER($actual_cm, useGrouping: 0) } سم.

caravans-leave-toast-success = غادرت لوبي القافلة
caravans-leave-toast-success-with-contribution = غادرت اللوبي. المُعاد: { NUMBER($contribution_cm, useGrouping: 0) } سم
caravans-leave-toast-leader-cannot-leave = القائد لا يمكنه المغادرة. لإلغاء القافلة، اضغط "إلغاء".
caravans-leave-toast-not-a-participant = لست مشاركاً في هذه القافلة

caravans-join-usage =
    🐪 للانضمام كقافلة، مرّر معرّف القافلة (مرئي في اللوبي) ومساهمة بالسنتيمتر:
    <code>/caravan_join &lt;caravan_id&gt; &lt;contribution_cm&gt;</code>

    مثال: <code>/caravan_join 42 30</code>
caravans-join-caravan-id-invalid = 🐪 معرّف القافلة يجب أن يكون عدداً صحيحاً موجباً، حصلت على: <code>{ $value }</code>.
caravans-join-success-caravaneer =
    🐪 انضممت للقافلة كقافلة!
    المساهمة: { NUMBER($contribution_cm, useGrouping: 0) } سم
caravans-join-role-conflict-caravaneer = 🐪 فقط أعضاء قبيلة المُرسل يمكنهم الانضمام كقافلة.

# ============================================================================
# /boss (Sprint 3.3-D, GDD §10)
# ============================================================================

bosses-not-registered = 👹 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من استدعاء رئيس الغارة.
bosses-usage = 👹 لاستدعاء رئيس غارة، اكتب <code>/boss</code> — سيُختار لاعب عشوائي من أفضل { NUMBER($top_n_pool, useGrouping: 0) } كرئيس.
bosses-cooldown = 👹 فترة تهدئة رئيس الغارة العامة لم تنتهِ بعد. حاول مرة أخرى بعد { NUMBER($remaining_minutes, useGrouping: 0) } دقيقة.
bosses-already-in = 👹 أنت بالفعل في غارة نشطة — انتظر حتى تنتهي أو غادر اللوبي أولاً.
bosses-requirement-thickness = 👹 استدعاء رئيس غارة يتطلب سُمكاً ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }. تدرّب عبر /upgrade.
bosses-requirement-length = 👹 تحتاج طولاً ≥ { NUMBER($required_cm, useGrouping: 0) } سم لاستدعاء غارة. لديك { NUMBER($actual_cm, useGrouping: 0) } سم.
bosses-player-frozen = 👹 ملفك الشخصي مجمّد — لا يمكنك استدعاء رئيس غارة.
bosses-pool-empty = 👹 لا مرشحين مؤهلين لرئيس الغارة حالياً — حاول لاحقاً.

bosses-summoned-private =
    👹 تم استدعاء رئيس الغارة!
    الرئيس: <b>{ $boss_nick }</b> ({ NUMBER($boss_length_cm, useGrouping: 0) } سم)
    اللوبي مفتوح لمدة { NUMBER($lobby_minutes, useGrouping: 0) } دقيقة — تم نشر الإعلان في المحادثة.
bosses-summoned-announcement =
    👹 <b>{ $summoner_nick }</b> يتحدّى <b>{ $boss_nick }</b> في غارة!
    طول الرئيس: { NUMBER($boss_length_cm, useGrouping: 0) } سم
    اللوبي مفتوح لمدة { NUMBER($lobby_minutes, useGrouping: 0) } دقيقة — انضم قبل فوات الأوان.
bosses-button-show-lobby = عرض اللوبي
bosses-button-cancel = إلغاء الغارة

bosses-lobby-state =
    👹 <b>{ $summoner_nick }</b> يغير على <b>{ $boss_nick }</b>
    اللوبي { $lobby_status }.

    طول الرئيس: { NUMBER($boss_length_cm, useGrouping: 0) } سم
    المغيرون: { NUMBER($raiders_count, useGrouping: 0) }
bosses-lobby-status-open = يُغلق بعد { NUMBER($remaining_minutes, useGrouping: 0) } دقيقة
bosses-lobby-status-closing = يُغلق
bosses-button-join = انضم للغارة
bosses-button-leave = مغادرة

bosses-battle-started =
    👹 بدأت الغارة ضد <b>{ $boss_nick }</b>!

    المستدعي: <b>{ $summoner_nick }</b>
    المغيرون: { NUMBER($raiders_count, useGrouping: 0) }
    طول الرئيس: { NUMBER($boss_length_cm, useGrouping: 0) } سم

    ⚔️ الرئيس يضرب كل { NUMBER($round_seconds, useGrouping: 0) } ثانية.
bosses-round-tick =
    ⚔️ الجولة { NUMBER($round_number, useGrouping: 0) } — الرئيس <b>{ $boss_nick }</b>

    الضرر للرئيس: { NUMBER($boss_damage_cm, useGrouping: 0) } سم (الآن { NUMBER($boss_length_cm, useGrouping: 0) } سم)
    المُستبعدون: { NUMBER($eliminated_count, useGrouping: 0) }
    المغيرون المتبقون: { NUMBER($raiders_alive, useGrouping: 0) }
bosses-battle-finished-victory =
    🏆 المغيرون هزموا <b>{ $boss_nick }</b>!

    المستدعي: <b>{ $summoner_nick }</b>
    المغيرون الأحياء: { NUMBER($raiders_alive, useGrouping: 0) }

    🎁 كل مُغير ناجٍ يحصل على +{ NUMBER($per_raider_grant_cm, useGrouping: 0) } سم.
bosses-battle-finished-defeat =
    ☠️ فشلت الغارة ضد <b>{ $boss_nick }</b>!

    المستدعي: <b>{ $summoner_nick }</b>
    المغيرون الأحياء: { NUMBER($raiders_alive, useGrouping: 0) }

    الرئيس يأخذ { NUMBER($total_granted_cm, useGrouping: 0) } سم من الطول.

bosses-cancel-message = 👹 ألغى المستدعي الغارة.
bosses-cancel-toast-success = تم إلغاء الغارة
bosses-cancel-toast-already-cancelled = الغارة مُلغاة بالفعل

bosses-callback-toast-fight-not-found = الغارة غير موجودة
bosses-callback-toast-invalid-state = الغارة لم تعد في اللوبي
bosses-callback-toast-not-summoner = فقط المستدعي يمكنه إلغاء الغارة
bosses-callback-toast-player-not-found = اضغط /start في الرسائل الخاصة مع البوت أولاً
bosses-callback-toast-player-frozen = ملفك الشخصي مجمّد
bosses-callback-toast-generic-error = حدث خطأ ما. يرجى المحاولة مرة أخرى.

bosses-join-toast-success = انضممت للغارة
bosses-callback-toast-lobby-closed = لوبي الغارة مغلق بالفعل
bosses-callback-toast-already-in-fight = أنت بالفعل مشارك في هذه الغارة
bosses-callback-toast-cannot-join-as-boss = لا يمكنك الانضمام كمُغير — أنت الرئيس
bosses-callback-toast-requirement-thickness = يتطلب سُمكاً ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }.
bosses-callback-toast-requirement-length = يتطلب طولاً ≥ { NUMBER($required_cm, useGrouping: 0) } سم. لديك { NUMBER($actual_cm, useGrouping: 0) } سم.

bosses-leave-toast-success = غادرت لوبي الغارة
bosses-leave-toast-not-a-participant = لست مشاركاً في هذه الغارة
bosses-leave-toast-summoner-leaves = المستدعي لا يمكنه المغادرة — استخدم "إلغاء الغارة" بدلاً من ذلك.

## /inventory + /enchant (Sprint 3.4-D)

inventory-group = 🎒 أمر /inventory يعمل فقط في المحادثة الخاصة مع البوت. افتح رسالة خاصة وحاول مرة أخرى.

inventory-other = 🎒 أمر /inventory يعمل فقط في المحادثة الخاصة مع البوت.

inventory-not-registered = 🎒 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من عرض مخزونك.

inventory-empty = 🎒 مخزونك فارغ.\nاذهب في رحلة /forest أو /mountains، قاتل /boss، أو انضم لـ /caravan للحصول على عناصر ولفائف.

inventory-card =
    🎒 المخزون
    العناصر: { NUMBER($items_count, useGrouping: 0) }
    مجموعات اللفائف: { NUMBER($scrolls_count, useGrouping: 0) }

inventory-item-line = • <b>{ $display_name }{ $enchant_suffix }</b> [{ $slot_label }، { $rarity_label }]

inventory-scroll-line = • { $scroll_label } × { NUMBER($qty, useGrouping: 0) }

inventory-section-items = 📦 العناصر:
inventory-section-scrolls = 📜 اللفائف:

inventory-button-enchant = ⚒ سحر

inventory-toast-no-scroll = لا لفائف مطابقة لهذا العنصر.

inventory-picker-card =
    ⚒ سحر عنصر
    العنصر: <b>{ $item_display }</b>

    اختر لفيفة للسحر بها.

inventory-picker-button-regular = لفيفة عادية
inventory-picker-button-blessed = لفيفة مباركة
inventory-picker-button-cancel = إلغاء

inventory-picker-cancelled = تم إلغاء السحر.

inventory-picker-toast-cancelled = تم الإلغاء.

inventory-slot-hat = الرأس
inventory-slot-body = الجسم
inventory-slot-legs = الأرجل
inventory-slot-boots = الأحذية
inventory-slot-ring = الخاتم
inventory-slot-chain = السلسلة
inventory-slot-right-hand = اليد اليمنى
inventory-slot-left-hand = اليد اليسرى

inventory-rarity-common = عادي
inventory-rarity-uncommon = غير عادي
inventory-rarity-rare = نادر
inventory-rarity-epic = ملحمي
inventory-rarity-legendary = أسطوري

inventory-scroll-display-regular = لفيفة { $category_label }
inventory-scroll-display-blessed = لفيفة { $category_label } مباركة

inventory-scroll-category-weapon = سلاح
inventory-scroll-category-armor = درع
inventory-scroll-category-jewelry = مجوهرات

# --- /enchant ---

enchant-group = ⚒ أمر /enchant يعمل فقط في المحادثة الخاصة مع البوت. افتح رسالة خاصة وحاول مرة أخرى.

enchant-other = ⚒ أمر /enchant يعمل فقط في المحادثة الخاصة مع البوت.

enchant-not-registered = ⚒ يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من السحر.

enchant-usage = الاستخدام: <code>/enchant &lt;item_id&gt; &lt;scroll_id&gt;</code>\n\nمثال: <code>/enchant item.right_hand.test_1 weapon_scroll:regular</code>\n\nأو افتح /inventory واضغط زر ⚒ سحر على بطاقة العنصر.

enchant-warning-regular =
    ⚒ محاولة سحر
    العنصر: <b>{ $item_display }</b>
    اللفيفة: { $scroll_display }
    المستوى: { $tier_emoji } { $tier_label }

    النتائج الممكنة:
    • نجاح (+1)
    • بلا تأثير
    • انخفاض (-1)
    • <b>تدمير</b> (العنصر يُفقد للأبد)

enchant-warning-blessed =
    ⚒ محاولة سحر مبارك
    العنصر: <b>{ $item_display }</b>
    اللفيفة: { $scroll_display }
    المستوى: { $tier_emoji } { $tier_label }

    النتائج الممكنة:
    • نجاح كبير (+2)
    • نجاح (+1)
    • بلا تأثير
    • انخفاض (-1)
    • انخفاض كبير (-2)

    اللفيفة المباركة لا تدمّر العنصر أبداً.

enchant-button-confirm = تأكيد
enchant-button-cancel = إلغاء

enchant-success =
    ✅ نجاح! { $item_display }
    المستوى: +{ NUMBER($old_level, useGrouping: 0) } → +{ NUMBER($new_level, useGrouping: 0) }

enchant-no-effect =
    ⚪ بلا تأثير.
    العنصر: <b>{ $item_display }</b>
    المستوى لم يتغيّر: +{ NUMBER($old_level, useGrouping: 0) }
    تم استهلاك اللفيفة.

enchant-drop =
    🔻 انخفاض.
    العنصر: <b>{ $item_display }</b>
    المستوى: +{ NUMBER($old_level, useGrouping: 0) } → +{ NUMBER($new_level, useGrouping: 0) }

enchant-destroy =
    💥 تم تدمير العنصر!
    <b>{ $item_display }</b> فُقد للأبد.

enchant-cancelled = تم إلغاء السحر.

enchant-idempotent = ℹ المحاولة تمت معالجتها بالفعل. افتح /inventory لرؤية الحالة الحالية.

enchant-tier-safe = آمن
enchant-tier-easy = سهل
enchant-tier-hard = صعب
enchant-tier-very-hard = صعب جداً
enchant-tier-extreme = شديد
enchant-tier-impossible = مستحيل

enchant-error-wrong-category = ⚠ هذه اللفيفة لا يمكنها سحر هذا العنصر: عدم تطابق الفئة.
enchant-error-item-not-found = ⚠ العنصر غير موجود في مخزونك.
enchant-error-scroll-not-found = ⚠ لا تملك هذه اللفيفة.
enchant-error-out-of-stock = ⚠ نفدت لديك هذه اللفيفة.
enchant-error-bad-args = ⚠ وسائط خاطئة. انظر /enchant للاستخدام.

enchant-toast-confirmed = اكتمل السحر.
enchant-toast-cancelled = تم إلغاء السحر.
enchant-toast-already-processed = تمت المعالجة بالفعل.
enchant-toast-error = حدث خطأ ما.

# ============================================================================
# /roulette_free (Sprint 3.5-D, GDD §12.4)
# ============================================================================

roulette-free-group = 🎰 أمر /roulette_free يعمل فقط في المحادثة الخاصة مع البوت. افتح رسالة خاصة وحاول مرة أخرى.
roulette-free-other = 🎰 أمر /roulette_free يعمل فقط في المحادثة الخاصة مع البوت.
roulette-free-not-registered = 🎰 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من تدوير الروليت.

roulette-free-requirement-thickness = 🎰 الروليت يُفتح عند سُمك ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }. تدرّب عبر /upgrade.
roulette-free-requirement-length = 🎰 التدوير يتطلب ≥ { NUMBER($required_cm, useGrouping: 0) } سم. لديك { NUMBER($actual_cm, useGrouping: 0) } سم.

roulette-free-prompt =
    🎰 روليت مجاني
    الطول الحالي: { NUMBER($current_length_cm, useGrouping: 0) } سم
    تكلفة التدوير: { NUMBER($cost_cm, useGrouping: 0) } سم
    بعد التدوير سيكون لديك: { NUMBER($remaining_cm, useGrouping: 0) } سم

    اضغط الزر للتدوير.

roulette-free-button-spin = تدوير — { NUMBER($cost_cm, useGrouping: 0) } سم

roulette-free-animation-frame-1 = 🎰 يتم تدوير الروليت…
roulette-free-animation-frame-2 = 🎰 الكرة لا تزال تتدحرج…
roulette-free-animation-frame-3 = 🎰 كادت تتوقف…

roulette-free-result-length =
    🎰 طول! ربحت <b>+{ NUMBER($length_cm, useGrouping: 0) } سم</b>.
    تكلفة التدوير: { NUMBER($cost_cm, useGrouping: 0) } سم.

roulette-free-result-item =
    🎰 حصلت على عنصر!
    تكلفة التدوير: { NUMBER($cost_cm, useGrouping: 0) } سم.
    ستُمنح المكافأة في المرحلة 4 — في الوقت الحالي تم تسجيل اللفة.

roulette-free-result-scroll-regular =
    🎰 حصلت على لفيفة!
    تكلفة التدوير: { NUMBER($cost_cm, useGrouping: 0) } سم.
    ستُمنح المكافأة في المرحلة 4 — في الوقت الحالي تم تسجيل اللفة.

roulette-free-result-scroll-blessed =
    🎰 حصلت على لفيفة مباركة!
    تكلفة التدوير: { NUMBER($cost_cm, useGrouping: 0) } سم.
    ستُمنح المكافأة في المرحلة 4 — في الوقت الحالي تم تسجيل اللفة.

roulette-free-result-crypto-lot =
    🎰 حصلت على حصة كريبتو!
    تكلفة التدوير: { NUMBER($cost_cm, useGrouping: 0) } سم.
    ستُمنح المكافأة في المرحلة 4 — في الوقت الحالي تم تسجيل اللفة.

roulette-free-result-idempotent = ℹ هذه اللفة تمت معالجتها بالفعل. افتح /profile لرؤية الحالة الحالية.

roulette-free-toast-thickness-gate = تحتاج سُمكاً ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }.
roulette-free-toast-insufficient-length = تحتاج ≥ { NUMBER($required_cm, useGrouping: 0) } سم. لديك { NUMBER($actual_cm, useGrouping: 0) } سم.
roulette-free-toast-not-registered = اضغط /start في الرسائل الخاصة مع البوت أولاً.
roulette-free-toast-spin-complete = اكتمل التدوير.
roulette-free-toast-already-processed = تمت المعالجة بالفعل.
roulette-free-toast-error = حدث خطأ ما.

# -----------------------------------------------------------------------------
# /roulette_paid (Sprint 4.1-A, GDD §12.5)
# -----------------------------------------------------------------------------
roulette-paid-group = 🎰 أمر /roulette_paid متاح فقط في الرسائل الخاصة. افتح المحادثة الخاصة مع البوت وحاول مرة أخرى.
roulette-paid-other = 🎰 أمر /roulette_paid متاح فقط في الرسائل الخاصة.
roulette-paid-not-registered = 🎰 يبدو أنك لم تسجّل بعد. اضغط /start في هذه المحادثة — ثم ستتمكن من تدوير الروليت.

roulette-paid-requirement-thickness = 🎰 الروليت المدفوع يُفتح عند سُمك ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }. جرّب /upgrade.

roulette-paid-prompt =
    🎰 روليت مدفوع
    كل لفة فرصة لطول، عناصر، لفائف، أو جائزة كريبتو.

    التكلفة:
    — لفة واحدة: { NUMBER($single_cost_stars, useGrouping: 0) } ⭐
    — باقة { NUMBER($pack10_spins, useGrouping: 0) }: { NUMBER($pack10_cost_stars, useGrouping: 0) } ⭐

    اختر باقة للمتابعة إلى الدفع.

roulette-paid-button-buy-single = اشترِ لفة واحدة — { NUMBER($cost_stars, useGrouping: 0) } ⭐
roulette-paid-button-buy-pack-10 = اشترِ باقة { NUMBER($pack10_spins, useGrouping: 0) } — { NUMBER($cost_stars, useGrouping: 0) } ⭐

roulette-paid-invoice-title-single = 🎰 روليت مدفوع — لفة واحدة
roulette-paid-invoice-title-pack-10 = 🎰 روليت مدفوع — باقة 10
roulette-paid-invoice-description-single = لفة واحدة من الروليت المدفوع مقابل { NUMBER($cost_stars, useGrouping: 0) } ⭐. فرصة لطول، عناصر، لفائف، أو جائزة كريبتو.
roulette-paid-invoice-description-pack-10 = { NUMBER($pack10_spins, useGrouping: 0) } لفات من الروليت المدفوع مقابل { NUMBER($cost_stars, useGrouping: 0) } ⭐. ~10% خصم مقارنة بالشراء المنفرد.
roulette-paid-invoice-label-single = روليت مدفوع — لفة واحدة
roulette-paid-invoice-label-pack-10 = روليت مدفوع — باقة { NUMBER($pack10_spins, useGrouping: 0) }

roulette-paid-result-single-length =
    🎰 طول! حصلت على <b>+{ NUMBER($length_cm, useGrouping: 0) } سم</b>.
    تم خصم: { NUMBER($spent_stars, useGrouping: 0) } ⭐.

roulette-paid-result-single-item =
    🎰 حصلت على عنصر!
    تم خصم: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    ستُمنح المكافأة في المرحلة 4 — في الوقت الحالي تم تسجيل النتيجة.

roulette-paid-result-single-scroll-regular =
    🎰 حصلت على لفيفة!
    تم خصم: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    ستُمنح المكافأة في المرحلة 4 — في الوقت الحالي تم تسجيل النتيجة.

roulette-paid-result-single-scroll-blessed =
    🎰 حصلت على لفيفة مباركة!
    تم خصم: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    ستُمنح المكافأة في المرحلة 4 — في الوقت الحالي تم تسجيل النتيجة.

roulette-paid-result-single-crypto-lot =
    🎰 حصلت على حصة كريبتو!
    تم خصم: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    ستُمنح المكافأة في المرحلة 4 — في الوقت الحالي تم تسجيل النتيجة.

roulette-paid-result-pack-10 =
    🎰 اكتملت باقة { NUMBER($n_spins, useGrouping: 0) }!
    الطول: <b>+{ NUMBER($total_length_cm, useGrouping: 0) } سم</b> ({ NUMBER($n_length, useGrouping: 0) } من { NUMBER($n_spins, useGrouping: 0) }).
    عناصر: { NUMBER($n_item, useGrouping: 0) }، لفائف: { NUMBER($n_scroll_regular, useGrouping: 0) }، مباركة: { NUMBER($n_scroll_blessed, useGrouping: 0) }، حصص كريبتو: { NUMBER($n_crypto_lot, useGrouping: 0) }.
    تم خصم: { NUMBER($spent_stars, useGrouping: 0) } ⭐.

roulette-paid-result-idempotent = ℹ هذه اللفة مكتملة بالفعل. افتح /profile لرؤية حالتك الحالية.

roulette-paid-payment-invalid = ⚠ لم يتم التحقق من الدفع وتم رفضه. لم تحدث أي لفة. أعد فتح /roulette_paid وحاول مرة أخرى.

roulette-paid-toast-thickness-gate = تحتاج سُمكاً ≥ { NUMBER($required, useGrouping: 0) }. أنت في { NUMBER($actual, useGrouping: 0) }.
roulette-paid-toast-not-registered = اضغط /start في الرسائل الخاصة مع البوت أولاً.
roulette-paid-toast-payment-ok = تم تأكيد الدفع، تم تدوير الروليت.
roulette-paid-toast-already-processed = تمت المعالجة بالفعل.
roulette-paid-toast-error = حدث خطأ ما.

## /link_wallet + /link_wallet_confirm (Sprint 4.1-D.6, GDD §12.6.4)

link-wallet-group = أمر `/link_wallet` يعمل فقط في الرسائل الخاصة مع البوت. افتح الرسائل الخاصة وحاول مرة أخرى.
link-wallet-other = أمر `/link_wallet` يعمل فقط في الرسائل الخاصة مع البوت.
link-wallet-not-registered = سجّل أولاً — اضغط /start في الرسائل الخاصة مع البوت.

link-wallet-prompt =
    💼 <b>ربط محفظة TON</b>

    اختر العملة التي ستُدفع بها حصص جوائزك — هذا إعداد لمرة واحدة. يمكنك تغيير العنوان لاحقاً بتشغيل `/link_wallet` مرة أخرى.

link-wallet-button-ton = ربط محفظة TON
link-wallet-button-usdt = ربط محفظة USDT (TON jetton)

link-wallet-instructions-ton =
    🔗 <b>TON Connect — محفظة TON</b>

    1. افتح محفظة متوافقة مع TON Connect (Tonkeeper, MyTonWallet, Tonhub).
    2. ابحث عن قسم «TON Connect» / «Connect dApp» واتصل بهذا البوت.
    3. وقّع `tonconnect_proof` — محفظتك تثبت ملكية العنوان.
    4. بعد التوقيع يربط البوت العنوان تلقائياً. إذا لم يحدث ذلك، شغّل `/link_wallet_confirm ton <address> <proof>` يدوياً.

link-wallet-instructions-usdt =
    🔗 <b>TON Connect — محفظة USDT</b>

    1. افتح محفظة متوافقة مع TON Connect (Tonkeeper, MyTonWallet, Tonhub).
    2. ابحث عن قسم «TON Connect» / «Connect dApp» واتصل بهذا البوت.
    3. وقّع `tonconnect_proof` — محفظتك تثبت ملكية عنوان TON الذي سيستقبل jetton-USDT.
    4. بعد التوقيع يربط البوت العنوان تلقائياً. إذا لم يحدث ذلك، شغّل `/link_wallet_confirm usdt <address> <proof>` يدوياً.

link-wallet-invalid-callback = حدث خطأ في الزر. اضغط /link_wallet مرة أخرى.
link-wallet-toast-invalid = انتهت صلاحية الزر. شغّل /link_wallet مرة أخرى.

link-wallet-confirm-group = أمر `/link_wallet_confirm` يعمل فقط في الرسائل الخاصة مع البوت. افتح الرسائل الخاصة وحاول مرة أخرى.
link-wallet-confirm-other = أمر `/link_wallet_confirm` يعمل فقط في الرسائل الخاصة مع البوت.
link-wallet-confirm-not-registered = سجّل أولاً — اضغط /start في الرسائل الخاصة مع البوت.

link-wallet-confirm-usage =
    الاستخدام: `/link_wallet_confirm <currency> <address> <proof>`.

    هنا `currency` هو `ton` أو `usdt`، `address` هو عنوان TON الخاص بك، و`proof` هو إثبات TON Connect الذي أنتجته محفظتك.

link-wallet-confirm-unsupported = العملة `{ $code }` غير مدعومة. المتاح: `ton`، `usdt`.

link-wallet-confirm-invalid-proof =
    ❌ فشل التحقق من إثبات TON Connect. التوقيع مزوّر أو منتهي الصلاحية.

    شغّل /link_wallet ووقّع مرة أخرى.

link-wallet-confirm-already-linked =
    ℹ المحفظة `{ $address }` مرتبطة بالفعل لـ `{ $currency }`. لا شيء للفعل — حصص الجوائز تذهب هناك.

link-wallet-confirm-linked =
    ✅ المحفظة `{ $address }` مرتبطة لـ `{ $currency }`. حصص الجوائز بهذه العملة ستُدفع هنا.

link-wallet-confirm-relinked =
    ✅ العنوان لـ `{ $currency }` أصبح الآن `{ $address }`. حصص الجوائز الجديدة ستُدفع للعنوان الجديد.

link-wallet-request-usage =
    الاستخدام: `/link_wallet <ton|usdt> <address>`.

    `currency` هو `ton` أو `usdt`، `address` هو عنوان TON الخاص بك (خام `workchain:hex64` أو base64url ودي).

link-wallet-request-invalid-currency = العملة `{ $code }` غير مدعومة. المتاح: `ton`، `usdt`.

link-wallet-request-invalid-address =
    ❌ العنوان `{ $address }` لا يبدو مثل عنوان TON. الصيغة المتوقعة: خام `workchain:hex64` أو سلسلة base64url ودية.

link-wallet-request-issued =
    🔗 <b>وقّع `ton_proof` عبر TON Connect</b>

    1. افتح محفظة متوافقة مع TON Connect (Tonkeeper, MyTonWallet, Tonhub) واتصل بالبوت.
    2. وقّع `ton_proof` بهذه المعلمات:
       • <code>domain</code> = <code>{ $domain }</code>
       • <code>payload</code> = <code>{ $nonce }</code>
    3. لديك <b>{ $expires_at_minutes }</b> دقيقة — بعدها ينتهي الـ nonce ويجب أن تبدأ من جديد.
    4. خذ رد المحفظة بصيغة JSON وشغّل `/link_wallet_confirm { $currency } { $address } <proof-json>`.

# /claim_prize <lot_id> (Sprint 4.1-D, D.7)
claim-prize-group = أمر `/claim_prize` متاح فقط في الرسائل الخاصة مع البوت. افتح المحادثة الخاصة.
claim-prize-other = أمر `/claim_prize` متاح فقط في الرسائل الخاصة مع البوت.
claim-prize-not-registered = سجّل أولاً — اضغط /start في الرسائل الخاصة مع البوت.

claim-prize-usage =
    الاستخدام: `/claim_prize <lot_id>`.

    `lot_id` هو معرّف الحصة المحجوزة من نتيجة الروليت. الدفع يذهب للمحفظة المرتبطة.

claim-prize-invalid-lot-id = `lot_id` يجب أن يكون عدداً صحيحاً موجباً. حصلت على: `{ $raw }`.

claim-prize-prompt =
    🎁 <b>جائزة كريبتو محجوزة — حصة #{ $lot_id }</b>

    العملة: `{ $currency }`. المبلغ: `{ $amount }` (وحدات أصلية).
    اضغط الزر أدناه للسحب إلى المحفظة المرتبطة (أو شغّل /link_wallet أولاً).

claim-prize-button = المطالبة بالجائزة

claim-prize-not-found = الحصة #{ $lot_id } غير موجودة. إما أنها طُولب بها بالفعل أو غير موجودة.

claim-prize-already-claimed = الحصة #{ $lot_id } تم دفعها بالفعل. لا يمكن المطالبة بها مرة أخرى.

claim-prize-not-reserved =
    الحصة #{ $lot_id } حالياً في الحالة `{ $status }`، وليست `reserved`.
    فقط الحصص المحجوزة يمكن سحبها عبر `/claim_prize`.

claim-prize-wallet-not-linked =
    لا محفظة مرتبطة للعملة `{ $currency }`. شغّل /link_wallet أولاً ثم عُد للمطالبة بالحصة.

claim-prize-not-owner = الحصة #{ $lot_id } لا تخصّك.

claim-prize-success =
    ✅ <b>تم إرسال الدفع — حصة #{ $lot_id }</b>

    العملة: `{ $currency }`. المبلغ: `{ $amount }`.
    رسوم الشبكة: `{ $actual_fee }`. المحفظة: `{ $address }`.
    هاش المعاملة: `{ $tx_hash }`.

claim-prize-refund =
    ⚠ <b>حصة #{ $lot_id } أُعيدت إلى المجمّع</b>

    رسوم الشبكة `{ $actual_fee }` تجاوزت الحاجز `{ $fee_buffer }` لـ `{ $currency } { $amount }`. الحصة ستعود إلى المجمّع وتعاود الظهور عندما تنخفض الرسوم.

claim-prize-invalid-callback = الزر لا يعمل. شغّل `/claim_prize <lot_id>` يدوياً.
claim-prize-toast-invalid = انتهت صلاحية الزر. استخدم `/claim_prize <lot_id>`.

# ───────────────────────────────────────────────────────────────────────────
# Sprint 4.1-E.12 — /prize_pool
# ───────────────────────────────────────────────────────────────────────────
admin-prize-pool-not-authorized = ❌ لقطة المجمّع الكريبتو متاحة فقط للمشرف الأعلى.
admin-prize-pool-header = 💰 <b>لقطة المجمّع الكريبتو</b>
admin-prize-pool-row =
    • <code>{ $currency }</code> · الرصيد=<code>{ $balance }</code> · نشط=<code>{ $active }</code> · محجوز=<code>{ $reserved }</code> · مطالَب=<code>{ $claimed }</code> · مُعاد=<code>{ $refunded }</code>
admin-prize-pool-unfrozen = ❄️ تجميد المدفوعات الكريبتو: <b>مُعطّل</b>.
admin-prize-pool-frozen =
    🧊 تجميد المدفوعات الكريبتو: <b>مُفعّل</b>.
    بواسطة: admin_id=<code>{ $admin_id }</code>
    في: <code>{ $frozen_at }</code>
    السبب: { $reason }

# ───────────────────────────────────────────────────────────────────────────
# Sprint 4.1-E.13 — /refund_lot
# ───────────────────────────────────────────────────────────────────────────
admin-refund-lot-usage = ⚠️ الاستخدام: <code>/refund_lot &lt;lot_id&gt; &lt;reason&gt;</code>. كلا الوسيطين مطلوبان.
admin-refund-lot-not-authorized = ❌ فقط المشرفون الأعلى يمكنهم إعادة حصص الجوائز قسرياً.
admin-refund-lot-totp-not-configured = ❌ TOTP غير مُعدّ. <code>/refund_lot</code> غير متاح حتى تشغّل <code>/admin_setup_totp</code>.
admin-refund-lot-bad-lot-id = ⚠️ <code>{ $value }</code> ليس معرّف lot_id صالح (عدد صحيح موجب).
admin-refund-lot-no-reason = ⚠️ السبب مطلوب. الاستخدام: <code>/refund_lot &lt;lot_id&gt; &lt;reason&gt;</code>.
admin-refund-lot-confirm-issued = 🛡️ أكّد الإعادة. ردّ: <code>/confirm { $token } &lt;6-digit code&gt;</code>. ينتهي التوكن بعد { $ttl_seconds } ثانية.
admin-refund-lot-success = ✅ الحصة <code>#{ $lot_id }</code> ({ $currency } <code>{ $amount }</code>) أُعيدت إلى المجمّع. رصيد المجمّع بعد الإعادة: <code>{ $pool_after }</code>.
admin-refund-lot-already-refunded = ℹ️ الحصة <code>#{ $lot_id }</code> أُعيدت بالفعل. رصيد المجمّع: <code>{ $pool_after }</code>.
admin-refund-lot-not-found = 🔍 الحصة <code>#{ $lot_id }</code> غير موجودة.
admin-refund-lot-bad-transition = 🚫 الحصة <code>#{ $lot_id }</code> في الحالة <code>{ $status }</code> — الإعادة عبر <code>/refund_lot</code> غير مسموحة (انظر GDD §12.6.6).

# ───────────────────────────────────────────────────────────────────────────
# Sprint 4.1-E.14 — /freeze_payouts + /unfreeze_payouts
# ───────────────────────────────────────────────────────────────────────────
admin-freeze-payouts-usage = ⚠️ الاستخدام: <code>/freeze_payouts &lt;reason&gt;</code>. السبب مطلوب.
admin-freeze-payouts-not-authorized = ❌ فقط المشرفون الأعلى يمكنهم تجميد المدفوعات الكريبتو.
admin-freeze-payouts-totp-not-configured = ❌ TOTP غير مُعدّ. <code>/freeze_payouts</code> غير متاح حتى تشغّل <code>/admin_setup_totp</code>.
admin-freeze-payouts-no-reason = ⚠️ السبب مطلوب. الاستخدام: <code>/freeze_payouts &lt;reason&gt;</code>.
admin-freeze-payouts-confirm-issued = 🛡️ أكّد تجميد المدفوعات. ردّ: <code>/confirm { $token } &lt;6-digit code&gt;</code>. ينتهي التوكن بعد { $ttl_seconds } ثانية.
admin-freeze-payouts-success = ✅ المدفوعات الكريبتو مجمّدة الآن. السبب: { $reason }
admin-freeze-payouts-already-frozen = ℹ️ المدفوعات الكريبتو مجمّدة بالفعل بواسطتك بنفس السبب — لا شيء للفعل. السبب: { $reason }

admin-unfreeze-payouts-not-authorized = ❌ فقط المشرفون الأعلى يمكنهم إلغاء تجميد المدفوعات الكريبتو.
admin-unfreeze-payouts-totp-not-configured = ❌ TOTP غير مُعدّ. <code>/unfreeze_payouts</code> غير متاح حتى تشغّل <code>/admin_setup_totp</code>.
admin-unfreeze-payouts-confirm-issued = 🛡️ أكّد إلغاء تجميد المدفوعات. ردّ: <code>/confirm { $token } &lt;6-digit code&gt;</code>. ينتهي التوكن بعد { $ttl_seconds } ثانية.
admin-unfreeze-payouts-success = ✅ المدفوعات الكريبتو مسموحة مرة أخرى الآن.
admin-unfreeze-payouts-already-unfrozen = ℹ️ المدفوعات الكريبتو لم تكن مجمّدة — لا شيء لإلغاء تجميده.
