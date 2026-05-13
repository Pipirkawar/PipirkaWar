# Bot localization for "Pipirik Wars" — ES (Spanish, full version).
#
# Complete Spanish localization covering all ~1600 keys from en.ftl.
# Latin American Spanish (es-MX style — `tú` form, no `vosotros`).
#
# Conventions:
# - Keys grouped by module: `start_*`, `profile_*`, `forest_*`, etc.
# - Parameters: Fluent placeholders `{ $name }` (BCP-47 / Mozilla Fluent).
# - HTML tags allowed in values (bot uses parse_mode=HTML), but prefer
#   only `<b>`/`<i>` to keep migration to other parse_modes simple.
# - Indentation: 4 spaces for continuation lines.

## /start (Sprint 1.1.C → 1.1.D → 1.2.4 DAU Gate)

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

# Referral arrival (Sprint 2.4.D, GDD §13.1).
# Parameters:
# - `$bonus_cm` — how many cm the newcomer got on top of the starting
#   length (`balance.referral.on_signup.newbie_bonus_cm`, default 5).
start-registered-with-referral = 🍆 ¡Listo! Te has registrado en Pipirik Wars.

    La longitud inicial es de 2 cm + <b>{ $bonus_cm } cm de bonificación por llegar mediante un enlace de referido</b>. El grosor es nivel 1. Tu nombre y título aparecerán más tarde — en tu primera ida al bosque.

## /profile (Sprint 1.1.E → 1.5.C)

profile-group = 🍆 El comando /profile solo funciona en el DM del bot. Abre un chat privado e inténtalo de nuevo.

profile-other = 🍆 El comando /profile solo funciona en el DM del bot.

profile-not-registered = 🍆 Parece que aún no estás registrado. Pulsa /start en este chat y aparecerá tu tarjeta.

# Localized title names from `domain.player.value_objects.Title`.
# Keys mirror enum values: `Title.NEWBIE = "newbie"` → `profile-title-newbie`.
profile-title-newbie = Novato
profile-title-ataman = Atamán Bandido

# Player card from GDD §2.2. Parameters:
# - `$nick` — assembled "Title DisplayName Name" (built by presenter)
# - `$length_cm` — integer, cm
# - `$thickness_level` — integer, level
profile-card =
    🏷 { $nick }

    📏 Longitud: { $length_cm } cm
    📐 Grosor: { $thickness_level }

    🎽 Equipo: vacío por ahora

## /top (Sprint 1.4.C → 1.5.C)

top-header = 🏆 <b>Top de Pipirik</b>

top-empty = 🏆 El top está vacío por ahora. ¡Sé el primero — pulsa /start!

# Single row in the top: "<rank>. Title DisplayName Name — N cm".
top-entry = { $rank }. { $nick } — { $length_cm } cm

## /clantop (Sprint 2.2.A)

clantop-header = 🛡 <b>Top de Clanes</b>

clantop-empty = 🛡 Aún no hay clanes en el top. ¡Añade el bot a un grupo — y registra tu clan!

# Single row in the clan top: "<rank>. ClanTitle — N cm (M 👥)".
clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } cm ({ $member_count } 👥)

## /oracle (Sprint 1.4.B → 1.5.D, extended in 3.6-B; GDD §11, §11.1)

oracle-group = 🔮 El comando /oracle solo funciona en el DM del bot. Abre un chat privado e inténtalo de nuevo.

oracle-other = 🔮 El comando /oracle solo funciona en el DM del bot.

oracle-not-registered = 🔮 Parece que aún no estás registrado. Pulsa /start en este chat y el oráculo te escuchará.

# Success header: prediction-of-the-day + template text. Parameters:
# - `$prediction` — prediction text, already with `{ user }` substituted
oracle-success-prediction =
    🔮 Predicción del día:
    { $prediction }

# Base length grant (always, GDD §11). Parameters:
# - `$base_cm` — integer, base roll 1..20 cm
oracle-base-line = 📏 +{ NUMBER($base_cm, useGrouping: 0) } cm — base

# Tribe bonus (only when `n_active_tribes > 0`, Sprint 3.6-B / GDD §11.1).
# Parameters:
# - `$tribe_bonus_cm` — integer, length bonus from tribes
# - `$n_active_tribes` — integer, number of active tribes the player is in
# Plural by `$n_active_tribes` (CLDR ES): 1 → tribu, otherwise → tribus.
oracle-tribe-bonus-line = 🛡 +{ NUMBER($tribe_bonus_cm, useGrouping: 0) } cm — bono de tribu ({ NUMBER($n_active_tribes, useGrouping: 0) } { $n_active_tribes ->
        [one] tribu
       *[other] tribus
    })

# Total length grant for this call (only when `n_active_tribes > 0`).
# Parameters: `$total_cm` — integer, `base_cm + tribe_bonus_cm`.
oracle-total-line = ✨ Total: +{ NUMBER($total_cm, useGrouping: 0) } cm

# New player length after applying the grant/cap (always).
# Parameters: `$new_length_cm` — integer.
oracle-new-length-line = Ahora tienes: { NUMBER($new_length_cm, useGrouping: 0) } cm

# "Come back tomorrow" message. Parameters:
# - `$hours` — integer, hours until 00:00 Moscow reset
# - `$minutes` — integer 0-59, minutes (`%02d` formatting done by presenter)
oracle-already-used =
    🔮 Ya visitaste al oráculo hoy.
    Vuelve en { NUMBER($hours, useGrouping: 0) }h { $minutes }m (00:00 hora de Moscú).

## /upgrade (Sprint 1.4.A → 1.5.D)

upgrade-group = 🍆 El comando /upgrade solo funciona en el DM del bot. Abre un chat privado e inténtalo de nuevo.

upgrade-other = 🍆 El comando /upgrade solo funciona en el DM del bot.

upgrade-not-registered = 🍆 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás mejorar.

# "Upgrade from N to N+1" proposal card. Parameters:
# - `$current_thickness` — integer, current level
# - `$next_thickness` — integer, target level (current+1)
# - `$cost_cm` — integer, cost in cm
# - `$current_length_cm` — integer, current player length
# - `$remaining_cm` — integer, what's left after deduction
# - `$min_after_spend_cm` — integer, lower bound from 20 cm rule
upgrade-proposal =
    📐 Mejora de grosor
    Nivel actual: { NUMBER($current_thickness, useGrouping: 0) }
    Nivel objetivo: { NUMBER($next_thickness, useGrouping: 0) }
    Costo: { NUMBER($cost_cm, useGrouping: 0) } cm
    Tienes: { NUMBER($current_length_cm, useGrouping: 0) } cm
    Restante: { NUMBER($remaining_cm, useGrouping: 0) } cm (mínimo por la regla de 20 cm: { NUMBER($min_after_spend_cm, useGrouping: 0) })

# Success message "Thickness upgraded". Parameters:
# - `$new_thickness`, `$cost_cm`, `$new_length_cm`.
upgrade-success =
    ✅ ¡Grosor mejorado a { NUMBER($new_thickness, useGrouping: 0) }!
    📏 Gastado: { NUMBER($cost_cm, useGrouping: 0) } cm
    Restante: { NUMBER($new_length_cm, useGrouping: 0) } cm

# "Insufficient length" rejection card. Parameters:
# - `$next_thickness`, `$cost_cm`, `$current_length_cm`,
# - `$min_after_spend_cm`, `$deficit_cm`.
upgrade-insufficient =
    ❌ Longitud insuficiente para mejorar a { NUMBER($next_thickness, useGrouping: 0) }.
    Costo: { NUMBER($cost_cm, useGrouping: 0) } cm
    Tienes: { NUMBER($current_length_cm, useGrouping: 0) } cm
    Mínimo restante: { NUMBER($min_after_spend_cm, useGrouping: 0) } cm
    Te faltan: { NUMBER($deficit_cm, useGrouping: 0) } cm

upgrade-cancelled = Mejora cancelada.

upgrade-race = ⚠️ El costo de la mejora ha cambiado — abre /upgrade de nuevo para ver el actual.

# Inline button label "Confirm (X cm)". Parameter `$cost_cm`.
upgrade-button-confirm = Confirmar ({ NUMBER($cost_cm, useGrouping: 0) } cm)

upgrade-button-cancel = Cancelar

# Toasts for callback responses (Telegram limit ≤ 200 chars).
upgrade-toast-upgraded = Grosor mejorado.

upgrade-toast-cancelled = Mejora cancelada.

upgrade-toast-player-not-found = Pulsa /start primero.

upgrade-toast-insufficient = Longitud insuficiente.

upgrade-toast-race = Costo cambiado.

# Anti-cheat soft-ban gate on /upgrade (Sprint 1.6.E, ГДД §3.3.5).
# `$banned-until` is an ISO-8601 string of the ban-expiration moment (UTC, tz-aware).
upgrade-anticheat-blocked = La mejora está temporalmente congelada. La verificación anti-trampas está activa hasta { $banned-until }.

upgrade-toast-anticheat-blocked = Verificación anti-trampas activa.

# Compressed "Insufficient length" used to replace message text after a
# callback click (without the full card — handler doesn't know the
# fresh thickness without re-fetching the profile).
upgrade-insufficient-short =
    ❌ Longitud insuficiente.
    Costo: { NUMBER($cost_cm, useGrouping: 0) } cm
    Tienes: { NUMBER($current_length_cm, useGrouping: 0) } cm
    Mínimo restante: { NUMBER($min_after_spend_cm, useGrouping: 0) } cm
    Te faltan: { NUMBER($deficit_cm, useGrouping: 0) } cm

## /forest (Sprint 1.3.D → 1.5.E)

forest-group = 🍆 El comando /forest solo está disponible en el chat privado del bot. Abre el DM e inténtalo de nuevo.

forest-other = 🍆 El comando /forest solo está disponible en el chat privado del bot.

forest-not-registered = 🍆 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás ir al bosque.

forest-already-in = 🌲 Ya estás en el bosque — espera tu regreso. El bot enviará un mensaje cuando el viaje termine.

# "Went to the forest" start message (GDD §8.2). Parameters:
# - `$nick` — assembled "Title Name PlayerName" (via presenter)
# - `$cooldown_minutes` — integer, minutes until return
forest-started = 🌲 { $nick } se fue al bosque por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...

# Fallback message when `GetProfile` couldn't find the player right after
# `StartForestRun` — parameter `$cooldown_minutes`.
forest-started-fallback = 🌲 Te fuiste al bosque por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...

# "Returned from forest" message — header and length line (GDD §8.2).
# Parameters:
# - `$nick` — full nick "Title Name PlayerName" with recomputed DisplayName
# - `$length_delta_cm` — integer, +N cm gained in the forest
# - `$length_before_cm` / `$length_after_cm` — integers, before/after
forest-finished-header = 🌲 ¡{ $nick } regresó del bosque!
forest-finished-length =
    📏 Longitud: +{ NUMBER($length_delta_cm, useGrouping: 0) } cm (era { NUMBER($length_before_cm, useGrouping: 0) }, ahora { NUMBER($length_after_cm, useGrouping: 0) })

# `{delta}` substitution for forest flavour log templates (Sprint 1.5.G,
# GDD §15). `$length_delta_cm` — integer; format mirrors `+N cm` in
# `forest-finished-length`. Kept as a separate key so localizers can
# change units / sign for future languages without touching templates.
forest-flavour-delta = +{ NUMBER($length_delta_cm, useGrouping: 0) } cm

# Title "Newbie" granted (first forest return, GDD §8.2).
forest-finished-title-granted = 🎖 Título obtenido: Novato

# Parameter `$item_name` — display_name of the item,
# `$rarity` — localized rarity (see forest-rarity-*).
forest-finished-item-found = 🎩 Encontrado: { $item_name } [{ $rarity }]

# Name granted automatically (newbie without a name yet). Parameter `$name`.
forest-finished-name-granted = 🪪 Nombre recibido: { $name }

# Name offered for replacement (player already has a name). Parameter `$name`.
forest-finished-name-found = 🪪 Nombre encontrado: { $name }

# Localized rarities (UI "Found: <item> [<rarity>]").
forest-rarity-common = común
forest-rarity-rare = raro
forest-rarity-epic = épico

# Inline button labels under the "returned from forest" message.
forest-button-equip = Equipar
forest-button-drop-item = Descartar
forest-button-replace-name = Reemplazar
forest-button-drop-name = Descartar

# Toasts for callback responses (Telegram limit ≤ 200 chars).
forest-toast-name-applied = Nombre reemplazado.
forest-toast-name-already-applied = El nombre ya fue aplicado.
forest-toast-name-dropped = Nombre descartado.
forest-toast-item-dropped = Objeto descartado.
forest-toast-item-equipped-placeholder = El equipo vendrá después — el objeto está en tu inventario por ahora.
forest-toast-foreign-button = Este botón no es para ti.
forest-toast-run-not-found = Esta expedición al bosque ya no está activa.
forest-toast-drop-mismatch = Botón desactualizado.
forest-toast-player-not-found = Pulsa /start primero.

# ----------------------------- /lang -----------------------------
# `/lang ru|en` — interface language switcher (Sprint 1.5.F).

# Command called outside a private chat.
lang-group = El comando `/lang` es solo para chat privado. Abre el DM.

# Command called from a non-user (e.g., from a channel).
lang-other = El comando `/lang` es solo para usuarios normales.

