# Bot localization for "Pipirik Wars" — ES (Spanish).
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

start-registered = 🍆 ¡Listo! Te has registrado en Pipirik Wars.

    La longitud inicial es de 2 cm, el grosor es nivel 1. Tu nombre y título aparecerán más tarde — en tu primera ida al bosque.

start-already = 🍆 Ya estás registrado. Usa /profile para ver tu tarjeta.

start-group = 🍆 ¡"Pipirik Wars" está aquí!

    1. Primero, regístrate en el chat privado del bot: abre un DM y pulsa /start.
    2. Luego añádeme a un grupo como administrador — esto convierte el chat en un clan.

start-other = 🍆 "Pipirik Wars" está aquí. El comando /start funciona en DM o en un grupo.

start-queued = 🍆 Los servidores están llenos — te pusimos en la cola.

    Tu posición: #{ $position }.
    En cuanto se libere un hueco, te registraremos y te enviaremos una notificación.

start-registered-with-referral = 🍆 ¡Listo! Te has registrado en Pipirik Wars.

    La longitud inicial es de 2 cm + <b>{ $bonus_cm } cm de bonificación por llegar mediante un enlace de referido</b>. El grosor es nivel 1. Tu nombre y título aparecerán más tarde — en tu primera ida al bosque.

## /profile

profile-group = 🍆 El comando /profile solo funciona en el DM del bot. Abre un chat privado e inténtalo de nuevo.

profile-other = 🍆 El comando /profile solo funciona en el DM del bot.

profile-not-registered = 🍆 Parece que aún no estás registrado. Pulsa /start en este chat y aparecerá tu tarjeta.

profile-title-newbie = Novato
profile-title-ataman = Atamán Bandido

profile-card =
    🏷 { $nick }

    📏 Longitud: { $length_cm } cm
    📐 Grosor: { $thickness_level }

    🎽 Equipo: vacío por ahora

## /top

top-header = 🏆 <b>Top de Pipirik</b>

top-empty = 🏆 El top está vacío por ahora. ¡Sé el primero — pulsa /start!

top-entry = { $rank }. { $nick } — { $length_cm } cm

## /clantop

clantop-header = 🛡 <b>Top de Clanes</b>

clantop-empty = 🛡 Aún no hay clanes en el top. ¡Añade el bot a un grupo — y registra tu clan!

clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } cm ({ $member_count } 👥)

## /forest

forest-group = 🍆 El comando /forest solo está disponible en el chat privado del bot. Abre el DM e inténtalo de nuevo.

forest-other = 🍆 El comando /forest solo está disponible en el chat privado del bot.

forest-not-registered = 🍆 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás ir al bosque.

forest-already-in = 🌲 Ya estás en el bosque — espera tu regreso. El bot enviará un mensaje cuando el viaje termine.

forest-started = 🌲 { $nick } se fue al bosque por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...

forest-started-fallback = 🌲 Te fuiste al bosque por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...

forest-finished-header = 🌲 ¡{ $nick } regresó del bosque!

forest-finished-length =
    📏 Longitud: +{ NUMBER($length_delta_cm, useGrouping: 0) } cm (era { NUMBER($length_before_cm, useGrouping: 0) }, ahora { NUMBER($length_after_cm, useGrouping: 0) })

forest-finished-title-granted = 🎖 Título obtenido: Novato

forest-rarity-common = común
forest-rarity-rare = raro
forest-rarity-epic = épico

## /lang

lang-group = El comando `/lang` es solo para chat privado. Abre el DM.

lang-other = El comando `/lang` es solo para usuarios normales.

lang-not-registered = Pulsa /start primero, luego ejecuta /lang ru|en|pt|es|tr|id|fa|uk|ar.

lang-usage = Uso: /lang ru|en|pt|es|tr|id|fa|uk|ar.

lang-unsupported = El idioma `{ $code }` no es compatible. Disponibles: ru, en, pt, es, tr, id, fa, uk, ar.

lang-set-es = Idioma de la interfaz cambiado a español. Todas las respuestas y mensajes en segundo plano ahora estarán en español.
lang-set-ar = تم تغيير لغة الواجهة إلى العربية. جميع الردود والرسائل في الخلفية ستكون الآن باللغة العربية.