# Player is not registered yet.
lang-not-registered = Pulsa /start primero, luego ejecuta /lang ru|en|pt|es|tr|id|fa|uk.

# Usage hint when args are missing/invalid.
lang-usage = Uso: /lang ru|en|pt|es|tr|id|fa|uk.

# Unsupported language code passed.
lang-unsupported = El idioma `{ $code }` no es compatible. Disponibles: ru, en, pt, es, tr, id, fa, uk.

# Locale switched successfully. Each `lang-set-<code>` is rendered in its
# own locale (the one the user just switched to), so the player sees the
# confirmation in the new language. See `bot/presenters/lang.py`.
lang-set-ru = Язык интерфейса: русский. Все ответы и фоновые сообщения теперь на русском.
lang-set-en = Interface language switched to English. All replies and background messages will be in English.
lang-set-pt = Idioma da interface alterado para português. Todas as respostas e mensagens em segundo plano agora serão em português.
lang-set-es = Idioma de la interfaz cambiado a español. Todas las respuestas y mensajes en segundo plano ahora estarán en español.
lang-set-tr = Arayüz dili Türkçe olarak değiştirildi. Tüm yanıtlar ve arka plan mesajları artık Türkçe olacak.
lang-set-id = Bahasa antarmuka diubah ke Bahasa Indonesia. Semua balasan dan pesan latar belakang sekarang akan dalam Bahasa Indonesia.
lang-set-fa = زبان رابط به فارسی تغییر یافت. تمام پاسخ‌ها و پیام‌های پس‌زمینه اکنون به فارسی خواهد بود.
lang-set-uk = Мову інтерфейсу змінено на українську. Усі відповіді та фонові повідомлення тепер будуть українською.


# Anti-cheat hardcap (Sprint 1.6.D, GDD §3.3).
# Player attempted a length-granting action but is in a soft-ban.
# `$banned-until` — ISO string of ban expiration moment (UTC, tz-aware).
anticheat-soft-ban-active = La verificación anti-trampas está activa hasta { $banned-until }. El crecimiento de longitud está temporalmente congelado.

# Part of the requested delta was clamped by the daily cap.
# `$applied` — actually applied cm; `$requested` — originally requested.
anticheat-cap-clamped-daily = Límite diario de crecimiento casi alcanzado. Se aplicaron { NUMBER($applied, useGrouping: 0) } cm de { NUMBER($requested, useGrouping: 0) } cm.

# Part of the requested delta was clamped by the weekly cap.
anticheat-cap-clamped-weekly = Límite semanal de crecimiento casi alcanzado. Se aplicaron { NUMBER($applied, useGrouping: 0) } cm de { NUMBER($requested, useGrouping: 0) } cm.


# /anticheat_unban (Sprint 1.6.G, GDD §3.3) — admin command.
# Shown when command format is invalid.
anticheat-unban-usage = ⚠️ Uso: `/anticheat_unban <tg_id> <razón>`. La razón es obligatoria.

# Not an admin (or role below super_admin).
anticheat-unban-not-authorized = ❌ No tienes permiso para este comando. Levantar un ban anti-trampas solo está disponible para super_admin activos.

# Target player is not registered.
anticheat-unban-player-not-found = ❌ El jugador con tg_id { $tg_id } no está registrado.

# Ban is not active (None or already expired) — idempotent no-op.
anticheat-unban-not-banned = ℹ️ El jugador tg_id { $tg_id } no tiene un ban anti-trampas activo. No se requiere acción.

# Ban successfully lifted. `$banned-until-before` — ISO string of previous ban expiration.
anticheat-unban-success = ✅ Ban anti-trampas levantado (tg_id { $tg_id }, estaba baneado hasta { $banned-until-before }). Razón: { $reason }.


# ──────────────────────────────────────────────────────────────────────────
# 1×1 PvP duel (Sprint 2.1.E, GDD §7.1).
# ──────────────────────────────────────────────────────────────────────────

# /duel in private chat without reply — challenge is auto-queued to the global pool.
# Kept as fallback for compatibility; the active flow uses duel-global-enqueued.
duel-private-needs-global = 🍆 Para desafiar a alguien, responde /duel a su mensaje en un chat grupal. O espera — tu `/duel` en chat privado ya fue enviado al pool global.

# /duel without reply in a group, or with invalid arguments.
duel-usage = 🍆 Uso: responde `/duel` al mensaje de tu oponente. El modo por defecto es chat → global. Para solo chat — `/duel chat`. En chat privado, `/duel` sin argumentos te pone en el pool global.

# Player (challenger) isn't registered yet.
duel-not-registered = 🍆 Aún no estás registrado. Pulsa /start primero.

# Opponent isn't registered yet.
duel-target-not-registered = 🍆 Tu oponente aún no está registrado — pídele que inicie /start con el bot.

# Reply on a bot message — not allowed.
duel-target-is-bot = 🍆 Solo puedes desafiar a un jugador real, no a un bot.

# Reply on own message — not allowed.
duel-self-challenge = 🍆 ¿Desafiarte a ti mismo? Busca un oponente de verdad.

# Challenge card in chat (chat_only mode). $challenger / $challenged — @username.
duel-challenge-chat = ⚔️ ¡{ $challenger } desafía a { $challenged } a un duelo (solo chat)! ¿Aceptas?

# Challenge card in chat (chat_then_global mode).
duel-challenge-chat-then-global = ⚔️ ¡{ $challenger } desafía a { $challenged } a un duelo! Si no se acepta en 3 minutos, el desafío pasará al pool global.

# Notification that challenge has been sent to the global pool (global_only).
duel-challenge-global = ⚔️ { $challenger }, tu desafío fue enviado al pool global — esperando hasta { NUMBER($ttl_minutes, useGrouping: 0) } min.

# Private-chat notification after `/duel` without args — enqueued in global pool.
duel-global-enqueued = ⚔️ Desafío enviado al pool global. Esperando que alguien use /duel_global. Expira en { NUMBER($ttl_minutes, useGrouping: 0) } min — cancela manualmente con /cancel_duel { $duel_id }.

# Private-chat reply after `/duel_global` — successful match.
duel-global-matched = ⚔️ ¡Emparejado con { $challenger }! Pelea iniciada — espera las rondas en chat privado.

# Private-chat reply after `/duel_global` — lobby empty (or race with self-challenge).
duel-global-empty = 🪂 El pool global está vacío. Inténtalo después o envía un desafío con /duel.

# `/duel_global` outside private chat — disallowed.
duel-global-only-in-private = 🤖 `/duel_global` solo funciona en chat privado — los oponentes no deben exponerse públicamente.

# Replaces challenge card after accept.
duel-chat-accepted = ✅ { $challenged } aceptó el desafío de { $challenger }. Pelea en curso (privado).

# Inline buttons.
duel-button-accept = Aceptar
duel-button-reject = Rechazar
duel-button-attack-high = Ataque: ⬆ alto
duel-button-attack-mid = Ataque: ➡ medio
duel-button-attack-low = Ataque: ⬇ bajo
duel-button-block-high = Bloqueo: ⬆ alto
duel-button-block-mid = Bloqueo: ➡ medio
duel-button-block-low = Bloqueo: ⬇ bajo

# Round prompt (DM).
duel-round-attack-prompt = 🥊 Ronda { NUMBER($round_num, useGrouping: 0) } de 3. ¿Dónde golpeas?

# Block-selection prompt (after attack).
duel-round-block-prompt = 🛡 Ronda { NUMBER($round_num, useGrouping: 0) } de 3. Ataque: { $attack }. ¿Qué bloqueas?

# Player has moved — waiting for opponent.
duel-round-waiting = ⏳ Ronda { NUMBER($round_num, useGrouping: 0) } — movimiento aceptado. Esperando al oponente…

# Final result.
duel-result-victory = 🏆 ¡Victoria! +{ NUMBER($delta_cm, useGrouping: 0) } cm. Tu longitud ahora es { NUMBER($new_length_cm, useGrouping: 0) } cm.
duel-result-defeat = 💀 Derrota. { NUMBER($delta_cm, useGrouping: 0) } cm. Tu longitud ahora es { NUMBER($new_length_cm, useGrouping: 0) } cm.
duel-result-draw = 🤝 Empate. Longitud sin cambios — { NUMBER($length_cm, useGrouping: 0) } cm.

# Public result card (Sprint 2.1.H, GDD §15) — shareable summary.
# `$winner` / `$loser` — formatted `@username` / «—». In the draw variant —
# `$p1` / `$p2` (no winner).
duel-result-card-victory = ⚔️ Duelo terminado: { $winner } aplastó a { $loser } (+{ NUMBER($delta_cm, useGrouping: 0) } cm).
duel-result-card-draw = ⚔️ El duelo terminó en empate: { $p1 } y { $p2 } intercambiaron golpes sin daño.
duel-share-button = 📢 Compartir

# /cancel_duel.
duel-cancelled = ❌ Desafío cancelado por { $challenger }.
duel-cancel-usage = Uso: `/cancel_duel <duel_id>`. El ID aparece en la tarjeta del desafío.

# Toast notifications (callback_query answers).
duel-toast-accepted = ¡Desafío aceptado!
duel-toast-rejected = Gracias, no me interesa.
duel-toast-cancelled = Desafío cancelado.
duel-toast-not-found = Este duelo ya no está activo.
duel-toast-not-participant = Este duelo no es tuyo.
duel-toast-foreign-button = Este botón no es para ti.
duel-toast-invalid-state = El duelo ya no está en esa fase.
duel-toast-already-submitted = Ya hiciste tu movimiento en esta ronda.
duel-toast-outdated = Botón desactualizado.

# Pre-duel requirements not met.
duel-requirements-not-met = 📏 Los duelos requieren longitud ≥ { NUMBER($min_length_cm, useGrouping: 0) } cm y grosor ≥ { NUMBER($min_thickness_level, useGrouping: 0) }.

# Anti-cheat soft-ban active.
duel-anticheat-blocked = La verificación anti-trampas está activa hasta { $banned-until }. Los duelos están temporalmente congelados.

# Player is busy with another activity (forest etc.).
duel-lock-already-held = 🔒 Estás ocupado (ej., en /forest). Termina la actividad actual primero.

# === Mass PvP clan×clan (Sprint 2.2.F, GDD §7.2) ===

# /clan_attack — usage and base errors.
pvp-mass-needs-group-chat = ⚔️El comando `/clan_attack` solo funciona en chats grupales de clan. Ejecútalo desde el chat del clan que quieres atacar.
pvp-mass-not-registered = 🍆Regístrate primero con `/start` en el DM del bot.
pvp-mass-attacker-not-found = ❌Este chat no está vinculado a un clan registrado.
pvp-mass-attacker-not-member = 🚫Solo los miembros de este clan pueden atacar a otros clanes.
pvp-mass-target-not-found = ❌Chat objetivo no encontrado o no vinculado a un clan registrado.
pvp-mass-target-needed = Uso: `/clan_attack <chat_id>` o responde a un mensaje del chat del clan defensor.
pvp-mass-self-attack = 🤝No puedes atacar a tu propio clan.
pvp-mass-clan-frozen = 🧊Uno de los clanes está congelado — el duelo masivo es imposible.
pvp-mass-cooldown = ⏳El enfriamiento sigue activo: próximo ataque posible en { NUMBER($cooldown_hours, useGrouping: 0) } h.
pvp-mass-no-participants = 🪶Un bando no tiene participantes que cumplan los requisitos (longitud ≥ { NUMBER($min_length_cm, useGrouping: 0) } cm, grosor ≥ { NUMBER($min_thickness_level, useGrouping: 0) }).
pvp-mass-lock-already-held = 🔒Algunos participantes están ocupados con otra actividad. Inténtalo de nuevo en un minuto.

# Start card in the group chat.
pvp-mass-started = ⚔️Batalla de clanes: <b>{ $attacker }</b> × <b>{ $defender }</b>! Formación: { NUMBER($attacker_size, useGrouping: 0) } × { NUMBER($defender_size, useGrouping: 0) }. Todos los participantes recibieron instrucciones por DM. Temporizador de movimiento — { NUMBER($timer_seconds, useGrouping: 0) } seg.

# DM prompts.
pvp-mass-prompt-attack = ⚔️Batalla clan × clan. ¿Dónde golpeas?
pvp-mass-prompt-block = 🛡Ataque elegido: { $attack }. ¿Qué bloqueas?
pvp-mass-waiting = ⏳Tu movimiento fue aceptado. Esperando a los demás…

# Final result in DM to each participant.
pvp-mass-result-victory = 🏆¡Victoria! El clan <b>{ $clan }</b> ganó y tomó { NUMBER($total_dealt, useGrouping: 0) } cm. Tu delta: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } cm.
pvp-mass-result-defeat = 💀Derrota. El clan <b>{ $clan }</b> perdió, { NUMBER($total_lost, useGrouping: 0) } cm fueron para el enemigo. Tu delta: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } cm.
pvp-mass-result-draw = 🤝Empate. Nadie ganó por más. Tu delta: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } cm.

# Final card in chat.
pvp-mass-result-chat-victory = 🏆¡La batalla clan × clan terminó! El clan <b>{ $clan }</b> ganó y tomó { NUMBER($total_dealt, useGrouping: 0) } cm.
pvp-mass-result-chat-draw = 🤝La batalla clan × clan terminó en empate ({ NUMBER($total_dealt, useGrouping: 0) } cm infligidos por cada bando).

# Buttons.
pvp-mass-button-attack-high = ⬆️ Cabeza
pvp-mass-button-attack-mid = ↔ Cuerpo
pvp-mass-button-attack-low = ⬇️ Piernas
pvp-mass-button-block-high = 🛡⬆ Cabeza
pvp-mass-button-block-mid = 🛡↔ Cuerpo
pvp-mass-button-block-low = 🛡⬇ Piernas

# Toast notifications.
pvp-mass-toast-not-found = Esta batalla ya no está activa.
pvp-mass-toast-not-participant = No eres participante de esta batalla.
pvp-mass-toast-foreign-button = Este botón no es para ti.
pvp-mass-toast-invalid-state = La batalla ya terminó.
pvp-mass-toast-already-submitted = Ya hiciste tu movimiento.
pvp-mass-toast-outdated = Este botón está desactualizado.
pvp-mass-toast-attack-selected = Ataque elegido. Ahora elige un bloqueo.
pvp-mass-toast-move-accepted = ¡Movimiento aceptado!

## /clan_history (Sprint 2.2.G — clan attack journal)

clan-history-needs-group-chat = 📜 El comando `/clan_history` solo funciona en un chat grupal de clan.
clan-history-not-registered = 📜 Este chat no está registrado como clan. Usa /start para registrarte.
clan-history-header = 📜 <b>Historial de ataques del clan</b> ({ $clan_title })
clan-history-empty = 📜 El clan <b>{ $clan_title }</b> no tiene batallas masivas completadas aún.
# One journal row: "<idx>. ⚔ Opponent — victory +20 cm (3×3)".
clan-history-entry-victory = { $idx }. ⚔ { $opponent_clan_title } — 🏆 victoria +{ NUMBER($our_delta_cm, useGrouping: 0) } cm ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-defeat = { $idx }. ⚔ { $opponent_clan_title } — 💀 derrota { NUMBER($our_delta_cm, useGrouping: 0) } cm ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-draw = { $idx }. ⚔ { $opponent_clan_title } — 🤝 empate ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-cancelled = { $idx }. ⚔ { $opponent_clan_title } — ⛔ cancelada ({ $when })

## /clan_head (Sprint 2.3.E — daily clan head)

clan-head-needs-group-chat = 👑 El comando /clan_head solo funciona en un chat grupal de clan.
clan-head-not-registered = 👑 Este chat no está vinculado a un clan registrado. Usa /start para registrarte.
clan-head-frozen-clan = 👑 El clan está temporalmente congelado. No se puede asignar un líder.
clan-head-not-enough-active = 👑 Muy pocos miembros activos en el clan en los últimos 7 días (se necesitan al menos { NUMBER($required, useGrouping: 0) }, activos: { NUMBER($active_count, useGrouping: 0) }).
clan-head-success = 👑 <b>Líder del clan del día</b> — ¡{ $head_display_name }!
  +{ NUMBER($bonus_cm, useGrouping: 0) } cm de longitud (ahora { NUMBER($new_length_cm, useGrouping: 0) } cm).

  💬 <i>{ $quote_text }</i>
clan-head-already-assigned = 👑 El líder del clan de hoy ya fue asignado — { $head_display_name } (+{ NUMBER($bonus_cm, useGrouping: 0) } cm).

  💬 <i>{ $quote_text }</i>

## Referral-share button (Sprint 2.4.D-b, GDD §13.2)
# Button label under duel / forest results — shares result with referral link.
referral-share-button = 🔗 Compartir

# Text posted to chat when user clicks "Share" after a duel (victory).
# Parameters: $winner, $loser, $delta_cm, $winner_length_cm, $deeplink.
referral-share-duel-victory = ⚔️ PIPIRIK WARS — ¡Resultado de la batalla!
    ¡{ $winner } 🏆 ganó!
    ¡Robó { NUMBER($delta_cm, useGrouping: 0) } cm de { $loser }!
    📏 Nueva longitud: { NUMBER($winner_length_cm, useGrouping: 0) } cm

    🎮 Juega tú también → { $deeplink }

# Text for a draw.
# Parameters: $p1, $p2, $deeplink.
referral-share-duel-draw = ⚔️ PIPIRIK WARS — ¡Resultado de la batalla!
    Empate: { $p1 } y { $p2 } quedaron en igualdad de condiciones.

    🎮 Juega tú también → { $deeplink }

# Text posted to chat when user clicks "Share" after a forest run.
# Parameters: $player, $delta_cm, $length_cm, $deeplink.
referral-share-forest = 🌲 PIPIRIK WARS — ¡Expedición al bosque!
    ¡{ $player } regresó del bosque con { NUMBER($delta_cm, useGrouping: 0) } cm!
    📏 Nueva longitud: { NUMBER($length_cm, useGrouping: 0) } cm

    🎮 Juega tú también → { $deeplink }


## Weekly clan referral summary (Sprint 2.4.E, GDD §13.3)
# Card is posted to the clan chat on Sunday 18:00 UTC by cron.
# Parameters: $clan_title.
weekly-referral-summary-title = 📊 REPORTE SEMANAL — Clan "{ $clan_title }"
# Parameters: $total — total number of new clan referrals in the past week.
weekly-referral-summary-total = 👥 Nuevos referidos esta semana: { NUMBER($total, useGrouping: 0) }
# Parameters: $rank (1..3), $referrer_display_name, $count.
weekly-referral-summary-line = 🏆 { NUMBER($rank, useGrouping: 0) }. { $referrer_display_name } — trajo { NUMBER($count, useGrouping: 0) }
weekly-referral-summary-footer = ¡Invita a tus amigos — todos crecen juntos!


## Admin — support commands (Sprint 2.5-B, GDD §18.6.5)
# Used by `/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban` and the
# shared `/confirm` handler.

# /find_player <text>
admin-find-player-usage = ⚠️ Uso: <code>/find_player &lt;tg_id | @username | subcadena&gt;</code>. La consulta es obligatoria.
admin-find-player-not-authorized = ❌ Solo los administradores activos pueden buscar jugadores.
admin-find-player-empty = 🔍 No se encontraron jugadores para la consulta <code>{ $query }</code>.
admin-find-player-header = 🔍 { $count } jugador(es) encontrado(s) para la consulta <code>{ $query }</code>.
# Single row. Parameters: $tg_id, $username (or "—"), $name (or "—"),
#  $title (or "—"), $length_cm, $thickness_level, $status.
admin-find-player-row = • <code>{ $tg_id }</code> · @{ $username } · «{ $name }» · { $title } · L{ $length_cm }/T{ $thickness_level } · { $status }

# /player <tg_id>
admin-player-usage = ⚠️ Uso: <code>/player &lt;tg_id&gt;</code>. El argumento es obligatorio.
admin-player-not-authorized = ❌ Solo los administradores activos pueden ver tarjetas de jugadores.
admin-player-bad-id = ⚠️ <code>{ $value }</code> no es un tg_id válido (entero). Inténtalo de nuevo.
admin-player-not-found = 🔍 No existe un jugador con tg_id <code>{ $tg_id }</code>.
admin-player-card-summary = • <code>{ $tg_id }</code> · @{ $username } · «{ $name }» · { $title } · L{ $length_cm }/T{ $thickness_level } · { $status }
admin-player-card-clan = 🏰 Clan: <code>{ $title }</code> ({ $clan_status }) · rol { $role } · desde { $joined_at }
admin-player-card-no-clan = 🏰 Clan: —
admin-player-card-forest-active = 🌲 Expedición al bosque activa #{ $run_id }: desde { $started_at } hasta { $ends_at }.
admin-player-card-no-forest = 🌲 Sin expedición al bosque activa.
admin-player-card-anticheat = 🛡️ Ban anti-trampas hasta: { $until }.
admin-player-card-no-anticheat = 🛡️ Ban anti-trampas: no activo.

# /freeze
admin-freeze-usage = ⚠️ Uso: <code>/freeze &lt;tg_id&gt; [razón]</code>.
admin-freeze-not-authorized = ❌ Solo los administradores activos pueden congelar jugadores.
admin-freeze-bad-id = ⚠️ <code>{ $value }</code> no es un tg_id válido (entero).
admin-freeze-not-found = 🔍 No existe un jugador con tg_id <code>{ $tg_id }</code>.
admin-freeze-already = ❄️ El jugador <code>{ $tg_id }</code> ya está congelado.
admin-freeze-ok = 🥶 El jugador <code>{ $tg_id }</code> ha sido congelado.{ $reason_suffix }
admin-freeze-reason-suffix = Razón: { $reason }.

# /unfreeze
admin-unfreeze-usage = ⚠️ Uso: <code>/unfreeze &lt;tg_id&gt; [razón]</code>.
admin-unfreeze-not-authorized = ❌ Solo los administradores activos pueden descongelar jugadores.
admin-unfreeze-bad-id = ⚠️ <code>{ $value }</code> no es un tg_id válido (entero).
admin-unfreeze-not-found = 🔍 No existe un jugador con tg_id <code>{ $tg_id }</code>.
admin-unfreeze-already = ▶️ El jugador <code>{ $tg_id }</code> ya está activo.
admin-unfreeze-ok = ☀️ El jugador <code>{ $tg_id }</code> ha sido descongelado.{ $reason_suffix }
admin-unfreeze-reason-suffix = Razón: { $reason }.

# /ban — necessitates TOTP (B.4)
admin-ban-usage = ⚠️ Uso: <code>/ban &lt;tg_id&gt; &lt;razón&gt;</code>. La razón es obligatoria.
admin-ban-not-authorized = ❌ Solo los administradores activos pueden banear jugadores.
admin-ban-totp-not-configured = ❌ Tu TOTP no está configurado. `/ban` no está disponible.
admin-ban-bad-id = ⚠️ <code>{ $value }</code> no es un tg_id válido (entero).
admin-ban-no-reason = ⚠️ La razón es obligatoria. Uso: <code>/ban &lt;tg_id&gt; &lt;razón&gt;</code>.
admin-ban-not-found = 🔍 No existe un jugador con tg_id <code>{ $tg_id }</code>.
admin-ban-already = 🛑 El jugador <code>{ $tg_id }</code> ya está baneado.
admin-ban-confirm-issued = 🛡️ Confirma esta operación. Envía: <code>/confirm { $token } &lt;código de 6 dígitos&gt;</code>. TTL del token: { $ttl_seconds } seg.

# /confirm (B.5)
admin-confirm-usage = ⚠️ Uso: <code>/confirm &lt;token&gt; &lt;código de 6 dígitos&gt;</code>.
admin-confirm-not-authorized = ❌ Solo los administradores activos pueden confirmar operaciones.
admin-confirm-totp-not-configured = ❌ Tu TOTP no está configurado. La confirmación es imposible.
admin-confirm-token-not-found = ❌ El token <code>{ $token }</code> ya fue usado o no existe.
admin-confirm-token-expired = ⌛ Token expirado. Vuelve a ejecutar el comando.
admin-confirm-admin-mismatch = ❌ Este token pertenece a otro administrador.
admin-confirm-code-invalid = ❌ Código de 6 dígitos inválido.
admin-confirm-success-ban = ✅ El jugador <code>{ $tg_id }</code> ha sido baneado.
admin-confirm-success-ban-already = 🛑 El jugador <code>{ $tg_id }</code> ya estaba baneado.
admin-confirm-unknown-command-kind = ⚠️ Tipo de comando desconocido <code>{ $command_kind }</code> — actualiza el bot.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-C — economy commands (TOTP-protected except /balance_get)
# ─────────────────────────────────────────────────────────────────────────────

# /grant_length <tg_id> <±delta_cm> <reason>
admin-grant-length-usage = ⚠️ Uso: <code>/grant_length &lt;tg_id&gt; &lt;±delta_cm&gt; &lt;razón&gt;</code>. Los tres son obligatorios.
admin-grant-length-not-authorized = ❌ Solo los administradores activos pueden modificar la longitud.
admin-grant-length-totp-not-configured = ❌ Tu TOTP no está configurado. `/grant_length` no está disponible.
admin-grant-length-bad-id = ⚠️ <code>{ $value }</code> no es un tg_id válido (entero).
admin-grant-length-bad-delta = ⚠️ <code>{ $value }</code> no es un ±entero o es igual a 0.
admin-grant-length-no-reason = ⚠️ La razón es obligatoria. Uso: <code>/grant_length &lt;tg_id&gt; &lt;±delta_cm&gt; &lt;razón&gt;</code>.
admin-grant-length-not-found = 🔍 No existe un jugador con tg_id <code>{ $tg_id }</code>.
admin-grant-length-blocked = 🚫 No se puede modificar la longitud del jugador <code>{ $tg_id }</code>: { $reason }.
admin-grant-length-confirm-issued = 🛡️ Confirma esta operación. Envía: <code>/confirm { $token } &lt;código de 6 dígitos&gt;</code>. TTL del token: { $ttl_seconds } seg.
admin-grant-length-success = ✅ Jugador <code>{ $tg_id }</code>: aplicados { $delta } cm. Nueva longitud: { $new_length_cm } cm.
admin-grant-length-success-clamped = ⚠️ Jugador <code>{ $tg_id }</code>: solicitados { $requested } cm, aplicados { $applied } cm (límite 24h). Nueva longitud: { $new_length_cm } cm.
admin-grant-length-soft-ban = 🚫 El jugador <code>{ $tg_id }</code> está en soft-ban anti-trampas — operación rechazada.

# /grant_thickness <tg_id> <new_level> <reason>
admin-grant-thickness-usage = ⚠️ Uso: <code>/grant_thickness &lt;tg_id&gt; &lt;nuevo_nivel&gt; &lt;razón&gt;</code>.
admin-grant-thickness-not-authorized = ❌ Solo los administradores activos pueden modificar el grosor.
admin-grant-thickness-totp-not-configured = ❌ Tu TOTP no está configurado. `/grant_thickness` no está disponible.
admin-grant-thickness-bad-id = ⚠️ <code>{ $value }</code> no es un tg_id válido (entero).
admin-grant-thickness-bad-level = ⚠️ <code>{ $value }</code> no es un nivel (entero ≥ 1).
admin-grant-thickness-no-reason = ⚠️ La razón es obligatoria. Uso: <code>/grant_thickness &lt;tg_id&gt; &lt;nuevo_nivel&gt; &lt;razón&gt;</code>.
admin-grant-thickness-not-found = 🔍 No existe un jugador con tg_id <code>{ $tg_id }</code>.
admin-grant-thickness-blocked = 🚫 No se puede modificar el grosor del jugador <code>{ $tg_id }</code>: { $reason }.
admin-grant-thickness-level-invalid = ⚠️ Nivel <code>{ $level }</code> fuera de rango [1, { $max_level }] ({ $reason_code }).
admin-grant-thickness-confirm-issued = 🛡️ Confirma esta operación. Envía: <code>/confirm { $token } &lt;código de 6 dígitos&gt;</code>. TTL del token: { $ttl_seconds } seg.
admin-grant-thickness-success = ✅ Jugador <code>{ $tg_id }</code>: nivel de grosor establecido en { $new_level } (era { $previous_level }).
admin-grant-thickness-already-at-level = ℹ️ El jugador <code>{ $tg_id }</code> ya está en el nivel de grosor { $level }.

# /balance_get <key>
admin-balance-get-usage = ⚠️ Uso: <code>/balance_get &lt;clave.con.puntos&gt;</code>.
admin-balance-get-not-authorized = ❌ Solo los administradores activos pueden leer valores del balance.
admin-balance-get-key-not-found = ⚠️ Clave <code>{ $path }</code> no encontrada ({ $reason } en el segmento <code>{ $segment }</code>).
admin-balance-get-result = 📦 <code>{ $path }</code> = <code>{ $value }</code> (balance v{ $version }).

# /balance_set <key> <value> <reason>
admin-balance-set-usage = ⚠️ Uso: <code>/balance_set &lt;clave.con.puntos&gt; &lt;valor_json&gt; &lt;razón&gt;</code>.
admin-balance-set-not-authorized = ❌ Solo los administradores activos pueden modificar valores del balance.
admin-balance-set-totp-not-configured = ❌ Tu TOTP no está configurado. `/balance_set` no está disponible.
admin-balance-set-no-reason = ⚠️ La razón es obligatoria.
admin-balance-set-bad-value = ⚠️ <code>{ $value }</code> no es un fragmento JSON válido.
admin-balance-set-key-not-found = ⚠️ Clave <code>{ $path }</code> no encontrada ({ $reason } en el segmento <code>{ $segment }</code>).
admin-balance-set-validation-error = ❌ El valor para <code>{ $path }</code> no pasó la validación: { $error }.
admin-balance-set-confirm-issued = 🛡️ Confirma esta operación. Envía: <code>/confirm { $token } &lt;código de 6 dígitos&gt;</code>. TTL del token: { $ttl_seconds } seg.
admin-balance-set-success = ✅ Clave <code>{ $path }</code>: <code>{ $previous }</code> → <code>{ $new }</code> (balance v{ $version }).
admin-balance-set-already-at-value = ℹ️ La clave <code>{ $path }</code> ya tiene el valor <code>{ $value }</code>.

# Shared /confirm idempotency-replay
admin-idempotency-replay = ℹ️ Este comando (<code>{ $command_kind }</code>) ya fue ejecutado en el último minuto — repetición omitida.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.5 — read-side observability `/audit` (GDD §18.6.4)
# ─────────────────────────────────────────────────────────────────────────────

# /audit [target_tg_id|-] [action|-] [limit]
admin-audit-usage = ⚠️ Uso: <code>/audit [target_tg_id|-] [action|-] [límite]</code>. Todos los argumentos son opcionales; <code>-</code> significa "sin filtro".
admin-audit-not-authorized = ❌ Solo los administradores activos pueden inspeccionar el registro de auditoría.
admin-audit-bad-tg-id = ⚠️ <code>{ $value }</code> no es un tg_id válido (entero) ni <code>-</code>.
admin-audit-bad-limit = ⚠️ <code>{ $value }</code> no es un límite válido (entero > 0).
admin-audit-unknown-action = ⚠️ Categoría de acción desconocida <code>{ $value }</code>.
admin-audit-target-not-found = 🔍 No existe un administrador con tg_id <code>{ $tg_id }</code>.
# Params: $target (tg_id or "—"); $action (action filter or "—").
admin-audit-empty = 🗒️ No se encontraron registros (objetivo=<code>{ $target }</code>, acción=<code>{ $action }</code>).
# Header without target filter. $count — rows below, $limit — cap.
admin-audit-header-all = 🗒️ Registro de auditoría: { $count } registros más recientes (límite { $limit }, todos los admins).
# Header with target filter. $target_tg_id — admin tg_id.
admin-audit-header-target = 🗒️ Registro de auditoría del admin <code>{ $target_tg_id }</code>: { $count } registros más recientes (límite { $limit }).
# Appended to header if action filter is set.
admin-audit-filter-action-suffix = Filtro de acción: <code>{ $action }</code>.
# One list row. Params:
# $id, $occurred_at (ISO-8601 UTC), $actor_tg_id, $action, $target_kind, $target_id, $source, $reason.
admin-audit-row = • #{ $id } · { $occurred_at } · @{ $actor_tg_id } · <code>{ $action }</code> · { $target_kind }=<code>{ $target_id }</code> · src={ $source } · { $reason }

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.1 — `/clan` read-only clan card (GDD §18.6.5)
# ─────────────────────────────────────────────────────────────────────────────

# /clan <id|chat_id>
admin-clan-usage = ⚠ Uso: <code>/clan &lt;id|chat_id&gt;</code>.
admin-clan-not-authorized = ❌Solo los administradores activos pueden ver tarjetas de clanes.
admin-clan-bad-id = ⚠ <code>{ $value }</code> no es un id de clan (entero).
admin-clan-not-found = 🔍Clan con id/chat_id <code>{ $query }</code> no encontrado.
# Card header. Params: $clan_id, $chat_id, $chat_kind, $title, $status, $created_at, $updated_at, $member_count, $active_member_count, $total_length_cm.
admin-clan-card-summary =
    🛡 Clan #{ $clan_id }: <b>{ $title }</b>
    chat_id: <code>{ $chat_id }</code> ({ $chat_kind })
    Estado: { $status }
    Creado: { $created_at } · actualizado: { $updated_at }
    Miembros: { $member_count } (activos { $active_member_count }) · longitud total: { $total_length_cm } cm.
# Caravan leader. Params: $tg_id, $username, $name, $length_cm, $joined_at.
admin-clan-card-leader = 👑 Líder: @{ $username } ({ $name }, tg_id <code>{ $tg_id }</code>) · longitud { $length_cm } cm · desde { $joined_at }.
admin-clan-card-no-leader = 👑 Líder: —
# One member row. Params: $tg_id, $username, $name, $length_cm, $thickness_level, $status, $role, $joined_at.
admin-clan-card-member-row = • @{ $username } ({ $name }, tg_id <code>{ $tg_id }</code>) · { $length_cm } cm · t{ $thickness_level } · { $status } · { $role } · desde { $joined_at }
admin-clan-card-no-members = (el clan no tiene miembros)

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.2 — `/freeze_clan` / `/unfreeze_clan` (GDD §18.6.5)
# ─────────────────────────────────────────────────────────────────────────────

# /freeze_clan <id|chat_id> [reason]
admin-freeze-clan-usage = ⚠ Uso: <code>/freeze_clan &lt;id|chat_id&gt; [razón]</code>.
admin-freeze-clan-not-authorized = ❌Solo los administradores activos pueden congelar clanes.
admin-freeze-clan-bad-id = ⚠ <code>{ $value }</code> no es un id de clan (entero).
admin-freeze-clan-not-found = 🔍Clan con id/chat_id <code>{ $query }</code> no encontrado.
admin-freeze-clan-already = ℹ El clan #{ $clan_id } ya está congelado.
admin-freeze-clan-ok = ❄ Clan #{ $clan_id } congelado.{ $reason_suffix }
admin-freeze-clan-reason-suffix = Razón: { $reason }.

# /unfreeze_clan <id|chat_id>
admin-unfreeze-clan-usage = ⚠ Uso: <code>/unfreeze_clan &lt;id|chat_id&gt;</code>.
admin-unfreeze-clan-not-authorized = ❌Solo los administradores activos pueden descongelar clanes.
admin-unfreeze-clan-bad-id = ⚠ <code>{ $value }</code> no es un id de clan (entero).
admin-unfreeze-clan-not-found = 🔍Clan con id/chat_id <code>{ $query }</code> no encontrado.
admin-unfreeze-clan-already = ℹ El clan #{ $clan_id } ya está activo.
admin-unfreeze-clan-ok = 🔥 Clan #{ $clan_id } descongelado.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.3 — `/clan_daily_head_history` (read-only)
# ─────────────────────────────────────────────────────────────────────────────

admin-clan-daily-head-history-usage = ⚠ Uso: <code>/clan_daily_head_history &lt;id|chat_id&gt; [N=10]</code>.
admin-clan-daily-head-history-not-authorized = ❌Solo los administradores activos pueden ver el historial de líderes diarios.
admin-clan-daily-head-history-bad-id = ⚠ <code>{ $value }</code> no es un id de clan (entero).
admin-clan-daily-head-history-bad-limit = ⚠ <code>{ $value }</code> no es un límite (entero 1..50).
admin-clan-daily-head-history-not-found = 🔍Clan con id/chat_id <code>{ $query }</code> no encontrado.
admin-clan-daily-head-history-empty = 👑 Clan #{ $clan_id } "{ $title }": el historial de líderes diarios está vacío.
admin-clan-daily-head-history-header = 👑 Clan #{ $clan_id } "{ $title }", últimas { $count } asignaciones de líder diario:
admin-clan-daily-head-history-row = • <b>{ $moscow_date }</b> — { $tg_id } (@{ $username }, { $name }) +{ $bonus } cm ({ $source })
admin-clan-daily-head-history-row-orphan = • <b>{ $moscow_date }</b> — jugador eliminado +{ $bonus } cm ({ $source })

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.4 — `/announce` (broadcast with TOTP-confirm)
# ─────────────────────────────────────────────────────────────────────────────

admin-announce-usage = ⚠ Uso: <code>/announce &lt;ru|en|*&gt; &lt;texto&gt;</code>. El idioma elige la audiencia: ru — jugadores con idioma RU, en — con EN o sin elección explícita (predeterminado), * — todos los jugadores activos.
admin-announce-non-private = 🍆 Los comandos de administración solo están disponibles en el DM con el bot.
admin-announce-not-authorized = ❌Solo los administradores activos pueden lanzar difusiones.
admin-announce-totp-not-configured = ❌Tu TOTP no está configurado. <code>/announce</code> no está disponible sin él.
admin-announce-bad-locale = ⚠ <code>{ $value }</code> no es un filtro de idioma conocido. Permitidos: <code>ru</code>, <code>en</code>, <code>*</code>.
admin-announce-empty-message = ⚠ El texto del anuncio no puede estar vacío.
admin-announce-too-long = ⚠ El mensaje es muy largo: { $length } caracteres, máximo { $max_length }.
admin-announce-confirm-issued = 🛡 Listo para difundir a <b>{ $recipient_count }</b> jugadores (filtro: { $locale_filter }). Confirma: <code>/confirm { $token } &lt;código de 6 dígitos&gt;</code>. El token vive { $ttl_seconds } segundos.
admin-announce-progress-start = 📤 Iniciando difusión: { $recipient_count } destinatarios (filtro: { $locale_filter }). Te avisaré cuando termine.
admin-announce-progress-final = ✅ Difusión completada. Destinatarios: { $recipient_count }, entregados: { $sent_count }, fallidos: { $failed_count }, bloqueados: { $blocked_count }.
admin-announce-progress-failed = ⚠ La difusión en segundo plano falló. Detalles en los logs del bot y auditoría de admin.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-D.6 — `/admin_setup_totp` (self-service TOTP secret bootstrap)
# ─────────────────────────────────────────────────────────────────────────────
# The `secret` + `otpauth://` URI never reaches the chat — the handler logs
# them only via `structlog` on the server (event=admin_totp_setup). The
# Telegram chat sees only a short "configured, check logs" acknowledgement.

admin-setup-totp-usage = ⚠ Uso: <code>/admin_setup_totp &lt;contraseña-bootstrap&gt;</code>. Solo disponible en DM con el bot.
admin-setup-totp-non-private = 🍆 Los comandos de administración solo están disponibles en el DM con el bot.
admin-setup-totp-not-authorized = ❌ Solo los super-admins activos pueden inicializar un secreto TOTP.
admin-setup-totp-password-not-configured = ❌ <code>BOOTSTRAP_ADMIN_PASSWORD</code> no está configurado en el entorno del bot. El comando rechaza (fail-closed): la emisión autoservicio de un nuevo secreto TOTP sin un segundo factor no está permitida.
admin-setup-totp-password-invalid = ❌ Contraseña bootstrap inválida.
admin-setup-totp-already-configured = ❌ TOTP ya está configurado. Emitir un nuevo secreto requiere un reinicio manual del DBA (ver <code>docs/admin_runbook.md</code>).
admin-setup-totp-success = ✅ TOTP configurado. El secreto y la URI <code>otpauth://</code> están en los logs del servidor (event=<code>admin_totp_setup</code>) — ábrelos en tu infraestructura e impórtalos a Authenticator/1Password. El secreto intencionalmente nunca aparece en el chat.

# ============================================================================
# /mountains, /dungeon (Sprint 3.1-E, GDD §8). PvE locations with ±-outcome.
# Mirrors `forest-*`; differences: two length-line variants
# (`-gain` / `-loss` / `-zero`) and `requirement-*` for entry checks.
# ============================================================================

# --------------------------- /mountains -------------------------------------

mountains-group = 🏔 El comando /mountains solo está disponible en el chat privado del bot. Abre el DM e inténtalo de nuevo.
mountains-other = 🏔 El comando /mountains solo está disponible en el chat privado del bot.
mountains-not-registered = 🏔 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás ir a las montañas.
mountains-already-in = 🏔 Ya estás en las montañas — espera tu regreso. El bot enviará un mensaje cuando el viaje termine.
mountains-requirement-thickness = 🏔 Las montañas necesitan grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }. Entrena con /upgrade.
mountains-requirement-length = 🏔 Las montañas requieren ≥ { NUMBER($required_cm, useGrouping: 0) } cm. Tienes { NUMBER($actual_cm, useGrouping: 0) } cm.
mountains-started = 🏔 { $nick } se fue a las montañas por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...
mountains-started-fallback = 🏔 Te fuiste a las montañas por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...

mountains-finished-header = 🏔 ¡{ $nick } regresó de las montañas!
mountains-finished-length-gain =
    📏 Longitud: +{ NUMBER($length_delta_cm, useGrouping: 0) } cm (era { NUMBER($length_before_cm, useGrouping: 0) }, ahora { NUMBER($length_after_cm, useGrouping: 0) })
mountains-finished-length-loss =
    📏 Longitud: −{ NUMBER($length_delta_abs_cm, useGrouping: 0) } cm (era { NUMBER($length_before_cm, useGrouping: 0) }, ahora { NUMBER($length_after_cm, useGrouping: 0) })
mountains-finished-length-zero =
    📏 Longitud sin cambios ({ NUMBER($length_before_cm, useGrouping: 0) } cm)
mountains-finished-item-found = 🎩 Encontrado: { $item_name } [{ $rarity }]

mountains-button-equip = Equipar
mountains-button-drop-item = Descartar

mountains-toast-item-equipped-placeholder = El equipo vendrá después — el objeto está en tu inventario por ahora.
mountains-toast-item-dropped = Objeto descartado.
mountains-toast-foreign-button = Este botón no es para ti.
mountains-toast-run-not-found = Esta expedición ya no está activa.
mountains-toast-drop-mismatch = Botón desactualizado.

# --------------------------- /dungeon ---------------------------------------

dungeon-group = 🏰 El comando /dungeon solo está disponible en el chat privado del bot. Abre el DM e inténtalo de nuevo.
dungeon-other = 🏰 El comando /dungeon solo está disponible en el chat privado del bot.
dungeon-not-registered = 🏰 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás entrar a la mazmorra.
dungeon-already-in = 🏰 Ya estás en la mazmorra — espera tu regreso. El bot enviará un mensaje cuando el viaje termine.
dungeon-requirement-thickness = 🏰 La mazmorra necesita grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }. Entrena con /upgrade.
dungeon-requirement-length = 🏰 La mazmorra requiere ≥ { NUMBER($required_cm, useGrouping: 0) } cm. Tienes { NUMBER($actual_cm, useGrouping: 0) } cm.
dungeon-started = 🏰 { $nick } entró a la mazmorra por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...
dungeon-started-fallback = 🏰 Entraste a la mazmorra por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...

dungeon-finished-header = 🏰 ¡{ $nick } regresó de la mazmorra!
dungeon-finished-length-gain =
    📏 Longitud: +{ NUMBER($length_delta_cm, useGrouping: 0) } cm (era { NUMBER($length_before_cm, useGrouping: 0) }, ahora { NUMBER($length_after_cm, useGrouping: 0) })
dungeon-finished-length-loss =
    📏 Longitud: −{ NUMBER($length_delta_abs_cm, useGrouping: 0) } cm (era { NUMBER($length_before_cm, useGrouping: 0) }, ahora { NUMBER($length_after_cm, useGrouping: 0) })
dungeon-finished-length-zero =
    📏 Longitud sin cambios ({ NUMBER($length_before_cm, useGrouping: 0) } cm)
dungeon-finished-item-found = 🎩 Encontrado: { $item_name } [{ $rarity }]

dungeon-button-equip = Equipar
dungeon-button-drop-item = Descartar

dungeon-toast-item-equipped-placeholder = El equipo vendrá después — el objeto está en tu inventario por ahora.
dungeon-toast-item-dropped = Objeto descartado.
dungeon-toast-foreign-button = Este botón no es para ti.
dungeon-toast-run-not-found = Esta expedición ya no está activa.
dungeon-toast-drop-mismatch = Botón desactualizado.

# ============================================================================
# /caravan (Sprint 3.2-D, GDD §9). Clan caravans: a leader assembles
# a group, marches to another clan's chat, and weathers a raider ambush.
# The command runs only in the bot's private chat: the leader passes
# the receiver clan's chat_id and a contribution amount in cm. The
# lobby announcement with a "Show lobby" button is posted into the
# sender clan's chat.
# ============================================================================

caravans-group = 🐪 El comando /caravan solo está disponible en el chat privado del bot. Abre el DM e inténtalo de nuevo.
caravans-other = 🐪 El comando /caravan solo está disponible en el chat privado del bot.
caravans-not-registered = 🐪 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás armar una caravana.
caravans-usage =
    🐪 Para armar una caravana, pasa el chat_id del clan receptor y tu contribución en cm:
    <code>/caravan &lt;chat_id_receptor&gt; &lt;contribución_cm&gt;</code>

    Ejemplo: <code>/caravan -1001234567890 30</code>
caravans-receiver-invalid = 🐪 Eso no parece un chat_id de Telegram: <code>{ $value }</code>. Pasa el chat_id numérico del clan receptor (los ids de chat grupal son negativos).
caravans-contribution-invalid = 🐪 La contribución debe ser un entero positivo, recibido: <code>{ $value }</code>.
caravans-no-clan = 🐪 No tienes clan. Solo un líder de clan puede armar una caravana.
caravans-not-a-leader = 🐪 Solo un líder de clan puede armar una caravana — eres un miembro regular.
caravans-receiver-not-found = 🐪 El chat con chat_id <code>{ $chat_id }</code> no es un clan registrado. Pasa el chat_id de otro clan.
caravans-receiver-same-as-sender = 🐪 No puedes enviar una caravana a tu propio clan. Pasa el chat_id de otro clan.
caravans-already-in = 🐪 Tu clan ya tiene una caravana activa — espera a que termine o cancélala desde el lobby.
caravans-cooldown = 🐪 El enfriamiento de la caravana del clan no ha expirado. Inténtalo de nuevo en { NUMBER($remaining_minutes, useGrouping: 0) } min.
caravans-requirement-thickness = 🐪 Armar una caravana requiere grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }. Entrena con /upgrade.
caravans-requirement-length = 🐪 Después de tu contribución debes mantener ≥ { NUMBER($required_cm, useGrouping: 0) } cm de longitud. Te quedarían { NUMBER($actual_cm, useGrouping: 0) } cm.
caravans-player-frozen = 🐪 Tu perfil está congelado — no puedes armar una caravana.
caravans-clan-frozen-sender = 🐪 Tu clan está congelado — no puedes armar una caravana.
caravans-clan-frozen-receiver = 🐪 El clan receptor está congelado — no puedes enviarle una caravana.

caravans-created-private =
    🐪 ¡Caravana armada!
    Receptor: <b>{ $receiver_clan_name }</b>
    Contribución: { NUMBER($contribution_cm, useGrouping: 0) } cm
    El lobby está abierto por { NUMBER($lobby_minutes, useGrouping: 0) } min — el anuncio fue publicado en el chat de tu clan.
caravans-created-announcement =
    🐪 ¡<b>{ $leader_nick }</b> está armando una caravana!
    Destino: <b>{ $receiver_clan_name }</b>
    Contribución del líder: { NUMBER($contribution_cm, useGrouping: 0) } cm
    El lobby está abierto por { NUMBER($lobby_minutes, useGrouping: 0) } min — únete mientras puedas.
caravans-button-show-lobby = Ver lobby
caravans-button-cancel = Cancelar caravana

# --- Callback `caravan:show_lobby:<id>` (Sprint 3.2-D, D.3c) ---

caravans-lobby-state =
    🐪 <b>{ $leader_nick }</b> está armando una caravana hacia <b>{ $receiver_clan_name }</b>
    Lobby { $lobby_status }.

    Formación:
    • Caravaneros: { NUMBER($caravaneers_count, useGrouping: 0) } (contribución: { NUMBER($total_contribution_cm, useGrouping: 0) } cm)
    • Defensores: { NUMBER($defenders_count, useGrouping: 0) } / { NUMBER($defenders_cap, useGrouping: 0) }
    • Asaltantes: { NUMBER($raiders_count, useGrouping: 0) } / { NUMBER($raiders_cap, useGrouping: 0) }
caravans-lobby-status-open = cierra en { NUMBER($remaining_minutes, useGrouping: 0) } min
caravans-lobby-status-closing = cerrando
caravans-button-join-defender = Unirse como defensor
caravans-button-join-raider = Unirse como asaltante
caravans-button-leave = Salir

# --- Battle started / battle finished (Sprint 3.2-D, D.4–D.6) ---
# Published by APScheduler callbacks to the sender and receiver clan chats
# right after the successful `LOBBY → IN_BATTLE` and `IN_BATTLE → FINISHED`.

caravans-battle-started =
    🐪 ¡La caravana de <b>{ $sender_clan_name }</b> hacia <b>{ $receiver_clan_name }</b> partió!

    Líder: <b>{ $leader_nick }</b>
    Caravaneros: { NUMBER($caravaneers_count, useGrouping: 0) }
    Defensores: { NUMBER($defenders_count, useGrouping: 0) }
    Asaltantes: { NUMBER($raiders_count, useGrouping: 0) }
    Carga: { NUMBER($total_cargo_cm, useGrouping: 0) } cm

    ⚔️ La batalla terminará en aproximadamente { NUMBER($battle_minutes, useGrouping: 0) } min.
caravans-battle-finished-delivered =
    ✅ ¡La caravana de <b>{ $sender_clan_name }</b> fue entregada a <b>{ $receiver_clan_name }</b>!

    Líder: <b>{ $leader_nick }</b>
    Caravaneros sobrevivientes: { NUMBER($caravaneers_alive, useGrouping: 0) } / { NUMBER($caravaneers_total, useGrouping: 0) }
    Defensores sobrevivientes: { NUMBER($defenders_alive, useGrouping: 0) } / { NUMBER($defenders_total, useGrouping: 0) }

    🎁 Cada miembro del clan emisor recibió +{ NUMBER($clan_bonus_sender_cm, useGrouping: 0) } cm.
    🎁 Cada miembro del clan receptor recibió +{ NUMBER($clan_bonus_receiver_cm, useGrouping: 0) } cm.
caravans-battle-finished-raided =
    ☠️ ¡La caravana de <b>{ $sender_clan_name }</b> hacia <b>{ $receiver_clan_name }</b> fue asaltada!

    Líder: <b>{ $leader_nick }</b>
    Atamán ganador: <b>{ $ataman_nick }</b>

    La carga ({ NUMBER($total_cargo_cm, useGrouping: 0) } cm) se repartió entre { NUMBER($raiders_count, useGrouping: 0) } asaltantes.

# --- Callback `caravan:cancel:<id>` (Sprint 3.2-D, D.3) ---

caravans-cancel-message = 🐪 Caravana cancelada por el líder.
caravans-cancel-toast-success = Caravana cancelada
caravans-cancel-toast-already-cancelled = La caravana ya fue cancelada

# --- Common caravan callback toasts (Sprint 3.2-D, D.3) ---

caravans-callback-toast-caravan-not-found = Caravana no encontrada
caravans-callback-toast-invalid-state = La caravana ya no está en el lobby
caravans-callback-toast-not-a-leader = Solo el líder puede cancelar la caravana
caravans-callback-toast-player-not-found = Pulsa /start en el chat privado del bot primero
caravans-callback-toast-generic-error = Algo salió mal. Inténtalo de nuevo.

# --- Callback `caravan:join_defender|join_raider:<id>` (Sprint 3.2-D, D.3d) ---

caravans-join-toast-success-defender = Te uniste al lobby como defensor
caravans-join-toast-success-raider = Te uniste al lobby como asaltante
caravans-callback-toast-lobby-closed = El lobby de la caravana ya está cerrado
caravans-callback-toast-player-frozen = Tu perfil está congelado
caravans-callback-toast-already-in-caravan = Ya estás en una caravana activa
caravans-callback-toast-role-conflict-defender = Los defensores deben ser miembros del clan receptor
caravans-callback-toast-role-conflict-raider = Los asaltantes no deben ser miembros de ninguno de los clanes de la caravana
caravans-callback-toast-capacity-defender = Capacidad de defensores alcanzada: { NUMBER($limit, useGrouping: 0) }. No quedan lugares.
caravans-callback-toast-capacity-raider = Capacidad de asaltantes alcanzada: { NUMBER($limit, useGrouping: 0) }. No quedan lugares.
caravans-callback-toast-requirement-thickness = Requiere grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }.
caravans-callback-toast-requirement-length = Requiere longitud ≥ { NUMBER($required_cm, useGrouping: 0) } cm. Tienes { NUMBER($actual_cm, useGrouping: 0) } cm.

# --- Callback `caravan:leave:<id>` (Sprint 3.2-D, D.3e) ---

caravans-leave-toast-success = Saliste del lobby de la caravana
caravans-leave-toast-success-with-contribution = Saliste del lobby. Devueltos: { NUMBER($contribution_cm, useGrouping: 0) } cm
caravans-leave-toast-leader-cannot-leave = El líder no puede salir. Para disolver la caravana, pulsa "Cancelar".
caravans-leave-toast-not-a-participant = No eres participante de esta caravana

# --- Command `/caravan_join` (Sprint 3.2-D, D.3f) ---
# This command runs only in the bot's private chat: a player passes the
# caravan_id and a contribution in cm to join the lobby as a CARAVANEER
# (DEFENDER/RAIDER use lobby inline buttons — they don't need a contribution).

caravans-join-usage =
    🐪 Para unirte a una caravana como caravanero, pasa el caravan_id (visible en el lobby) y una contribución en cm:
    <code>/caravan_join &lt;caravan_id&gt; &lt;contribución_cm&gt;</code>

    Ejemplo: <code>/caravan_join 42 30</code>
caravans-join-caravan-id-invalid = 🐪 caravan_id debe ser un entero positivo, recibido: <code>{ $value }</code>.
caravans-join-success-caravaneer =
    🐪 ¡Te uniste a la caravana como caravanero!
    Contribución: { NUMBER($contribution_cm, useGrouping: 0) } cm
caravans-join-role-conflict-caravaneer = 🐪 Solo los miembros del clan emisor pueden unirse como caravaneros.

# ============================================================================
# /boss (Sprint 3.3-D, GDD §10). Raid bosses: a summoner challenges a
# random top-30 player to a raid, gathers a lobby of raiders, and the
# group fights the boss in fixed-duration rounds. The command runs in
# DM (private chat with the bot); the lobby announcement with a
# "Show lobby" button is posted to the same chat where /boss was sent
# (group or DM).
# ============================================================================

bosses-not-registered = 👹 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás invocar un jefe de raid.
bosses-usage = 👹 Para invocar un jefe de raid, escribe <code>/boss</code> — se elegirá un jugador aleatorio del top-{ NUMBER($top_n_pool, useGrouping: 0) } como jefe.
bosses-cooldown = 👹 El enfriamiento global de jefes de raid no ha expirado. Inténtalo de nuevo en { NUMBER($remaining_minutes, useGrouping: 0) } min.
bosses-already-in = 👹 Ya estás en un raid activo — espera a que termine o sal del lobby primero.
bosses-requirement-thickness = 👹 Invocar un jefe de raid requiere grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }. Entrena con /upgrade.
bosses-requirement-length = 👹 Necesitas longitud ≥ { NUMBER($required_cm, useGrouping: 0) } cm para invocar un raid. Tienes { NUMBER($actual_cm, useGrouping: 0) } cm.
bosses-player-frozen = 👹 Tu perfil está congelado — no puedes invocar un jefe de raid.
bosses-pool-empty = 👹 No hay candidatos a jefe elegibles en este momento — inténtalo más tarde.

bosses-summoned-private =
    👹 ¡Jefe de raid invocado!
    Jefe: <b>{ $boss_nick }</b> ({ NUMBER($boss_length_cm, useGrouping: 0) } cm)
    El lobby está abierto por { NUMBER($lobby_minutes, useGrouping: 0) } min — el anuncio fue publicado en el chat.
bosses-summoned-announcement =
    👹 ¡<b>{ $summoner_nick }</b> desafía a <b>{ $boss_nick }</b> a un raid!
    Longitud del jefe: { NUMBER($boss_length_cm, useGrouping: 0) } cm
    El lobby está abierto por { NUMBER($lobby_minutes, useGrouping: 0) } min — únete mientras puedas.
bosses-button-show-lobby = Ver lobby
bosses-button-cancel = Cancelar raid

# --- Callback `boss:show_lobby:<id>` (Sprint 3.3-D, D.4) ---

bosses-lobby-state =
    👹 <b>{ $summoner_nick }</b> ataca a <b>{ $boss_nick }</b>
    Lobby { $lobby_status }.

    Longitud del jefe: { NUMBER($boss_length_cm, useGrouping: 0) } cm
    Atacantes: { NUMBER($raiders_count, useGrouping: 0) }
bosses-lobby-status-open = cierra en { NUMBER($remaining_minutes, useGrouping: 0) } min
bosses-lobby-status-closing = cerrando
bosses-button-join = Unirse al raid
bosses-button-leave = Salir

# --- Battle started / round tick / battle finished (Sprint 3.3-D, D.7) ---
# Published by APScheduler callbacks to the chat where /boss was sent
# right after `LOBBY → IN_BATTLE`, after each round, and on `IN_BATTLE
# → FINISHED`.

bosses-battle-started =
    👹 ¡El raid contra <b>{ $boss_nick }</b> ha comenzado!

    Invocador: <b>{ $summoner_nick }</b>
    Atacantes: { NUMBER($raiders_count, useGrouping: 0) }
    Longitud del jefe: { NUMBER($boss_length_cm, useGrouping: 0) } cm

    ⚔️ El jefe golpea cada { NUMBER($round_seconds, useGrouping: 0) } seg.
bosses-round-tick =
    ⚔️ Ronda { NUMBER($round_number, useGrouping: 0) } — jefe <b>{ $boss_nick }</b>

    Daño al jefe: { NUMBER($boss_damage_cm, useGrouping: 0) } cm (ahora { NUMBER($boss_length_cm, useGrouping: 0) } cm)
    Eliminados: { NUMBER($eliminated_count, useGrouping: 0) }
    Atacantes restantes: { NUMBER($raiders_alive, useGrouping: 0) }
bosses-battle-finished-victory =
    🏆 ¡Los atacantes derrotaron a <b>{ $boss_nick }</b>!

    Invocador: <b>{ $summoner_nick }</b>
    Atacantes vivos: { NUMBER($raiders_alive, useGrouping: 0) }

    🎁 Cada atacante sobreviviente recibe +{ NUMBER($per_raider_grant_cm, useGrouping: 0) } cm.
bosses-battle-finished-defeat =
    ☠️ ¡El raid contra <b>{ $boss_nick }</b> falló!

    Invocador: <b>{ $summoner_nick }</b>
    Atacantes vivos: { NUMBER($raiders_alive, useGrouping: 0) }

    El jefe reclama { NUMBER($total_granted_cm, useGrouping: 0) } cm de longitud.

# --- Callback `boss:cancel:<id>` (Sprint 3.3-D, D.4) ---

bosses-cancel-message = 👹 Raid cancelado por el invocador.
bosses-cancel-toast-success = Raid cancelado
bosses-cancel-toast-already-cancelled = El raid ya fue cancelado

# --- Common boss callback toasts (Sprint 3.3-D, D.4) ---

bosses-callback-toast-fight-not-found = Raid no encontrado
bosses-callback-toast-invalid-state = El raid ya no está en el lobby
bosses-callback-toast-not-summoner = Solo el invocador puede cancelar el raid
bosses-callback-toast-player-not-found = Pulsa /start en el chat privado del bot primero
bosses-callback-toast-player-frozen = Tu perfil está congelado
bosses-callback-toast-generic-error = Algo salió mal. Inténtalo de nuevo.

# --- Callback `boss:join:<id>` (Sprint 3.3-D, D.4) ---

bosses-join-toast-success = Te uniste al raid
bosses-callback-toast-lobby-closed = El lobby del raid ya está cerrado
bosses-callback-toast-already-in-fight = Ya eres participante de este raid
bosses-callback-toast-cannot-join-as-boss = No puedes unirte como atacante — tú eres el jefe
bosses-callback-toast-requirement-thickness = Requiere grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }.
bosses-callback-toast-requirement-length = Requiere longitud ≥ { NUMBER($required_cm, useGrouping: 0) } cm. Tienes { NUMBER($actual_cm, useGrouping: 0) } cm.

# --- Callback `boss:leave:<id>` (Sprint 3.3-D, D.4) ---

bosses-leave-toast-success = Saliste del lobby del raid
bosses-leave-toast-not-a-participant = No eres participante de este raid
bosses-leave-toast-summoner-leaves = El invocador no puede salir — usa "Cancelar raid" en su lugar.

## /inventory + /enchant (Sprint 3.4-D)

# --- /inventory ---

inventory-group = 🎒 El comando /inventory solo funciona en el DM del bot. Abre un chat privado e inténtalo de nuevo.

inventory-other = 🎒 El comando /inventory solo funciona en el DM del bot.

inventory-not-registered = 🎒 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás ver tu inventario.

inventory-empty = 🎒 Tu inventario está vacío.\nVe a una expedición con /forest o /mountains, pelea contra un /boss, o únete a un /caravan para obtener objetos y pergaminos.

# Inventory listing card. Parameters:
# - `$items_count` — total number of items the player owns.
# - `$scrolls_count` — total number of scroll stacks the player owns.
inventory-card =
    🎒 Inventario
    Objetos: { NUMBER($items_count, useGrouping: 0) }
    Pilas de pergaminos: { NUMBER($scrolls_count, useGrouping: 0) }

# One item line. Parameters:
# - `$display_name` — catalog display name (e.g. "Hat of the Voivode").
# - `$enchant_suffix` — pre-formatted "+N" suffix (or empty for level 0).
# - `$slot_label` — localized slot name.
# - `$rarity_label` — localized rarity name.
inventory-item-line = • <b>{ $display_name }{ $enchant_suffix }</b> [{ $slot_label }, { $rarity_label }]

# One scroll stack line. Parameters:
# - `$scroll_label` — localized scroll display name (e.g. "Weapon scroll, blessed").
# - `$qty` — integer count.
inventory-scroll-line = • { $scroll_label } × { NUMBER($qty, useGrouping: 0) }

inventory-section-items = 📦 Objetos:
inventory-section-scrolls = 📜 Pergaminos:

# Inline button "Enchant" on item card.
inventory-button-enchant = ⚒ Encantar

# Disabled hint when player has no matching scrolls for the item.
inventory-toast-no-scroll = No hay pergaminos compatibles para este objeto.

# Picker card to choose between regular and blessed scrolls — D.1d.
# Parameters:
# - `$item_display` — full pretty item name with +N (e.g. "Sword +5").
inventory-picker-card =
    ⚒ Encantando un objeto
    Objeto: <b>{ $item_display }</b>

    Elige un pergamino para encantar.

inventory-picker-button-regular = Pergamino regular
inventory-picker-button-blessed = Pergamino bendecido
inventory-picker-button-cancel = Cancelar

inventory-picker-cancelled = Encantamiento cancelado.

# Toast after the picker "Cancel" button (Telegram limit ≤ 200 chars).
inventory-picker-toast-cancelled = Cancelado.

# Slot labels (8 slots, ГДД §2.6).
inventory-slot-hat = cabeza
inventory-slot-body = cuerpo
inventory-slot-legs = piernas
inventory-slot-boots = botas
inventory-slot-ring = anillo
inventory-slot-chain = cadena
inventory-slot-right-hand = mano derecha
inventory-slot-left-hand = mano izquierda

# Rarity labels (ГДД §2.5).
inventory-rarity-common = común
inventory-rarity-uncommon = poco común
inventory-rarity-rare = raro
inventory-rarity-epic = épico
inventory-rarity-legendary = legendario

# Scroll display labels.
# `$category_label` is one of inventory-scroll-category-* values.
inventory-scroll-display-regular = pergamino de { $category_label }
inventory-scroll-display-blessed = pergamino bendecido de { $category_label }

inventory-scroll-category-weapon = arma
inventory-scroll-category-armor = armadura
inventory-scroll-category-jewelry = joyería

# --- /enchant ---

enchant-group = ⚒ El comando /enchant solo funciona en el DM del bot. Abre un chat privado e inténtalo de nuevo.

enchant-other = ⚒ El comando /enchant solo funciona en el DM del bot.

enchant-not-registered = ⚒ Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás encantar.

enchant-usage = Uso: <code>/enchant &lt;item_id&gt; &lt;scroll_id&gt;</code>\n\nEjemplo: <code>/enchant item.right_hand.test_1 weapon_scroll:regular</code>\n\nO abre /inventory y pulsa el botón ⚒ Encantar en la tarjeta del objeto.

# Warning card before confirmation. Parameters:
# - `$item_display` — full pretty item name with +N (e.g. "Sword +5").
# - `$scroll_display` — pretty scroll name.
# - `$tier_label` — localized tier (safe / easy / hard / very-hard / extreme / impossible).
# - `$tier_emoji` — single emoji indicating tier.
enchant-warning-regular =
    ⚒ Intento de encantamiento
    Objeto: <b>{ $item_display }</b>
    Pergamino: { $scroll_display }
    Nivel de dificultad: { $tier_emoji } { $tier_label }

    Resultados posibles:
    • Éxito (+1)
    • Sin efecto
    • Caída (-1)
    • <b>Destrucción</b> (el objeto se pierde para siempre)

enchant-warning-blessed =
    ⚒ Intento de encantamiento bendecido
    Objeto: <b>{ $item_display }</b>
    Pergamino: { $scroll_display }
    Nivel de dificultad: { $tier_emoji } { $tier_label }

    Resultados posibles:
    • Gran éxito (+2)
    • Éxito (+1)
    • Sin efecto
    • Caída (-1)
    • Gran caída (-2)

    Un pergamino bendecido nunca destruye el objeto.

# Inline buttons for confirm/cancel.
enchant-button-confirm = Confirmar
enchant-button-cancel = Cancelar

# Result messages. Parameters in all:
# - `$item_display` — full pretty item name with the new +N (after).
# - `$old_level` — integer, level before attempt.
# - `$new_level` — integer, level after attempt.
enchant-success =
    ✅ ¡Éxito! { $item_display }
    Nivel: +{ NUMBER($old_level, useGrouping: 0) } → +{ NUMBER($new_level, useGrouping: 0) }

enchant-no-effect =
    ⚪ Sin efecto.
    Objeto: <b>{ $item_display }</b>
    Nivel sin cambios: +{ NUMBER($old_level, useGrouping: 0) }
    El pergamino fue consumido.

enchant-drop =
    🔻 Caída.
    Objeto: <b>{ $item_display }</b>
    Nivel: +{ NUMBER($old_level, useGrouping: 0) } → +{ NUMBER($new_level, useGrouping: 0) }

enchant-destroy =
    💥 ¡El objeto fue destruido!
    <b>{ $item_display }</b> se perdió para siempre.

enchant-cancelled = Encantamiento cancelado.

enchant-idempotent = ℹ El intento ya fue procesado. Abre /inventory para ver el estado actual.

# Tier labels + emoji (ГДД §2.8.5).
enchant-tier-safe = seguro
enchant-tier-easy = fácil
enchant-tier-hard = difícil
enchant-tier-very-hard = muy difícil
enchant-tier-extreme = extremo
enchant-tier-impossible = imposible

# Error messages.
enchant-error-wrong-category = ⚠ Este pergamino no puede encantar este objeto: categoría incompatible.
enchant-error-item-not-found = ⚠ Objeto no encontrado en tu inventario.
enchant-error-scroll-not-found = ⚠ No posees este pergamino.
enchant-error-out-of-stock = ⚠ Se te acabaron estos pergaminos.
enchant-error-bad-args = ⚠ Argumentos incorrectos. Consulta /enchant para el uso.

# Toasts on callback responses (Telegram limit ≤ 200 chars).
enchant-toast-confirmed = Encantamiento completado.
enchant-toast-cancelled = Encantamiento cancelado.
enchant-toast-already-processed = Ya procesado.
enchant-toast-error = Algo salió mal.

# ============================================================================
# /roulette_free (Sprint 3.5-D, GDD §12.4). Free-to-play roulette:
# thickness ≥ 2, 100 cm cost, draws a prize — length (LENGTH outcome)
# or a reserved item / scroll / crypto lot (Phase 4). The command runs
# only in the bot's private chat.
# ============================================================================

roulette-free-group = 🎰 El comando /roulette_free solo funciona en el DM del bot. Abre un chat privado e inténtalo de nuevo.
roulette-free-other = 🎰 El comando /roulette_free solo funciona en el DM del bot.
roulette-free-not-registered = 🎰 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás girar la ruleta.

# Gate-warning cards in the DM (instead of the pre-spin card).
roulette-free-requirement-thickness = 🎰 La ruleta se desbloquea con grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }. Entrena con /upgrade.
roulette-free-requirement-length = 🎰 Un giro requiere ≥ { NUMBER($required_cm, useGrouping: 0) } cm. Tienes { NUMBER($actual_cm, useGrouping: 0) } cm.

# Pre-spin card with a [Spin — 100 cm] button.
roulette-free-prompt =
    🎰 Ruleta gratuita
    Longitud actual: { NUMBER($current_length_cm, useGrouping: 0) } cm
    Costo del giro: { NUMBER($cost_cm, useGrouping: 0) } cm
    Después del giro tendrás: { NUMBER($remaining_cm, useGrouping: 0) } cm

    Pulsa el botón para girar.

roulette-free-button-spin = Girar — { NUMBER($cost_cm, useGrouping: 0) } cm

# Animation frames (3 frames via edit_text).
roulette-free-animation-frame-1 = 🎰 Girando la ruleta…
roulette-free-animation-frame-2 = 🎰 La bola sigue rodando…
roulette-free-animation-frame-3 = 🎰 Casi se detiene…

# Result cards. All take $cost_cm — actual spin cost. The LENGTH variant
# also takes $length_cm — the prize in centimeters.
roulette-free-result-length =
    🎰 ¡Longitud! Ganaste <b>+{ NUMBER($length_cm, useGrouping: 0) } cm</b>.
    Costo del giro: { NUMBER($cost_cm, useGrouping: 0) } cm.

roulette-free-result-item =
    🎰 ¡Obtuviste un objeto!
    Costo del giro: { NUMBER($cost_cm, useGrouping: 0) } cm.
    La recompensa se otorgará en la Fase 4 — por ahora el giro quedó registrado.

roulette-free-result-scroll-regular =
    🎰 ¡Obtuviste un pergamino!
    Costo del giro: { NUMBER($cost_cm, useGrouping: 0) } cm.
    La recompensa se otorgará en la Fase 4 — por ahora el giro quedó registrado.

roulette-free-result-scroll-blessed =
    🎰 ¡Obtuviste un pergamino bendecido!
    Costo del giro: { NUMBER($cost_cm, useGrouping: 0) } cm.
    La recompensa se otorgará en la Fase 4 — por ahora el giro quedó registrado.

roulette-free-result-crypto-lot =
    🎰 ¡Obtuviste un lote cripto!
    Costo del giro: { NUMBER($cost_cm, useGrouping: 0) } cm.
    La recompensa se otorgará en la Fase 4 — por ahora el giro quedó registrado.

roulette-free-result-idempotent = ℹ Este giro ya fue procesado. Abre /profile para ver el estado actual.

# Toasts on callback responses (Telegram limit ≤ 200 chars).
roulette-free-toast-thickness-gate = Necesitas grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }.
roulette-free-toast-insufficient-length = Necesitas ≥ { NUMBER($required_cm, useGrouping: 0) } cm. Tienes { NUMBER($actual_cm, useGrouping: 0) } cm.
roulette-free-toast-not-registered = Pulsa /start en el DM del bot primero.
roulette-free-toast-spin-complete = Giro completado.
roulette-free-toast-already-processed = Ya procesado.
roulette-free-toast-error = Algo salió mal.

# -----------------------------------------------------------------------------
# /roulette_paid (Sprint 4.1-A, GDD §12.5). Paid roulette via Telegram Stars:
# 1 ⭐ = 1 spin, 9 ⭐ = 10 spins. Thickness ≥ 1 (available from start).
# Cost is charged in Stars via invoice + pre_checkout_query +
# successful_payment flow. On a LENGTH outcome the player receives "fresh" cm
# (`ROULETTE_PAID_REWARD`); other outcomes — placeholder until 4.1-C.
# -----------------------------------------------------------------------------
roulette-paid-group = 🎰 El comando /roulette_paid solo funciona en el DM. Abre el chat privado del bot e inténtalo de nuevo.
roulette-paid-other = 🎰 El comando /roulette_paid solo funciona en el DM.
roulette-paid-not-registered = 🎰 Parece que aún no estás registrado. Pulsa /start en este chat — luego podrás girar la ruleta.

# Gate warning card (if thickness < config min_thickness_level).
roulette-paid-requirement-thickness = 🎰 La ruleta de pago se desbloquea con grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }. Prueba /upgrade.

# Pre-spin card with two purchase buttons (single and pack-10).
roulette-paid-prompt =
    🎰 Ruleta de pago
    Cada giro es una oportunidad de obtener longitud, objetos, pergaminos o un premio cripto.

    Costo:
    — 1 giro: { NUMBER($single_cost_stars, useGrouping: 0) } ⭐
    — Pack de { NUMBER($pack10_spins, useGrouping: 0) }: { NUMBER($pack10_cost_stars, useGrouping: 0) } ⭐

    Elige un pack para proceder al pago.

roulette-paid-button-buy-single = Comprar 1 giro — { NUMBER($cost_stars, useGrouping: 0) } ⭐
roulette-paid-button-buy-pack-10 = Comprar pack de { NUMBER($pack10_spins, useGrouping: 0) } — { NUMBER($cost_stars, useGrouping: 0) } ⭐

# Invoice (Telegram Stars) — title / description / label per-pack.
roulette-paid-invoice-title-single = 🎰 Ruleta de pago — 1 giro
roulette-paid-invoice-title-pack-10 = 🎰 Ruleta de pago — pack de 10
roulette-paid-invoice-description-single = Un giro de la ruleta de pago por { NUMBER($cost_stars, useGrouping: 0) } ⭐. Oportunidad de obtener longitud, objetos, pergaminos o un premio cripto.
roulette-paid-invoice-description-pack-10 = { NUMBER($pack10_spins, useGrouping: 0) } giros de la ruleta de pago por { NUMBER($cost_stars, useGrouping: 0) } ⭐. ~10% de descuento vs compras individuales.
roulette-paid-invoice-label-single = Ruleta de pago — 1 giro
roulette-paid-invoice-label-pack-10 = Ruleta de pago — pack de { NUMBER($pack10_spins, useGrouping: 0) }

# Result cards for SINGLE-pack (one outcome).
roulette-paid-result-single-length =
    🎰 ¡Longitud! Obtuviste <b>+{ NUMBER($length_cm, useGrouping: 0) } cm</b>.
    Cobrado: { NUMBER($spent_stars, useGrouping: 0) } ⭐.

roulette-paid-result-single-item =
    🎰 ¡Obtuviste un objeto!
    Cobrado: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    La recompensa se otorgará en la Fase 4 — por ahora el resultado quedó registrado.

roulette-paid-result-single-scroll-regular =
    🎰 ¡Obtuviste un pergamino!
    Cobrado: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    La recompensa se otorgará en la Fase 4 — por ahora el resultado quedó registrado.

roulette-paid-result-single-scroll-blessed =
    🎰 ¡Obtuviste un pergamino bendecido!
    Cobrado: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    La recompensa se otorgará en la Fase 4 — por ahora el resultado quedó registrado.

roulette-paid-result-single-crypto-lot =
    🎰 ¡Obtuviste un lote cripto!
    Cobrado: { NUMBER($spent_stars, useGrouping: 0) } ⭐.
    La recompensa se otorgará en la Fase 4 — por ahora el resultado quedó registrado.

# Result card for PACK_10 — aggregated summary across pack10_spins outcomes.
roulette-paid-result-pack-10 =
    🎰 ¡Pack de { NUMBER($n_spins, useGrouping: 0) } completado!
    Longitud: <b>+{ NUMBER($total_length_cm, useGrouping: 0) } cm</b> ({ NUMBER($n_length, useGrouping: 0) } de { NUMBER($n_spins, useGrouping: 0) }).
    Objetos: { NUMBER($n_item, useGrouping: 0) }, pergaminos: { NUMBER($n_scroll_regular, useGrouping: 0) }, bendecidos: { NUMBER($n_scroll_blessed, useGrouping: 0) }, lotes cripto: { NUMBER($n_crypto_lot, useGrouping: 0) }.
    Cobrado: { NUMBER($spent_stars, useGrouping: 0) } ⭐.

roulette-paid-result-idempotent = ℹ Este giro ya fue completado. Abre /profile para ver tu estado actual.

# Card when invoice_payload fails server-side HMAC verification
# (Sprint 4.1-D, D.8.c). User-facing copy is intentionally generic
# — the machine-readable failure reason is logged separately.
roulette-paid-payment-invalid = ⚠ El pago no pudo ser verificado y fue rechazado. No se realizó ningún giro. Vuelve a abrir /roulette_paid e inténtalo de nuevo.

# Toasts.
roulette-paid-toast-thickness-gate = Necesitas grosor ≥ { NUMBER($required, useGrouping: 0) }. Estás en { NUMBER($actual, useGrouping: 0) }.
roulette-paid-toast-not-registered = Pulsa /start en el DM del bot primero.
roulette-paid-toast-payment-ok = Pago confirmado, ruleta girada.
roulette-paid-toast-already-processed = Ya procesado.
roulette-paid-toast-error = Algo salió mal.

## /link_wallet + /link_wallet_confirm (Sprint 4.1-D.6, GDD §12.6.4)

# Chat guards.
link-wallet-group = `/link_wallet` solo funciona en el DM del bot. Abre el DM e inténtalo de nuevo.
link-wallet-other = `/link_wallet` solo funciona en el DM del bot.
link-wallet-not-registered = Regístrate primero — pulsa /start en el DM del bot.

# Main prompt with currency selection buttons.
link-wallet-prompt =
    💼 <b>Vincular una billetera TON</b>

    Elige la moneda en la que se pagarán tus lotes de premio — esta es una configuración única. Puedes cambiar la dirección después ejecutando `/link_wallet` de nuevo.

link-wallet-button-ton = Vincular billetera TON
link-wallet-button-usdt = Vincular billetera USDT (jetton TON)

# Instructions after currency is picked.
link-wallet-instructions-ton =
    🔗 <b>TON Connect — Billetera TON</b>

    1. Abre una billetera compatible con TON-Connect (Tonkeeper, MyTonWallet, Tonhub).
    2. Busca la sección «TON Connect» / «Connect dApp» y conéctala a este bot.
    3. Firma el `tonconnect_proof` — tu billetera demuestra la propiedad de la dirección.
    4. Después de firmar, el bot vincula la dirección automáticamente. Si no sucedió, ejecuta `/link_wallet_confirm ton &lt;dirección&gt; &lt;prueba&gt;` manualmente.

link-wallet-instructions-usdt =
    🔗 <b>TON Connect — Billetera USDT</b>

    1. Abre una billetera compatible con TON-Connect (Tonkeeper, MyTonWallet, Tonhub).
    2. Busca la sección «TON Connect» / «Connect dApp» y conéctala a este bot.
    3. Firma el `tonconnect_proof` — tu billetera demuestra la propiedad de la dirección TON que recibirá el jetton-USDT.
    4. Después de firmar, el bot vincula la dirección automáticamente. Si no sucedió, ejecuta `/link_wallet_confirm usdt &lt;dirección&gt; &lt;prueba&gt;` manualmente.

link-wallet-invalid-callback = Algo anda mal con el botón. Pulsa /link_wallet de nuevo.
link-wallet-toast-invalid = Botón expirado. Ejecuta /link_wallet de nuevo.

# `/link_wallet_confirm <currency> <address> <proof>`.
link-wallet-confirm-group = `/link_wallet_confirm` solo funciona en el DM del bot. Abre el DM e inténtalo de nuevo.
link-wallet-confirm-other = `/link_wallet_confirm` solo funciona en el DM del bot.
link-wallet-confirm-not-registered = Regístrate primero — pulsa /start en el DM del bot.

link-wallet-confirm-usage =
    Uso: `/link_wallet_confirm <moneda> <dirección> <prueba>`.

    Aquí `moneda` es `ton` o `usdt`, `dirección` es tu dirección TON, y `prueba` es la prueba TON Connect que produjo tu billetera.

link-wallet-confirm-unsupported = La moneda `{ $code }` no es compatible. Disponibles: `ton`, `usdt`.

link-wallet-confirm-invalid-proof =
    ❌ La verificación de la prueba TON Connect falló. La firma es falsa o expiró.

    Ejecuta /link_wallet y firma de nuevo.

link-wallet-confirm-already-linked =
    ℹ La billetera `{ $address }` ya está vinculada para `{ $currency }`. No hay nada que hacer — los lotes de premio se envían ahí.

link-wallet-confirm-linked =
    ✅ Billetera `{ $address }` vinculada para `{ $currency }`. Los lotes de premio en esta moneda se pagarán aquí.

link-wallet-confirm-relinked =
    ✅ La dirección para `{ $currency }` ahora es `{ $address }`. Los nuevos lotes de premio se pagarán a la nueva dirección.

# /link_wallet <ton|usdt> <address> — phase-1 (Sprint 4.1-F, F.8.a).
link-wallet-request-usage =
    Uso: `/link_wallet <ton|usdt> <dirección>`.

    `moneda` es `ton` o `usdt`, `dirección` es tu dirección TON (raw `workchain:hex64` o base64url amigable).

link-wallet-request-invalid-currency = La moneda `{ $code }` no es compatible. Disponibles: `ton`, `usdt`.

link-wallet-request-invalid-address =
    ❌ La dirección `{ $address }` no parece una dirección TON. Formato esperado: raw `workchain:hex64` o cadena base64url amigable.

link-wallet-request-issued =
    🔗 <b>Firma `ton_proof` vía TON Connect</b>

    1. Abre una billetera compatible con TON-Connect (Tonkeeper, MyTonWallet, Tonhub) y conéctala al bot.
    2. Firma un `ton_proof` con estos parámetros:
       • <code>domain</code> = <code>{ $domain }</code>
       • <code>payload</code> = <code>{ $nonce }</code>
    3. Tienes <b>{ $expires_at_minutes }</b> min — después el nonce expira y debes empezar de nuevo.
    4. Toma la respuesta JSON de la billetera y ejecuta `/link_wallet_confirm { $currency } { $address } <proof-json>`.

# /claim_prize <lot_id> (Sprint 4.1-D, D.7).
claim-prize-group = `/claim_prize` solo está disponible en el DM del bot. Abre el chat privado.
claim-prize-other = `/claim_prize` solo está disponible en el DM del bot.
claim-prize-not-registered = Regístrate primero — pulsa /start en el DM del bot.

claim-prize-usage =
    Uso: `/claim_prize <lot_id>`.

    `lot_id` es el id del lote reservado de un resultado de ruleta. El pago va a la billetera vinculada.

claim-prize-invalid-lot-id = `lot_id` debe ser un entero positivo. Recibido: `{ $raw }`.

claim-prize-prompt =
    🎁 <b>Premio cripto reservado — lote #{ $lot_id }</b>

    Moneda: `{ $currency }`. Cantidad: `{ $amount }` (unidades nativas).
    Pulsa el botón de abajo para retirar a la billetera vinculada (o ejecuta /link_wallet primero).

claim-prize-button = Reclamar premio

claim-prize-not-found = Lote #{ $lot_id } no encontrado. O ya fue reclamado o no existe.

claim-prize-already-claimed = El lote #{ $lot_id } ya fue pagado. No se puede reclamar de nuevo.

claim-prize-not-reserved =
    El lote #{ $lot_id } actualmente está en estado `{ $status }`, no en `reserved`.
    Solo los lotes reservados se pueden retirar con `/claim_prize`.

claim-prize-wallet-not-linked =
    No hay billetera vinculada para la moneda `{ $currency }`. Ejecuta /link_wallet primero y luego vuelve a reclamar el lote.

claim-prize-not-owner = El lote #{ $lot_id } no te pertenece.

claim-prize-success =
    ✅ <b>Pago enviado — lote #{ $lot_id }</b>

    Moneda: `{ $currency }`. Cantidad: `{ $amount }`.
    Comisión de red: `{ $actual_fee }`. Billetera: `{ $address }`.
    Hash de transacción: `{ $tx_hash }`.

claim-prize-refund =
    ⚠ <b>Lote #{ $lot_id } devuelto al pool</b>

    La comisión de red `{ $actual_fee }` excedió el buffer `{ $fee_buffer }` para `{ $currency } { $amount }`. El lote volverá al pool y reaparecerá cuando las comisiones bajen.

claim-prize-invalid-callback = El botón no funciona. Ejecuta `/claim_prize <lot_id>` manualmente.
claim-prize-toast-invalid = Botón expirado. Usa `/claim_prize <lot_id>`.

# ───────────────────────────────────────────────────────────────────────────
# Sprint 4.1-E.12 — admin command `/prize_pool` (GDD §12.6.6)
# Read-only snapshot of crypto-pool + payout-freeze state.
# Access: SUPER_ADMIN (see AdminCommandKind.GET_PRIZE_POOL).
# ───────────────────────────────────────────────────────────────────────────
admin-prize-pool-not-authorized = ❌ La vista del crypto-pool es solo para super-admin.
admin-prize-pool-header = 💰 <b>Vista del crypto-pool</b>
admin-prize-pool-row =
    • <code>{ $currency }</code> · saldo=<code>{ $balance }</code> · activos=<code>{ $active }</code> · reservados=<code>{ $reserved }</code> · reclamados=<code>{ $claimed }</code> · reembolsados=<code>{ $refunded }</code>
admin-prize-pool-unfrozen = ❄️ Congelamiento de pagos cripto: <b>DESACTIVADO</b>.
admin-prize-pool-frozen =
    🧊 Congelamiento de pagos cripto: <b>ACTIVADO</b>.
    Por: admin_id=<code>{ $admin_id }</code>
    En: <code>{ $frozen_at }</code>
    Razón: { $reason }

# ───────────────────────────────────────────────────────────────────────────
# Sprint 4.1-E.13 — admin command `/refund_lot <lot_id> <reason>` (GDD §12.6.6)
# Force-refund a prize lot into the crypto-pool (super-admin + TOTP-confirm).
# Access: SUPER_ADMIN (see AdminCommandKind.REFUND_LOT). Phase 1: `/refund_lot`
# issues a token; phase 2: `/confirm <token> <code>` invokes RefundLot use-case.
# ───────────────────────────────────────────────────────────────────────────
admin-refund-lot-usage = ⚠️ Uso: <code>/refund_lot &lt;lot_id&gt; &lt;razón&gt;</code>. Ambos argumentos son obligatorios.
admin-refund-lot-not-authorized = ❌ Solo los super-admins pueden forzar el reembolso de lotes de premio.
admin-refund-lot-totp-not-configured = ❌ Tu TOTP no está configurado. <code>/refund_lot</code> no está disponible hasta que ejecutes <code>/admin_setup_totp</code>.
admin-refund-lot-bad-lot-id = ⚠️ <code>{ $value }</code> no es un lot_id válido (entero positivo).
admin-refund-lot-no-reason = ⚠️ La razón es obligatoria. Uso: <code>/refund_lot &lt;lot_id&gt; &lt;razón&gt;</code>.
admin-refund-lot-confirm-issued = 🛡️ Confirma el reembolso. Responde: <code>/confirm { $token } &lt;código de 6 dígitos&gt;</code>. El token expira en { $ttl_seconds } segundos.
admin-refund-lot-success = ✅ Lote <code>#{ $lot_id }</code> ({ $currency } <code>{ $amount }</code>) devuelto al pool. Saldo del pool después del reembolso: <code>{ $pool_after }</code>.
admin-refund-lot-already-refunded = ℹ️ El lote <code>#{ $lot_id }</code> ya fue reembolsado. Saldo del pool: <code>{ $pool_after }</code>.
admin-refund-lot-not-found = 🔍 Lote <code>#{ $lot_id }</code> no encontrado.
admin-refund-lot-bad-transition = 🚫 El lote <code>#{ $lot_id }</code> está en estado <code>{ $status }</code> — el reembolso vía <code>/refund_lot</code> no está permitido (ver GDD §12.6.6).

# ───────────────────────────────────────────────────────────────────────────
# Sprint 4.1-E.14 — admin commands `/freeze_payouts <reason>` + `/unfreeze_payouts`
# (GDD §12.6.6). Globally halt / resume crypto payouts (super-admin +
# TOTP-confirm). Access: SUPER_ADMIN (see `AdminCommandKind.FREEZE_PAYOUTS` /
# `UNFREEZE_PAYOUTS`). Phase 1: command issues a token; phase 2:
# `/confirm <token> <code>` invokes the corresponding use-case (`FreezePayouts`
# / `UnfreezePayouts`). Idempotent: a repeat `/freeze_payouts` by the same
# admin with the same reason is a no-op; `/unfreeze_payouts` while already
# unfrozen is a no-op.
# ───────────────────────────────────────────────────────────────────────────
admin-freeze-payouts-usage = ⚠️ Uso: <code>/freeze_payouts &lt;razón&gt;</code>. La razón es obligatoria.
admin-freeze-payouts-not-authorized = ❌ Solo los super-admins pueden congelar los pagos cripto.
admin-freeze-payouts-totp-not-configured = ❌ Tu TOTP no está configurado. <code>/freeze_payouts</code> no está disponible hasta que ejecutes <code>/admin_setup_totp</code>.
admin-freeze-payouts-no-reason = ⚠️ La razón es obligatoria. Uso: <code>/freeze_payouts &lt;razón&gt;</code>.
admin-freeze-payouts-confirm-issued = 🛡️ Confirma el congelamiento de pagos. Responde: <code>/confirm { $token } &lt;código de 6 dígitos&gt;</code>. El token expira en { $ttl_seconds } segundos.
admin-freeze-payouts-success = ✅ Los pagos cripto están ahora congelados. Razón: { $reason }
admin-freeze-payouts-already-frozen = ℹ️ Los pagos cripto ya fueron congelados por ti antes con la misma razón — no hay nada que hacer. Razón: { $reason }

admin-unfreeze-payouts-not-authorized = ❌ Solo los super-admins pueden descongelar los pagos cripto.
admin-unfreeze-payouts-totp-not-configured = ❌ Tu TOTP no está configurado. <code>/unfreeze_payouts</code> no está disponible hasta que ejecutes <code>/admin_setup_totp</code>.
admin-unfreeze-payouts-confirm-issued = 🛡️ Confirma el descongelamiento de pagos. Responde: <code>/confirm { $token } &lt;código de 6 dígitos&gt;</code>. El token expira en { $ttl_seconds } segundos.
admin-unfreeze-payouts-success = ✅ Los pagos cripto están permitidos de nuevo.
admin-unfreeze-payouts-already-unfrozen = ℹ️ Los pagos cripto no estaban congelados — no hay nada que descongelar.
